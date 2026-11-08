"""運用コマンド（specs/003-ingestion G3・R41）。"""

import uuid

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.cli import gc, reindex, sync_payload
from arag.ingest.index import QdrantIndex
from arag.ingest.pipeline import run_ingest
from arag.settings import Settings

from .conftest import ALICE
from .ingest_helpers import make_deps
from .test_ingest import MD, _personal, _upload

pytestmark = pytest.mark.integration


async def test_reindex_requeues_changed_versions_without_reparse(
    client: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    qdrant_index: QdrantIndex,
    storage_root: str,
    database_url: str,
) -> None:
    kb = await _personal(client, ALICE)
    job_id = (await _upload(client, kb, [("a.md", MD.encode())])).json()["items"][0]["job_id"]
    deps = make_deps(sessionmaker, storage_root, qdrant_index)
    await run_ingest(uuid.UUID(job_id), deps)
    settings = Settings(database_url=database_url, embed_model="fake-embed")
    # 版が同じなら対象 0 件
    assert await reindex(settings, all_=False, hashes=[], dry_run=False) == 0
    async with sessionmaker() as s:
        assert await s.scalar(text("SELECT status FROM app.ingest_jobs")) == "ready"
        await s.execute(text("UPDATE app.contents SET chunker_version = 'old'"))
        await s.commit()
    await reindex(settings, all_=False, hashes=[], dry_run=False)
    async with sessionmaker() as s:
        assert await s.scalar(text("SELECT status FROM app.ingest_jobs")) == "queued"
    # 原本を消しても保存済み docling.json から作り直せる（再解析しない）
    async with sessionmaker() as s:
        h = await s.scalar(text("SELECT content_hash FROM app.contents"))
    from pathlib import Path

    from arag.storage import content_prefix

    (Path(storage_root) / content_prefix(h) / "original.md").unlink()
    assert await run_ingest(uuid.UUID(job_id), deps) == "ready"


async def test_gc_command_with_zero_retention(
    client: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    qdrant_index: QdrantIndex,
    storage_root: str,
    database_url: str,
) -> None:
    kb = await _personal(client, ALICE)
    item = (await _upload(client, kb, [("a.md", MD.encode())])).json()["items"][0]
    await run_ingest(uuid.UUID(item["job_id"]), make_deps(sessionmaker, storage_root, qdrant_index))
    settings = Settings(
        database_url=database_url, storage_dir=storage_root, qdrant_collection=qdrant_index.alias
    )
    # 既定の保持期間内なら何も消えない
    assert await gc(settings, retention_days=None) == 0
    async with sessionmaker() as s:
        assert await s.scalar(text("SELECT count(*) FROM app.contents")) == 1
        await s.execute(text("UPDATE app.documents SET deleted_at = now() - interval '1 second'"))
        await s.commit()
    assert await gc(settings, retention_days=0) == 0
    async with sessionmaker() as s:
        assert await s.scalar(text("SELECT count(*) FROM app.contents")) == 0
        assert await s.scalar(text("SELECT count(*) FROM app.documents")) == 0


async def test_sync_payload_command_rewrites_refs(
    client: httpx.AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    qdrant_index: QdrantIndex,
    storage_root: str,
    database_url: str,
) -> None:
    kb = await _personal(client, ALICE)
    item = (await _upload(client, kb, [("a.md", MD.encode())])).json()["items"][0]
    await run_ingest(uuid.UUID(item["job_id"]), make_deps(sessionmaker, storage_root, qdrant_index))
    # payload が古い形のまま（例: P1 でアーカイブ時に外された）
    async with sessionmaker() as s:
        h = await s.scalar(text("SELECT content_hash FROM app.contents"))
    await qdrant_index.set_refs(h, [], [])
    settings = Settings(database_url=database_url, qdrant_collection=qdrant_index.alias)
    assert await sync_payload(settings) == 0
    pts, _ = await qdrant_index.client.scroll(qdrant_index.alias, limit=1)
    assert pts[0].payload["document_ids"] == [item["document_id"]]  # type: ignore[index]
