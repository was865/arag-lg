"""Qdrant の索引（specs/003-ingestion/design.md §3.6、R22・R23）。

コレクション `{name}_v1` をエイリアス `{name}` で参照する（埋め込みモデル切替時に並行作成して付け替える）。
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.db.models import Document, KnowledgeBase
from arag.ingest.sparse import SparseVector
from arag.logging import get_logger

log = get_logger("arag.ingest.index")

DENSE = "dense"
SPARSE = "bm25"
KEYWORD_FIELDS = ("content_hash", "document_ids", "kb_ids", "block_type")


@dataclass(slots=True)
class IndexPoint:
    id: uuid.UUID
    dense: list[float]
    sparse: SparseVector
    payload: dict[str, Any]


def _hash_filter(content_hash: str) -> models.Filter:
    return models.Filter(
        must=[models.FieldCondition(key="content_hash", match=models.MatchValue(value=content_hash))]
    )


def _is_missing(e: UnexpectedResponse) -> bool:
    return e.status_code == 404


class QdrantIndex:
    def __init__(self, client: AsyncQdrantClient, alias: str = "chunks") -> None:
        self.client = client
        self.alias = alias

    @property
    def collection(self) -> str:
        return f"{self.alias}_v1"

    async def _alias_exists(self) -> bool:
        aliases = await self.client.get_aliases()
        return any(a.alias_name == self.alias for a in aliases.aliases)

    async def ensure_collection(self, dim: int) -> None:
        """冪等。既存なら次元だけ確認する。"""
        if not await self.client.collection_exists(self.collection):
            try:
                await self.client.create_collection(
                    self.collection,
                    vectors_config={DENSE: models.VectorParams(size=dim, distance=models.Distance.COSINE)},
                    sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
                )
            except UnexpectedResponse as e:
                if e.status_code != 409:  # 並行作成は無視
                    raise
            for f in KEYWORD_FIELDS:
                await self.client.create_payload_index(
                    self.collection, field_name=f, field_schema=models.PayloadSchemaType.KEYWORD
                )
        else:
            info = await self.client.get_collection(self.collection)
            vectors = info.config.params.vectors
            size = vectors[DENSE].size if isinstance(vectors, dict) else None
            if size != dim:
                raise RuntimeError(
                    f"Qdrant の次元が一致しません: collection={size} embedder={dim}（再索引が必要）"
                )
        if not await self._alias_exists():
            await self.client.update_collection_aliases(
                change_aliases_operations=[
                    models.CreateAliasOperation(
                        create_alias=models.CreateAlias(
                            collection_name=self.collection, alias_name=self.alias
                        )
                    )
                ]
            )

    async def upsert(self, points: Sequence[IndexPoint], batch: int = 128) -> None:
        for i in range(0, len(points), batch):
            await self.client.upsert(
                self.alias,
                points=[
                    models.PointStruct(
                        id=str(p.id),
                        vector={
                            DENSE: p.dense,
                            SPARSE: models.SparseVector(indices=p.sparse.indices, values=p.sparse.values),
                        },
                        payload=p.payload,
                    )
                    for p in points[i : i + batch]
                ],
                wait=True,
            )

    # コレクション未作成（初回入庫前）なら消す・数える・更新する対象も無い
    async def delete_content(self, content_hash: str) -> None:
        try:
            await self.client.delete(
                self.alias,
                points_selector=models.FilterSelector(filter=_hash_filter(content_hash)),
                wait=True,
            )
        except UnexpectedResponse as e:
            if not _is_missing(e):
                raise

    async def count(self, content_hash: str) -> int:
        try:
            res = await self.client.count(self.alias, count_filter=_hash_filter(content_hash), exact=True)
        except UnexpectedResponse as e:
            if not _is_missing(e):
                raise
            return 0
        return res.count

    async def set_refs(self, content_hash: str, document_ids: list[str], kb_ids: list[str]) -> None:
        try:
            await self.client.set_payload(
                self.alias,
                payload={"document_ids": document_ids, "kb_ids": kb_ids},
                points=_hash_filter(content_hash),
                wait=True,
            )
        except UnexpectedResponse as e:
            if not _is_missing(e):
                raise


async def live_refs(session: AsyncSession, content_hash: str) -> tuple[list[str], list[str]]:
    """検索対象になる参照: 生存文書 × 生存かつアーカイブされていない KB。"""
    rows = await session.execute(
        select(Document.id, Document.kb_id)
        .join(KnowledgeBase, KnowledgeBase.id == Document.kb_id)
        .where(
            Document.content_hash == content_hash,
            Document.deleted_at.is_(None),
            KnowledgeBase.deleted_at.is_(None),
            KnowledgeBase.status == "active",
        )
    )
    pairs = rows.all()
    return sorted({str(d) for d, _ in pairs}), sorted({str(k) for _, k in pairs})


class QdrantPayloadSync:
    """KB・フォルダ・文書 API から呼ばれる PayloadSync の実体。"""

    def __init__(self, index: QdrantIndex, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self.index = index
        self.sessionmaker = sessionmaker

    async def sync(self, content_hashes: Iterable[str]) -> None:
        async with self.sessionmaker() as session:
            for h in set(content_hashes):
                docs, kbs = await live_refs(session, h)
                try:
                    await self.index.set_refs(h, docs, kbs)
                except Exception as e:
                    # 正は DB。ずれはワーカーの定期照合で直す（data-model §4）
                    log.warning("payload_sync_failed", content_hash=h, error=f"{type(e).__name__}: {e}")
