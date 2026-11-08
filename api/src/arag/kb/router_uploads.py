"""アップロード・ジョブ・進捗 SSE（specs/000-overview/api.md §3.5、R7〜R12・R26・R29・R30）。"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from arag.db.models import Content, IngestJob
from arag.deps import CtxDep
from arag.errors import ApiError, not_found
from arag.ingest import queue
from arag.ingest.events import TERMINAL, channel
from arag.kb import service, uploads
from arag.settings import Settings

router = APIRouter(tags=["uploads"])

MAX_FILES = 100
KEEPALIVE_SEC = 15.0


class UploadItem(BaseModel):
    filename: str
    document_id: uuid.UUID
    job_id: uuid.UUID | None
    status: uploads.UploadStatus


class UploadResult(BaseModel):
    items: list[UploadItem]


class JobOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID | None
    status: str
    stage: str
    progress: int
    stage_detail: str
    error: str | None
    attempts: int
    page_count: int | None
    chunk_count: int | None
    created_at: datetime
    finished_at: datetime | None


async def _job_out(ctx: CtxDep, job: IngestJob, document_id: uuid.UUID | None) -> JobOut:
    content = await ctx.session.get(Content, job.content_hash)
    chunk_count = None
    if job.status == "ready":
        chunk_count = await service.count_chunks(ctx.session, job.content_hash)
    return JobOut(
        id=job.id,
        document_id=document_id,
        status=job.status,
        stage=job.stage,
        progress=job.progress,
        stage_detail=job.stage_detail,
        error=job.error,
        attempts=job.attempts,
        page_count=content.page_count if content else None,
        chunk_count=chunk_count,
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


async def _visible_job(ctx: CtxDep, job_id: uuid.UUID, *, write: bool) -> tuple[IngestJob, uuid.UUID]:
    job = await ctx.session.get(IngestJob, job_id)
    if job is None:
        raise not_found()
    doc = await service.visible_document_for_content(ctx.session, ctx.principal, job.content_hash)
    if doc is None:
        raise not_found()
    if (
        write
        and await service.visible_document_for_content(
            ctx.session, ctx.principal, job.content_hash, write=True
        )
        is None
    ):
        raise ApiError(403, "forbidden", "このジョブを操作する権限がありません")
    return job, doc.id


@router.post("/v1/kbs/{kb_id}/uploads", response_model=UploadResult)
async def upload(
    request: Request,
    kb_id: uuid.UUID,
    ctx: CtxDep,
    files: Annotated[list[UploadFile], File(description="1〜N 件のファイル")],
    paths: Annotated[list[str] | None, Form(description="files と同じ順の相対パス（任意）")] = None,
    folder_id: Annotated[uuid.UUID | None, Form()] = None,
) -> UploadResult:
    settings: Settings = request.app.state.settings
    await service.get_writable_kb(ctx.session, ctx.principal, kb_id)
    if not ctx.principal.email_verified:
        raise ApiError(403, "email_not_verified", "メールアドレスの確認が必要です")
    if not files or len(files) > MAX_FILES:
        raise ApiError(400, "too_many_files", f"一度に送れるファイルは 1〜{MAX_FILES} 件です")
    if paths is not None and len(paths) != len(files):
        raise ApiError(400, "paths_mismatch", "paths の数が files と一致しません")
    await service.require_live_folder_in_kb(ctx.session, kb_id, folder_id)

    tmp = uploads.tmp_dir_for(settings.storage_dir)
    staged: list[uploads.Staged] = []
    try:
        # 先に全件を検査・一時保存する（1 件でも 413/415 なら全体を拒否）
        for i, f in enumerate(files):
            staged.append(
                await uploads.stage_upload(
                    f, paths[i] if paths else None, tmp, settings.upload_max_mb * 1024 * 1024
                )
            )
        outcomes = []
        for s in staged:
            target = await uploads.ensure_folder_path(ctx.session, kb_id, folder_id, s.folder_parts)
            outcomes.append(
                await uploads.register(
                    ctx.session,
                    request.app.state.storage,
                    s,
                    kb_id=kb_id,
                    folder_id=target,
                    user_id=ctx.principal.user_id,
                )
            )
        await ctx.session.commit()
    finally:
        for s in staged:
            await asyncio.to_thread(s.path.unlink, missing_ok=True)
    # 解析済みの内容に新しい参照が付いた → payload を更新（R23）
    reused = {s.content_hash for s, o in zip(staged, outcomes, strict=True) if o.status != "queued"}
    if reused:
        await ctx.payload_sync.sync(reused)
    return UploadResult(
        items=[
            UploadItem(filename=o.filename, document_id=o.document_id, job_id=o.job_id, status=o.status)
            for o in outcomes
        ]
    )


@router.get("/v1/jobs/events")
async def job_events(
    request: Request, ctx: CtxDep, ids: Annotated[str, Query(description="カンマ区切りのジョブ ID")]
) -> StreamingResponse:
    """購読 → 現状 → 差分の順で送り、全ジョブが終端になったら閉じる（R29）。"""
    try:
        job_ids = list(dict.fromkeys(uuid.UUID(x) for x in ids.split(",") if x.strip()))
    except ValueError as e:
        raise ApiError(400, "invalid_ids", "ジョブ ID が正しくありません") from e
    if not job_ids or len(job_ids) > MAX_FILES:
        raise ApiError(400, "invalid_ids", f"ジョブ ID は 1〜{MAX_FILES} 件です")
    # 権限外のジョブは黙って除く（存在を推測させない。R30）
    visible: dict[uuid.UUID, uuid.UUID] = {}
    for jid in job_ids:
        try:
            _, doc_id = await _visible_job(ctx, jid, write=False)
            visible[jid] = doc_id
        except ApiError:
            continue
    redis = request.app.state.redis
    sessionmaker = request.app.state.sessionmaker
    await ctx.session.close()

    async def stream() -> AsyncIterator[str]:
        pubsub = redis.pubsub()
        try:
            if visible:
                await pubsub.subscribe(*(channel(str(j)) for j in visible))
            pending = set(visible)
            # 購読してから現状を 1 回送る（購読前の更新を取りこぼさない）
            async with sessionmaker() as s:
                rows = await s.scalars(select(IngestJob).where(IngestJob.id.in_(list(visible))))
                for job in rows:
                    content = await s.get(Content, job.content_hash)
                    ev = _event(job, visible[job.id], content.page_count if content else None)
                    if job.status == "ready":
                        ev["chunk_count"] = await service.count_chunks(s, job.content_hash)
                    yield _sse(ev)
                    if job.status in TERMINAL:
                        pending.discard(job.id)
            while pending:
                if await request.is_disconnected():
                    return
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=KEEPALIVE_SEC)
                if msg is None:
                    yield ": keep-alive\n\n"
                    continue
                data = json.loads(msg["data"])
                jid = uuid.UUID(data["job_id"])
                if jid not in visible:
                    continue
                data["document_id"] = str(visible[jid])
                yield _sse(data)
                if data.get("status") in TERMINAL:
                    pending.discard(jid)
        finally:
            await pubsub.aclose()

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


def _event(job: IngestJob, document_id: uuid.UUID, page_count: int | None) -> dict[str, Any]:
    ev: dict[str, Any] = {
        "job_id": str(job.id),
        "document_id": str(document_id),
        "stage": job.stage,
        "progress": job.progress,
        "stage_detail": job.stage_detail,
        "status": job.status,
    }
    if job.error and job.status == "error":
        ev["error"] = job.error
    if page_count:
        ev["page_count"] = page_count
    return ev


def _sse(data: dict[str, Any]) -> str:
    return f"event: job\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/v1/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, ctx: CtxDep) -> JobOut:
    job, doc_id = await _visible_job(ctx, job_id, write=False)
    return await _job_out(ctx, job, doc_id)


@router.post("/v1/jobs/{job_id}/retry", response_model=JobOut)
async def retry_job(job_id: uuid.UUID, ctx: CtxDep) -> JobOut:
    job, doc_id = await _visible_job(ctx, job_id, write=True)
    if job.status not in ("error", "cancelled"):
        raise ApiError(409, "job_not_retryable", "失敗または取り消したジョブだけ再試行できます")
    await queue.reset_for_retry(ctx.session, job)
    await ctx.session.commit()
    await ctx.session.refresh(job)
    return await _job_out(ctx, job, doc_id)


@router.post("/v1/jobs/{job_id}/cancel", response_model=JobOut)
async def cancel_job(job_id: uuid.UUID, ctx: CtxDep) -> JobOut:
    job, doc_id = await _visible_job(ctx, job_id, write=True)
    if job.status in TERMINAL:
        raise ApiError(409, "job_finished", "このジョブは既に終了しています")
    locked = await ctx.session.get(IngestJob, job_id, with_for_update=True, populate_existing=True)
    assert locked is not None
    job = locked
    if job.status == "queued":
        # 未着手なら即座に取消（R26）
        job.status = "cancelled"
        job.stage_detail = "取り消しました"
        content = await ctx.session.get(Content, job.content_hash)
        if content is not None:
            content.status = "cancelled"
    else:
        job.cancel_requested = True  # 実行中はワーカーが段階の境目で止める
    await ctx.session.commit()
    await ctx.session.refresh(job)
    if job.status == "cancelled":
        # API 側で終端にしたときも購読者へ知らせる
        await ctx.publisher.publish(
            str(job.id),
            {
                "job_id": str(job.id),
                "status": "cancelled",
                "stage": job.stage,
                "stage_detail": job.stage_detail,
            },
        )
    return await _job_out(ctx, job, doc_id)
