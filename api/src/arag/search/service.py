"""検索関数（specs/004-retrieval design §1）。

scope → クエリの符号化 → Qdrant（サーバ側融合）→ 本文取得 → must_contain → rerank。
rerank・dense の失敗は縮退して続行し、Qdrant の失敗だけを 503 にする（R10・R11）。
"""

import asyncio
import threading
import time
import unicodedata
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arag.auth.principal import Principal
from arag.db.models import Chunk, Document, KnowledgeBase, Section
from arag.errors import ApiError
from arag.ingest.embedder import Embedder, EmbedError
from arag.ingest.index import DENSE, SPARSE
from arag.ingest.sparse import SparseEncoder, SparseVector
from arag.logging import get_logger
from arag.search.config import SearchConfig
from arag.search.hooks import candidates_hook, stage_hook
from arag.search.query import QdrantQuery, build_filter, build_query
from arag.search.rerank import Reranker, RerankError
from arag.search.schemas import PathHit, SearchHit, SearchRequest, SearchResult, SearchTrace, StageTiming
from arag.search.scope import Scope, resolve_scope

log = get_logger("arag.search")


@dataclass
class SearchDeps:
    client: AsyncQdrantClient
    collection: str
    embedder: Embedder | None
    reranker: Reranker | None
    sparse_factory: Callable[[], SparseEncoder]
    config: SearchConfig = field(default_factory=SearchConfig)


_local = threading.local()


def _encode_sparse(factory: Callable[[], SparseEncoder], text: str) -> SparseVector:
    # Sudachi のトークナイザはスレッド安全でないので、スレッドごとに作って使い回す
    cache: dict[int, SparseEncoder] = getattr(_local, "encoders", None) or {}
    _local.encoders = cache
    enc = cache.get(id(factory))
    if enc is None:
        enc = cache[id(factory)] = factory()
    return enc.encode_query(text)


class _Clock:
    def __init__(self) -> None:
        self.stages: list[StageTiming] = []
        self._t = time.perf_counter()

    def lap(self, name: Any, count: int | None = None) -> None:
        now = time.perf_counter()
        stage = StageTiming(name=name, ms=round((now - self._t) * 1000), count=count)
        self.stages.append(stage)
        self._t = now
        if (hook := stage_hook.get()) is not None:
            hook(stage)


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s).casefold()


@dataclass(slots=True)
class _Cand:
    chunk_id: uuid.UUID
    fused: float
    score: float = 0.0
    chunk: Chunk | None = None
    doc: tuple[uuid.UUID, str, uuid.UUID] | None = None  # document_id, name, kb_id


async def search(
    session: AsyncSession,
    deps: SearchDeps,
    principal: Principal,
    req: SearchRequest,
    *,
    config: SearchConfig | None = None,
) -> SearchResult:
    cfg = config or deps.config
    clock = _Clock()
    trace = SearchTrace()
    degraded: list[Any] = []
    scope = await resolve_scope(session, principal, req)
    clock.lap("scope", len(scope.kb_ids))
    if scope.empty:
        return SearchResult(hits=[], trace=SearchTrace(stages=clock.stages), degraded=[])

    # ---- クエリの符号化
    mode = req.mode
    dense: list[float] | None = None
    if mode in ("hybrid", "dense"):
        try:
            if deps.embedder is None:
                raise EmbedError("埋め込みサービスが設定されていません")
            dense = (await deps.embedder.embed_query([req.query]))[0]
        except EmbedError as e:
            if mode == "dense":
                raise ApiError(503, "embed_unavailable", "埋め込みサービスに接続できません") from e
            log.warning("search_dense_degraded", error=str(e))
            degraded.append("dense")
            mode = "keyword"
    sparse = None
    if mode in ("hybrid", "keyword"):
        sparse = await asyncio.to_thread(_encode_sparse, deps.sparse_factory, req.query)
    clock.lap("embed")

    # ---- Qdrant（1 往復）
    flt = build_filter(scope.kb_ids, scope.document_ids, req.block_types)
    q = build_query(mode, dense, sparse, flt, req.candidate_k, cfg)
    try:
        points = await _query(deps, q, req, mode, dense, sparse, flt, trace)
    except UnexpectedResponse as e:
        if e.status_code == 404:  # まだ何も入庫されていない
            points = []
        else:
            raise ApiError(503, "search_unavailable", "検索サービスに接続できません") from e
    except Exception as e:
        log.error("search_qdrant_failed", error=f"{type(e).__name__}: {e}")
        raise ApiError(503, "search_unavailable", "検索サービスに接続できません") from e
    clock.lap("query", len(points))

    # ---- 本文と見える文書
    cands = [_Cand(chunk_id=uuid.UUID(str(p.id)), fused=float(p.score)) for p in points]
    cands = await _hydrate(session, scope, cands)
    if req.must_contain:
        terms = [_norm(t) for t in req.must_contain]
        # 見出し（「第5条（異常時の対応）」など）にだけ出る語もあるので、見出しと本文の両方で確かめる
        cands = [
            c
            for c in cands
            if c.chunk and all(t in _norm(f"{c.chunk.heading_path or ''}\n{c.chunk.text}") for t in terms)
        ]
    if (cand_hook := candidates_hook.get()) is not None:
        cand_hook(
            [
                {"title": c.doc[1], "heading": c.chunk.heading_path, "score": round(c.fused, 4)}
                for c in cands
                if c.chunk is not None and c.doc is not None
            ]
        )
    clock.lap("hydrate", len(cands))

    # ---- rerank（失敗したら融合順のまま）
    for c in cands:
        c.score = c.fused
    if cfg.rerank_enabled and deps.reranker is not None and cands:
        inputs = [_rerank_text(c.chunk, cfg) for c in cands if c.chunk]
        try:
            scores = await deps.reranker.rerank(req.query, inputs)
            for c, s in zip(cands, scores, strict=True):
                c.score = s
            clock.lap("rerank", len(cands))
        except RerankError as e:
            log.warning("search_rerank_degraded", error=str(e))
            degraded.append("rerank")
            clock.lap("rerank", 0)
    # 同点は chunk_id 順（R12）
    cands.sort(key=lambda c: (-c.score, str(c.chunk_id)))
    top = cands[: req.top_k]

    hits = [_to_hit(i, c) for i, c in enumerate(top, start=1)]
    if req.include_section and hits:
        await _attach_sections(session, hits)
        clock.lap("section", len(hits))
    trace.stages = clock.stages
    return SearchResult(hits=hits, trace=trace, degraded=degraded)


async def _query(
    deps: SearchDeps,
    q: QdrantQuery,
    req: SearchRequest,
    mode: str,
    dense: list[float] | None,
    sparse: SparseVector | None,
    flt: models.Filter,
    trace: SearchTrace,
) -> list[models.ScoredPoint]:
    if not req.debug:
        res = await deps.client.query_points(
            deps.collection,
            query=q.query,
            using=q.using,
            prefetch=q.prefetch,
            query_filter=q.filter,
            limit=req.candidate_k,
            with_payload=False,
        )
        return res.points
    # debug: 融合・dense のみ・sparse のみを 1 往復で（R15）
    reqs = [q.request(req.candidate_k)]
    if dense is not None:
        reqs.append(models.QueryRequest(query=dense, using=DENSE, filter=flt, limit=req.candidate_k))
    if sparse is not None:
        reqs.append(
            models.QueryRequest(
                query=models.SparseVector(indices=sparse.indices, values=sparse.values),
                using=SPARSE,
                filter=flt,
                limit=req.candidate_k,
            )
        )
    results = await deps.client.query_batch_points(deps.collection, requests=reqs)
    rest = iter(results[1:])
    if dense is not None:
        trace.dense = [PathHit(chunk_id=uuid.UUID(str(p.id)), score=p.score) for p in next(rest).points]
    if sparse is not None:
        trace.sparse = [PathHit(chunk_id=uuid.UUID(str(p.id)), score=p.score) for p in next(rest).points]
    return results[0].points


async def _hydrate(session: AsyncSession, scope: Scope, cands: list[_Cand]) -> list[_Cand]:
    if not cands:
        return []
    chunks = {
        c.id: c for c in await session.scalars(select(Chunk).where(Chunk.id.in_([x.chunk_id for x in cands])))
    }
    hashes = {c.content_hash for c in chunks.values()}
    q = (
        select(Document.id, Document.content_hash, Document.filename, Document.kb_id, KnowledgeBase.kind)
        .join(KnowledgeBase, KnowledgeBase.id == Document.kb_id)
        .where(
            Document.content_hash.in_(hashes),
            Document.deleted_at.is_(None),
            Document.kb_id.in_([uuid.UUID(k) for k in scope.kb_ids]),
        )
        .order_by(Document.created_at, Document.id)
    )
    if scope.document_ids is not None:
        q = q.where(Document.id.in_([uuid.UUID(d) for d in scope.document_ids]))
    # 同じ内容が複数あれば個人 KB の文書を優先し、次に古いもの（R4）
    visible: dict[str, tuple[uuid.UUID, str, uuid.UUID]] = {}
    personal: set[str] = set()
    for did, h, name, kb_id, kind in (await session.execute(q)).all():
        if h not in visible or (kind == "personal" and h not in personal):
            visible[h] = (did, name, kb_id)
            if kind == "personal":
                personal.add(h)
    out: list[_Cand] = []
    for c in cands:
        ch = chunks.get(c.chunk_id)
        if ch is None or ch.content_hash not in visible:
            continue  # 同期の遅れ・再索引中の点は捨てる
        c.chunk = ch
        c.doc = visible[ch.content_hash]
        out.append(c)
    return out


def _rerank_text(chunk: Chunk | None, cfg: SearchConfig) -> str:
    assert chunk is not None
    text = chunk.text
    if cfg.rerank_input != "text" and chunk.context:
        text = f"{chunk.context}\n\n{text}"
    if cfg.rerank_input == "heading+context+text" and chunk.heading_path:
        text = f"{chunk.heading_path}\n{text}"
    return text[: cfg.rerank_max_chars] if cfg.rerank_max_chars > 0 else text


def _to_hit(rank: int, c: _Cand) -> SearchHit:
    ch, doc = c.chunk, c.doc
    assert ch is not None and doc is not None
    return SearchHit(
        rank=rank,
        chunk_id=ch.id,
        document_id=doc[0],
        document_name=doc[1],
        kb_id=doc[2],
        section_id=ch.section_id,
        heading_path=ch.heading_path,
        page_start=ch.page_start,
        page_end=ch.page_end,
        block_type=ch.block_type,
        text=ch.text,
        context=ch.context,
        boxes=ch.boxes,
        score=c.score,
        fused_score=c.fused,
    )


async def _attach_sections(session: AsyncSession, hits: list[SearchHit]) -> None:
    ids = {h.section_id for h in hits}
    texts = dict((await session.execute(select(Section.id, Section.text).where(Section.id.in_(ids)))).all())
    seen: set[uuid.UUID] = set()
    for h in hits:
        if h.section_id not in seen:
            h.section_text = texts.get(h.section_id)
            seen.add(h.section_id)


def build_search_deps(settings: Any, client: AsyncQdrantClient) -> SearchDeps:
    """Settings から本番の依存を作る（埋め込み・rerank が未設定ならそれなしで縮退動作。specs/016）。"""
    from arag.inference import build_embedder, build_reranker

    return SearchDeps(
        client=client,
        collection=settings.qdrant_collection,
        # 検索は応答を待たせないので、文書の埋め込みより短い時間・少ない再試行にする
        embedder=build_embedder(settings, timeout_sec=settings.rerank_timeout_sec, max_attempts=2),
        reranker=build_reranker(settings),
        sparse_factory=lambda: SparseEncoder(
            settings.sudachi_mode, avgdl=settings.bm25_avgdl, en_stem=settings.sparse_en_stem
        ),
        config=SearchConfig.from_settings(settings),
    )
