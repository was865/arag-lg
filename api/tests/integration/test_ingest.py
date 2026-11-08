"""アップロード → キュー → パイプライン → 進捗 → GC（specs/003-ingestion C1〜C4・E1〜E7）。"""

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.db.models import Chunk, Content, IngestJob, Section
from arag.ingest import queue
from arag.ingest.events import RedisPublisher
from arag.ingest.gc import run_gc
from arag.ingest.index import QdrantIndex
from arag.ingest.pipeline import run_ingest
from arag.settings import Settings
from arag.storage import content_prefix

from .conftest import ADMIN, ALICE, BOB, RecordingSync, as_user
from .ingest_helpers import FakeEmbedder, RecordingPublisher, make_deps

pytestmark = pytest.mark.integration

MD = "# 総則\n\n## 目的\n\nこの規程は情報資産を守る。\n\n## 定義\n\n情報資産とは MX-17 型番の機器をいう。\n"


async def _personal(client: httpx.AsyncClient, headers: dict[str, str]) -> str:
    kbs = (await client.get("/v1/kbs", headers=headers)).json()
    return str(next(k for k in kbs if k["kind"] == "personal")["id"])


async def _upload(
    client: httpx.AsyncClient,
    kb: str,
    files: list[tuple[str, bytes]],
    headers: dict[str, str] = ALICE,
    paths: list[str] | None = None,
) -> httpx.Response:
    data: dict[str, list[str]] = {"paths": paths} if paths else {}
    return await client.post(
        f"/v1/kbs/{kb}/uploads",
        files=[("files", (name, body, "application/octet-stream")) for name, body in files],
        data=data,
        headers=headers,
    )


async def _counts(sm: async_sessionmaker[AsyncSession], h: str) -> tuple[int, int]:
    async with sm() as s:
        c = await s.scalar(select(func.count(Chunk.id)).where(Chunk.content_hash == h))
        sec = await s.scalar(select(func.count(Section.id)).where(Section.content_hash == h))
    return int(c or 0), int(sec or 0)


async def _hash_of_job(sm: async_sessionmaker[AsyncSession], job_id: str) -> str:
    async with sm() as s:
        job = await s.get(IngestJob, uuid.UUID(job_id))
        assert job is not None
        return job.content_hash


async def test_upload_ingest_ready_and_indexed(
    client: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    qdrant_index: QdrantIndex,
    storage_root: str,
) -> None:
    kb = await _personal(client, ALICE)
    res = await _upload(client, kb, [("規程.md", MD.encode()), ("memo.txt", "メモ本文".encode())])
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert [i["status"] for i in items] == ["queued", "queued"]

    publisher = RecordingPublisher()
    deps = make_deps(sessionmaker, storage_root, qdrant_index, publisher=publisher)
    job_id = items[0]["job_id"]
    assert await run_ingest(uuid.UUID(job_id), deps) == "ready"

    # 段階が順に進み、progress は単調増加（R13）
    stages = [e["stage"] for e in publisher.events if "stage" in e]
    order = ["parsing", "chunking", "contextualizing", "embedding", "indexing", "ready"]
    assert [s for s in order if s in stages] == order
    progress = [e["progress"] for e in publisher.events if "progress" in e]
    assert progress == sorted(progress) and progress[-1] == 100

    job = (await client.get(f"/v1/jobs/{job_id}", headers=ALICE)).json()
    assert job["status"] == "ready" and job["chunk_count"] > 0
    assert job["document_id"] == items[0]["document_id"]

    h = await _hash_of_job(sessionmaker, job_id)
    chunks, sections = await _counts(sessionmaker, h)
    assert sections == 2  # 「総則 > 目的」「総則 > 定義」
    # E4: 子チャンク数 = 点の数、点は dense と bm25 を持つ
    assert await qdrant_index.count(h) == chunks
    pts, _ = await qdrant_index.client.scroll(qdrant_index.alias, limit=1, with_vectors=True)
    assert set(pts[0].vector) == {"dense", "bm25"}  # type: ignore[arg-type]
    assert pts[0].payload["document_ids"] == [items[0]["document_id"]]  # type: ignore[index]
    # 成果物が保存されている
    root = Path(storage_root) / content_prefix(h)
    assert {"original.md", "docling.json", "rendered.md"} <= {p.name for p in root.iterdir()}
    async with sessionmaker() as s:
        content = await s.get(Content, h)
        assert content is not None
        assert content.status == "ready" and content.embed_model == "fake-embed" and content.indexed_at
        ctx = list(await s.scalars(select(Chunk.context).where(Chunk.content_hash == h)))
    assert all(c.startswith("規程 > 総則") for c in ctx)  # 見出しフォールバック


async def test_dedup_skipped_and_duplicate(
    client: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    qdrant_index: QdrantIndex,
    storage_root: str,
    payload_sync: RecordingSync,
) -> None:
    kb = await _personal(client, ALICE)
    first = (await _upload(client, kb, [("a.md", MD.encode())])).json()["items"][0]
    await run_ingest(uuid.UUID(first["job_id"]), make_deps(sessionmaker, storage_root, qdrant_index))
    # 同じ KB → duplicate（同じ document_id）
    again = (await _upload(client, kb, [("別名.md", MD.encode())])).json()["items"][0]
    assert again["status"] == "duplicate" and again["document_id"] == first["document_id"]
    # 別 KB → 解析し直さず skipped（E3）、payload を同期
    org = (await client.post("/v1/kbs", json={"name": "全社"}, headers=ADMIN)).json()["id"]
    other = (await _upload(client, org, [("a.md", MD.encode())], headers=ADMIN)).json()["items"][0]
    assert other["status"] == "skipped" and other["job_id"] is None
    h = await _hash_of_job(sessionmaker, first["job_id"])
    assert payload_sync.calls[-1] == {h}
    async with sessionmaker() as s:
        jobs = await s.scalar(select(func.count(IngestJob.id)).where(IngestJob.content_hash == h))
        content = await s.get(Content, h)
    assert jobs == 1
    assert content is not None and content.ref_count == 2


async def test_concurrent_first_uploads_create_one_job(
    client: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    users = [as_user(f"u{i}") for i in range(6)]
    kbs = [await _personal(client, u) for u in users]
    body = "同時アップロード".encode()
    results = await asyncio.gather(
        *(_upload(client, kb, [("x.txt", body)], u) for kb, u in zip(kbs, users, strict=True))
    )
    statuses = sorted(r.json()["items"][0]["status"] for r in results)
    assert statuses.count("queued") == 1 and statuses.count("skipped") == 5
    async with sessionmaker() as s:
        assert await s.scalar(text("SELECT count(*) FROM app.ingest_jobs")) == 1
        assert await s.scalar(text("SELECT ref_count FROM app.contents")) == 6


async def test_relative_paths_create_folders(client: httpx.AsyncClient) -> None:
    kb = await _personal(client, ALICE)
    res = await _upload(
        client, kb, [("a.txt", b"a"), ("b.txt", b"b")], paths=["docs/規程/a.txt", "docs/../b.txt"]
    )
    assert res.status_code == 200, res.text
    assert [i["filename"] for i in res.json()["items"]] == ["a.txt", "b.txt"]
    folders = (await client.get(f"/v1/kbs/{kb}/folders", headers=ALICE)).json()
    by_name = {f["name"]: f for f in folders}
    assert set(by_name) == {"docs", "規程"}
    assert by_name["規程"]["parent_id"] == by_name["docs"]["id"]
    assert by_name["規程"]["document_count"] == 1 and by_name["docs"]["document_count"] == 1


async def test_rejects_unsupported_and_too_large(
    make_client: Callable[..., Awaitable[httpx.AsyncClient]], storage_root: str
) -> None:
    client = await make_client(upload_max_mb=1)
    kb = await _personal(client, ALICE)
    res = await _upload(client, kb, [("ok.txt", b"x"), ("evil.exe", b"MZ")])
    assert res.status_code == 415
    res = await _upload(client, kb, [("big.txt", b"x" * (1024 * 1024 + 1))])
    assert res.status_code == 413
    # 拒否時は内容も一時ファイルも残らない
    assert not list((Path(storage_root) / ".tmp").glob("*"))
    # 他人の KB へは 404、閲覧のみの全社 KB へは 403
    assert (await _upload(client, kb, [("a.txt", b"a")], headers=BOB)).status_code == 404
    org = (await client.post("/v1/kbs", json={"name": "全社"}, headers=ADMIN)).json()["id"]
    assert (await _upload(client, org, [("a.txt", b"a")], headers=BOB)).status_code == 403


async def test_rerun_is_idempotent(
    client: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    qdrant_index: QdrantIndex,
    storage_root: str,
) -> None:
    kb = await _personal(client, ALICE)
    job_id = (await _upload(client, kb, [("a.md", MD.encode())])).json()["items"][0]["job_id"]
    deps = make_deps(sessionmaker, storage_root, qdrant_index)
    await run_ingest(uuid.UUID(job_id), deps)
    h = await _hash_of_job(sessionmaker, job_id)
    before = await _counts(sessionmaker, h)
    await run_ingest(uuid.UUID(job_id), deps)
    assert await _counts(sessionmaker, h) == before
    assert await qdrant_index.count(h) == before[0]


async def test_cancel_queued_and_running(
    client: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    qdrant_index: QdrantIndex,
    storage_root: str,
) -> None:
    kb = await _personal(client, ALICE)
    items = (await _upload(client, kb, [("a.txt", b"one"), ("b.txt", b"two")])).json()["items"]
    # queued は即座に cancelled
    res = await client.post(f"/v1/jobs/{items[0]['job_id']}/cancel", headers=ALICE)
    assert res.json()["status"] == "cancelled"
    # 他人は操作できない（404）
    assert (await client.post(f"/v1/jobs/{items[1]['job_id']}/cancel", headers=BOB)).status_code == 404
    # 実行中扱い: フラグを立ててから実行 → 最初の段階の境目で止まる
    async with sessionmaker() as s:
        await s.execute(
            text("UPDATE app.ingest_jobs SET status='running', cancel_requested = true WHERE id = :id"),
            {"id": items[1]["job_id"]},
        )
        await s.commit()
    status = await run_ingest(
        uuid.UUID(items[1]["job_id"]), make_deps(sessionmaker, storage_root, qdrant_index)
    )
    assert status == "cancelled"
    h = await _hash_of_job(sessionmaker, items[1]["job_id"])
    assert await _counts(sessionmaker, h) == (0, 0)
    # 取消したジョブは再試行できる（attempts リセット）
    res = await client.post(f"/v1/jobs/{items[1]['job_id']}/retry", headers=ALICE)
    assert res.json()["status"] == "queued" and res.json()["attempts"] == 0
    # 手動の再試行は新しい実行なので開始時刻も消す（所要時間が前回からにならないように）
    assert res.json()["started_at"] is None and res.json()["finished_at"] is None


async def test_auto_retry_then_error(
    client: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    qdrant_index: QdrantIndex,
    storage_root: str,
) -> None:
    kb = await _personal(client, ALICE)
    job_id = uuid.UUID((await _upload(client, kb, [("a.txt", b"x")])).json()["items"][0]["job_id"])
    deps = make_deps(
        sessionmaker, storage_root, qdrant_index, embedder=FakeEmbedder(fail_times=10), max_retries=1
    )
    assert await run_ingest(job_id, deps) == "queued"
    async with sessionmaker() as s:
        job = await s.get(IngestJob, job_id)
        assert job is not None
        assert job.attempts == 1 and job.run_after > datetime.now(UTC) + timedelta(seconds=30)
    assert await run_ingest(job_id, deps) == "error"
    body = (await client.get(f"/v1/jobs/{job_id}", headers=ALICE)).json()
    assert body["status"] == "error"
    assert body["error"] == "ベクトル化サービスでエラーが発生しました"
    assert "error_detail" not in body  # ログ用の詳細は API で返さない
    async with sessionmaker() as s:
        job = await s.get(IngestJob, job_id)
        assert job is not None and "EmbedError" in (job.error_detail or "")


async def test_claim_and_requeue_stale(
    client: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    kb = await _personal(client, ALICE)
    await _upload(client, kb, [("a.txt", b"a")])
    async with sessionmaker() as s:
        jid = await queue.claim(s, "w1")
        assert jid is not None
        assert await queue.claim(s, "w2") is None  # 1 件しか無い
        assert await queue.heartbeat(s, jid, "w1")
        assert not await queue.heartbeat(s, jid, "w2")
        await s.execute(text("UPDATE app.ingest_jobs SET heartbeat_at = now() - interval '2 minutes'"))
        await s.commit()
        assert await queue.requeue_stale(s) == [jid]
        assert await queue.claim(s, "w2") == jid


async def test_progress_sse(
    client: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    qdrant_index: QdrantIndex,
    storage_root: str,
) -> None:
    kb = await _personal(client, ALICE)
    items = (await _upload(client, kb, [("a.md", MD.encode()), ("b.txt", b"bb")])).json()["items"]
    ids = ",".join(i["job_id"] for i in items)
    # b は先に終わらせておく（現状の送信で ready が出る）
    redis = Redis.from_url(Settings().redis_url, decode_responses=True)
    deps = make_deps(sessionmaker, storage_root, qdrant_index, publisher=RedisPublisher(redis))
    await run_ingest(uuid.UUID(items[1]["job_id"]), deps)

    events: list[dict[str, object]] = []

    async def read() -> None:
        async with client.stream("GET", f"/v1/jobs/events?ids={ids},{uuid.uuid4()}", headers=ALICE) as res:
            assert res.status_code == 200
            async for line in res.aiter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))

    reader = asyncio.create_task(read())
    await asyncio.sleep(0.5)  # 購読が始まるのを待つ
    await run_ingest(uuid.UUID(items[0]["job_id"]), deps)
    await asyncio.wait_for(reader, timeout=10)  # 全ジョブ終端で閉じる
    await redis.aclose()

    assert {e["job_id"] for e in events} == {i["job_id"] for i in items}  # 不明 ID は送らない
    first_a = next(e for e in events if e["job_id"] == items[0]["job_id"])
    assert first_a["status"] == "queued"  # 現状 → 差分の順
    last_a = [e for e in events if e["job_id"] == items[0]["job_id"]][-1]
    assert last_a["status"] == "ready" and last_a["document_id"] == items[0]["document_id"]
    assert last_a["chunk_count"] >= 1
    # 他人は購読しても何も受け取らずに閉じる
    res = await client.get(f"/v1/jobs/events?ids={ids}", headers=BOB)
    assert "data:" not in res.text


async def test_gc_removes_rows_points_and_files(
    client: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    qdrant_index: QdrantIndex,
    storage_root: str,
) -> None:
    kb = await _personal(client, ALICE)
    item = (await _upload(client, kb, [("a.md", MD.encode())])).json()["items"][0]
    deps = make_deps(sessionmaker, storage_root, qdrant_index)
    await run_ingest(uuid.UUID(item["job_id"]), deps)
    h = await _hash_of_job(sessionmaker, item["job_id"])
    # 保持期間内のごみ箱は消えない
    async with sessionmaker() as s:
        await s.execute(text("UPDATE app.documents SET deleted_at = now()"))
        await s.commit()
    async with sessionmaker() as s:
        counts = await run_gc(
            s, deps.storage, qdrant_index, now=datetime.now(UTC), retention=timedelta(days=30)
        )
    assert counts == {"documents": 0, "folders": 0, "kbs": 0, "contents": 0}
    async with sessionmaker() as s:
        counts = await run_gc(
            s,
            deps.storage,
            qdrant_index,
            now=datetime.now(UTC) + timedelta(seconds=1),
            retention=timedelta(0),
        )
    assert counts["documents"] == 1 and counts["contents"] == 1
    assert await _counts(sessionmaker, h) == (0, 0)
    assert await qdrant_index.count(h) == 0
    assert not (Path(storage_root) / content_prefix(h)).exists()
    async with sessionmaker() as s:
        assert (
            await s.scalar(text("SELECT action FROM app.audit_logs WHERE action = 'gc.purge'")) == "gc.purge"
        )
