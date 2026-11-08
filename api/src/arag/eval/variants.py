"""比較条件（variant）と、variant 用の別コレクション作成（specs/004-retrieval R21・R22）。"""

import os
import uuid
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml
from qdrant_client import AsyncQdrantClient
from qdrant_client import models as qm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arag.db.models import Chunk, Document
from arag.ingest.embedder import TeiEmbedder
from arag.ingest.index import IndexPoint, QdrantIndex, live_refs
from arag.ingest.sparse import SparseEncoder
from arag.search.config import SearchConfig
from arag.search.rerank import TeiReranker
from arag.search.service import SearchDeps
from arag.settings import Settings

DEFAULT_EMBED = "bge-m3"


@dataclass(frozen=True)
class ModelSpec:
    url_env: str
    model: str
    query_prefix: str = ""
    document_prefix: str = ""

    def url(self) -> str:
        v = env(self.url_env)
        if not v:
            raise SystemExit(f"{self.url_env} が設定されていません（.env に TEI の URL を書いてください）")
        return v


@dataclass(frozen=True)
class Variant:
    name: str
    mode: str = "hybrid"
    fusion: str = "rrf"
    rrf_k: int = 60
    weights: tuple[float, float] = (1.0, 1.0)
    rerank: bool = True
    rerank_input: str = "context+text"
    embed: str = DEFAULT_EMBED
    reranker: str = "bge-reranker-v2-m3"
    context: bool = True
    sparse_en_stem: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def own_collection(self) -> bool:
        """本番の索引と違う埋め込み・文脈・sparse なら別コレクションが要る。"""
        return self.embed != DEFAULT_EMBED or not self.context or self.sparse_en_stem

    def collection(self, base: str) -> str:
        return f"eval__{self.name}" if self.own_collection else base

    def config(self) -> SearchConfig:
        return SearchConfig(
            fusion=self.fusion,  # type: ignore[arg-type]
            rrf_k=self.rrf_k,
            weights=self.weights,
            rerank_enabled=self.rerank,
            rerank_input=self.rerank_input,  # type: ignore[arg-type]
        )


def env(name: str) -> str:
    """環境変数、無ければ .env（api/ から見た ../.env と .env）。"""
    if os.environ.get(name):
        return os.environ[name]
    for p in (Path("../.env"), Path(".env")):
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                k, _, v = line.partition("=")
                if k.strip() == name and v.strip():
                    return v.strip()
    return ""


def load_variants(path: Path) -> tuple[dict[str, Variant], dict[str, ModelSpec]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    models = {k: ModelSpec(**v) for k, v in data["models"].items()}
    raw: dict[str, dict[str, Any]] = data["variants"]
    known = {f.name for f in fields(Variant)}

    def resolve(name: str, depth: int = 0) -> dict[str, Any]:
        if depth > 5:
            raise ValueError(f"variant の base が循環しています: {name}")
        spec = dict(raw[name])
        base = spec.pop("base", None)
        merged = resolve(base, depth + 1) if base else {}
        merged.update(spec)
        return merged

    out: dict[str, Variant] = {}
    for name in raw:
        spec = resolve(name)
        unknown = set(spec) - known
        if unknown:
            raise ValueError(f"variant {name}: 未知の項目 {sorted(unknown)}")
        if "weights" in spec:
            spec["weights"] = tuple(float(x) for x in spec["weights"])
        for key in ("embed", "reranker"):
            if key in spec and spec[key] not in models:
                raise ValueError(f"variant {name}: models に無い {key}={spec[key]}")
        out[name] = Variant(name=name, **spec)
    return out, models


def search_deps(
    v: Variant, models: dict[str, ModelSpec], settings: Settings, client: AsyncQdrantClient
) -> SearchDeps:
    em, rm = models[v.embed], models[v.reranker]
    return SearchDeps(
        client=client,
        collection=v.collection(settings.qdrant_collection),
        embedder=TeiEmbedder(
            em.url(), model=em.model, query_prefix=em.query_prefix, document_prefix=em.document_prefix
        ),
        reranker=TeiReranker(rm.url(), model=rm.model, timeout_sec=settings.rerank_timeout_sec)
        if v.rerank
        else None,
        sparse_factory=lambda: SparseEncoder(
            settings.sudachi_mode, avgdl=settings.bm25_avgdl, en_stem=v.sparse_en_stem
        ),
        config=v.config(),
    )


async def build_collection(
    session: AsyncSession,
    v: Variant,
    models: dict[str, ModelSpec],
    settings: Settings,
    client: AsyncQdrantClient,
    kb_id: str,
    batch: int = 64,
) -> int:
    """Postgres の子チャンク（本文・文脈）から variant 用コレクションを作る。再解析・再文脈付与はしない。"""
    if not v.own_collection:
        return 0
    em = models[v.embed]
    embedder = TeiEmbedder(em.url(), model=em.model, document_prefix=em.document_prefix)
    encoder = SparseEncoder(settings.sudachi_mode, avgdl=settings.bm25_avgdl, en_stem=v.sparse_en_stem)
    index = QdrantIndex(client, v.collection(settings.qdrant_collection))
    await index.ensure_collection(await embedder.dimension())
    hashes = sorted(
        set(
            await session.scalars(
                select(Document.content_hash).where(Document.kb_id == kb_id, Document.deleted_at.is_(None))
            )
        )
    )
    total = 0
    for h in hashes:
        chunks = list(
            await session.scalars(select(Chunk).where(Chunk.content_hash == h).order_by(Chunk.ordinal))
        )
        if not chunks:
            continue
        docs, kbs = await live_refs(session, h)
        await index.delete_content(h)
        for i in range(0, len(chunks), batch):
            part = chunks[i : i + batch]
            bodies = [f"{c.context}\n\n{c.text}" if v.context and c.context else c.text for c in part]
            dense = await embedder.embed(bodies)
            await index.upsert(
                [
                    IndexPoint(
                        id=c.id,
                        dense=d,
                        sparse=encoder.encode_document(b),
                        payload={
                            "content_hash": h,
                            "section_id": str(c.section_id),
                            "document_ids": docs,
                            "kb_ids": kbs,
                            "block_type": c.block_type,
                            "page_start": c.page_start,
                            "heading_path": c.heading_path,
                        },
                    )
                    for c, b, d in zip(part, bodies, dense, strict=True)
                ]
            )
            total += len(part)
    return total


async def collection_drift(
    client: AsyncQdrantClient, collection: str, kb_id: str, chunk_ids: set[uuid.UUID]
) -> tuple[int, int]:
    """(DB にあるがコレクションに無い点の数, コレクションにあるが DB に無い古い点の数)。KB の点だけを見る。"""
    flt = qm.Filter(must=[qm.FieldCondition(key="kb_ids", match=qm.MatchAny(any=[kb_id]))])
    seen: set[uuid.UUID] = set()
    offset = None
    while True:
        points, offset = await client.scroll(
            collection, scroll_filter=flt, limit=1000, offset=offset, with_payload=False, with_vectors=False
        )
        seen |= {uuid.UUID(str(p.id)) for p in points}
        if offset is None:
            break
    return len(chunk_ids - seen), len(seen - chunk_ids)


async def kb_chunk_ids(session: AsyncSession, kb_id: str) -> set[uuid.UUID]:
    hashes = select(Document.content_hash).where(Document.kb_id == kb_id, Document.deleted_at.is_(None))
    return set(await session.scalars(select(Chunk.id).where(Chunk.content_hash.in_(hashes))))
