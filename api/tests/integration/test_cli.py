"""運用コマンド（specs/003-ingestion G3・R41）。"""

import uuid

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.cli import reindex
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
