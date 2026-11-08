"""Postgres のジョブキュー（specs/003-ingestion/design.md §3.0、R24・R26・R27）。

ingest_jobs 自体をキューにする。取得は FOR UPDATE SKIP LOCKED。
"""

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from arag.db.models import Content, IngestJob

NOTIFY_CHANNEL = "ingest_jobs"
RETRY_BASE = timedelta(seconds=30)
STALE_AFTER = timedelta(seconds=60)
HEARTBEAT_EVERY = timedelta(seconds=15)


async def notify(session: AsyncSession, job_id: uuid.UUID) -> None:
    """同じトランザクションで NOTIFY（コミット時に届く）。"""
    await session.execute(text("SELECT pg_notify(:ch, :id)"), {"ch": NOTIFY_CHANNEL, "id": str(job_id)})


async def enqueue(session: AsyncSession, content_hash: str) -> IngestJob:
    job = IngestJob(id=uuid.uuid4(), content_hash=content_hash, status="queued", stage="queued")
    session.add(job)
    await session.flush()
    await notify(session, job.id)
    return job


async def reset_for_retry(session: AsyncSession, job: IngestJob) -> None:
    """利用者の再試行: 回数をリセットして再投入（R26）。"""
    job.status = "queued"
    job.stage = "queued"
    job.progress = 0
    job.stage_detail = "待機中"
    job.error = None
    job.error_detail = None
    job.attempts = 0
    job.cancel_requested = False
    job.locked_by = None
    # 手動の再試行・再索引は新しい実行（自動再試行は claim の COALESCE で初回の開始時刻を保つ）
    job.started_at = None
    job.finished_at = None
    await session.execute(update(IngestJob).where(IngestJob.id == job.id).values(run_after=text("now()")))
    await session.execute(
        update(Content).where(Content.content_hash == job.content_hash).values(status="queued")
    )
    await notify(session, job.id)


async def claim(session: AsyncSession, worker_id: str) -> uuid.UUID | None:
    """実行可能なジョブを 1 件取って running にする。"""
    row = await session.execute(
        text(
            """
            UPDATE app.ingest_jobs SET status = 'running', locked_by = :w, heartbeat_at = now(),
                   started_at = COALESCE(started_at, now())
            WHERE id = (
              SELECT id FROM app.ingest_jobs
              WHERE status = 'queued' AND run_after <= now()
              ORDER BY run_after
              FOR UPDATE SKIP LOCKED
              LIMIT 1
            )
            RETURNING id
            """
        ),
        {"w": worker_id},
    )
    job_id = row.scalar_one_or_none()
    await session.commit()
    return job_id


async def heartbeat(session: AsyncSession, job_id: uuid.UUID, worker_id: str) -> bool:
    """自分が持っている間だけ更新できる。False なら他者に奪われた（停止扱いで再投入済み）。"""
    res = await session.execute(
        update(IngestJob)
        .where(IngestJob.id == job_id, IngestJob.locked_by == worker_id, IngestJob.status == "running")
        .values(heartbeat_at=text("now()"))
    )
    await session.commit()
    return bool(res.rowcount)  # type: ignore[attr-defined]


async def requeue_stale(session: AsyncSession, stale_after: timedelta = STALE_AFTER) -> list[uuid.UUID]:
    """ハートビートが途絶えた running を queued に戻す（R27）。"""
    rows = await session.scalars(
        update(IngestJob)
        .where(
            IngestJob.status == "running",
            IngestJob.heartbeat_at
            < text("now() - make_interval(secs => :s)").bindparams(s=stale_after.total_seconds()),
        )
        .values(status="queued", locked_by=None, run_after=text("now()"), stage_detail="再開待ち")
        .returning(IngestJob.id)
    )
    ids = list(rows)
    await session.commit()
    return ids


async def is_cancel_requested(session: AsyncSession, job_id: uuid.UUID) -> bool:
    return bool(await session.scalar(select(IngestJob.cancel_requested).where(IngestJob.id == job_id)))


def retry_delay(attempts: int) -> timedelta:
    return timedelta(seconds=RETRY_BASE.total_seconds() * 2**attempts)


async def record_failure(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    user_message: str,
    detail: str,
    retryable: bool,
    max_retries: int,
) -> str:
    """失敗を記録し、上限内なら遅延付きで queued に戻す。戻り値は新しい status（R24）。"""
    job = await session.get(IngestJob, job_id, with_for_update=True)
    assert job is not None
    job.attempts += 1
    job.error = user_message
    job.error_detail = detail[:8000]
    job.locked_by = None
    values: dict[str, Any]
    if retryable and job.attempts <= max_retries:
        job.status = "queued"
        job.stage_detail = f"再試行待ち（{job.attempts}/{max_retries}）"
        delay = retry_delay(job.attempts).total_seconds()
        values = {"run_after": text("now() + make_interval(secs => :d)").bindparams(d=delay)}
        content_status = "queued"
    else:
        job.status = "error"
        job.stage_detail = "エラー"
        values = {"finished_at": text("now()")}
        content_status = "error"
    await session.execute(update(IngestJob).where(IngestJob.id == job_id).values(**values))
    await session.execute(
        update(Content)
        .where(Content.content_hash == job.content_hash)
        .values(status=content_status, error=job.error)
    )
    await session.commit()
    return job.status
