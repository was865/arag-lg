"""Qdrant 索引（specs/003-ingestion D8・R22・R23）。"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.ingest.index import IndexPoint, QdrantIndex, QdrantPayloadSync
from arag.ingest.sparse import SparseVector

pytestmark = pytest.mark.integration

H = "e" * 64


def _point(i: int) -> IndexPoint:
    return IndexPoint(
        id=uuid.uuid4(),
        dense=[1.0, float(i), 0.0, 0.5],
        sparse=SparseVector(indices=[1, 7 + i], values=[0.5, 1.2]),
        payload={"content_hash": H, "block_type": "text", "document_ids": [], "kb_ids": []},
    )


async def test_ensure_collection_idempotent_and_dim_checked(qdrant_index: QdrantIndex) -> None:
    await qdrant_index.ensure_collection(4)
    await qdrant_index.ensure_collection(4)
    info = await qdrant_index.client.get_collection(qdrant_index.alias)
    assert info.config.params.sparse_vectors is not None
    with pytest.raises(RuntimeError, match="次元"):
        await qdrant_index.ensure_collection(8)


async def test_upsert_count_delete(qdrant_index: QdrantIndex) -> None:
    await qdrant_index.ensure_collection(4)
    await qdrant_index.upsert([_point(i) for i in range(5)], batch=2)
    assert await qdrant_index.count(H) == 5
    pts, _ = await qdrant_index.client.scroll(qdrant_index.alias, limit=1, with_vectors=True)
    assert set(pts[0].vector) == {"dense", "bm25"}  # type: ignore[arg-type]
    await qdrant_index.delete_content(H)
    assert await qdrant_index.count(H) == 0


async def test_sync_payload_drops_trashed_keeps_archived(
    qdrant_index: QdrantIndex, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await qdrant_index.ensure_collection(4)
    await qdrant_index.upsert([_point(0)])
    kb1, kb2, d1, d2 = (uuid.uuid4() for _ in range(4))
    async with sessionmaker() as s:
        await s.execute(
            text(
                "INSERT INTO app.knowledge_bases (id, kind, name, status) "
                "VALUES (:a, 'org', 'A', 'active'), (:b, 'org', 'B', 'active')"
            ),
            {"a": kb1, "b": kb2},
        )
        await s.execute(
            text(
                "INSERT INTO app.contents (content_hash, mime, ext, size, status, ref_count) "
                "VALUES (:h, 'text/plain', 'txt', 1, 'ready', 2)"
            ),
            {"h": H},
        )
        await s.execute(
            text(
                "INSERT INTO app.documents (id, kb_id, content_hash, filename, uploaded_by) "
                "VALUES (:d1, :a, :h, 'a', 'u'), (:d2, :b, :h, 'b', 'u')"
            ),
            {"d1": d1, "d2": d2, "a": kb1, "b": kb2, "h": H},
        )
        await s.commit()

    sync = QdrantPayloadSync(qdrant_index, sessionmaker)

    async def payload() -> dict:  # type: ignore[type-arg]
        pts, _ = await qdrant_index.client.scroll(qdrant_index.alias, limit=1)
        return pts[0].payload or {}

    await sync.sync([H])
    assert sorted((await payload())["document_ids"]) == sorted([str(d1), str(d2)])

    async with sessionmaker() as s:
        await s.execute(text("UPDATE app.documents SET deleted_at = now() WHERE id = :d"), {"d": d1})
        await s.execute(text("UPDATE app.knowledge_bases SET status = 'archived' WHERE id = :b"), {"b": kb2})
        await s.commit()
    await sync.sync([H])
    p = await payload()
    # アーカイブは検索時のフィルタで除く（payload からは外さない。specs/004-retrieval R5）
    assert p["document_ids"] == [str(d2)] and p["kb_ids"] == [str(kb2)]
    async with sessionmaker() as s:
        await s.execute(text("UPDATE app.knowledge_bases SET deleted_at = now() WHERE id = :b"), {"b": kb2})
        await s.commit()
    await sync.sync([H])
    p = await payload()
    assert p["document_ids"] == [] and p["kb_ids"] == []


async def test_missing_collection_is_noop(qdrant_index: QdrantIndex) -> None:
    # 初回入庫前（コレクション未作成）でも掃除・照合は失敗しない
    await qdrant_index.delete_content(H)
    await qdrant_index.set_refs(H, [], [])
    assert await qdrant_index.count(H) == 0
