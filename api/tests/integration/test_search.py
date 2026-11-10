"""検索関数と /v1/search（specs/004-retrieval B2・B5〜B8、E4）。

dense は偽の埋め込み（ハッシュ）なので意味を持たない。範囲・縮退・順序の検証は keyword（Sudachi BM25）で行う。
"""

import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.auth.principal import Principal
from arag.errors import ApiError
from arag.ingest.embedder import EmbedError
from arag.ingest.index import QdrantIndex
from arag.ingest.pipeline import run_ingest
from arag.ingest.sparse import SparseEncoder
from arag.search.config import SearchConfig
from arag.search.rerank import RerankError
from arag.search.schemas import SearchRequest
from arag.search.service import SearchDeps, search

from .conftest import ADMIN, ALICE, BOB
from .ingest_helpers import FakeEmbedder, make_deps
from .test_ingest import _personal, _upload

pytestmark = pytest.mark.integration

DOC_A = "# 点検\n\n## 判定\n\nMX-17 は即時停止を推奨する。\n\n## 補足\n\nMX-17 の部品は翌営業日に到着する。\n"
DOC_ORG = "# 規程\n\n## 保存\n\nログは 180 日保存する。MX-17 の記録も含む。\n"
DOC_BOB = "# 私的メモ\n\nMX-17 の秘密メモ。\n"
DOC_ARCH = "# 旧規程\n\nMX-17 は旧規程では監視継続とする。\n"
DOC_TRASH = "# 削除予定\n\nMX-17 の古い記録。\n"

ALICE_P = Principal(user_id="alice")


class FakeReranker:
    """クエリの語を本文に多く含むほど高い。fail=True なら常に失敗。"""

    model = "fake-rerank"

    def __init__(self, fail: bool = False, constant: float | None = None) -> None:
        self.fail = fail
        self.constant = constant
        self.inputs: list[str] = []

    async def rerank(self, query: str, texts: Sequence[str]) -> list[float]:
        if self.fail:
            raise RerankError("偽の失敗")
        self.inputs = list(texts)
        if self.constant is not None:
            return [self.constant] * len(texts)
        words = query.split()
        return [sum(w in t for w in words) / (len(words) or 1) for t in texts]


class FailingEmbedder(FakeEmbedder):
    async def embed_query(self, texts: Sequence[str]) -> list[list[float]]:
        raise EmbedError("偽の失敗")


@dataclass
class World:
    personal: str
    org: str
    archived: str
    doc_a: str
    doc_org: str
    doc_arch: str
    doc_shared_org: str
    doc_shared_personal: str


@pytest.fixture
async def world(
    make_client: Callable[..., Awaitable[httpx.AsyncClient]],
    sessionmaker: async_sessionmaker[AsyncSession],
    qdrant_index: QdrantIndex,
    storage_root: str,
) -> World:
    client = await make_client(index=qdrant_index)
    deps = make_deps(sessionmaker, storage_root, qdrant_index)

    async def up(kb: str, name: str, body: str, headers: dict[str, str]) -> str:
        item = (await _upload(client, kb, [(name, body.encode())], headers=headers)).json()["items"][0]
        if item["job_id"]:
            assert await run_ingest(uuid.UUID(item["job_id"]), deps) == "ready"
        return str(item["document_id"])

    personal = await _personal(client, ALICE)
    bob = await _personal(client, BOB)
    org = (await client.post("/v1/kbs", json={"name": "全社"}, headers=ADMIN)).json()["id"]
    arch = (await client.post("/v1/kbs", json={"name": "旧全社"}, headers=ADMIN)).json()["id"]
    doc_a = await up(personal, "a.md", DOC_A, ALICE)
    doc_org = await up(org, "org.md", DOC_ORG, ADMIN)
    await up(bob, "bob.md", DOC_BOB, BOB)
    doc_arch = await up(arch, "arch.md", DOC_ARCH, ADMIN)
    trash = await up(personal, "trash.md", DOC_TRASH, ALICE)
    # 同じ内容を全社 KB（先）と個人 KB（後）に置く
    shared = "# 共有\n\nGammaVision は海外リージョンのため不採用。\n"
    doc_shared_org = await up(org, "shared-org.md", shared, ADMIN)
    doc_shared_personal = await up(personal, "shared-mine.md", shared, ALICE)
    assert (await client.post(f"/v1/kbs/{arch}/archive", headers=ADMIN)).status_code == 200
    assert (await client.delete(f"/v1/documents/{trash}", headers=ALICE)).status_code == 204
    return World(personal, org, arch, doc_a, doc_org, doc_arch, doc_shared_org, doc_shared_personal)


def _deps(qdrant_index: QdrantIndex, **kw: object) -> SearchDeps:
    return SearchDeps(
        client=qdrant_index.client,
        collection=qdrant_index.alias,
        embedder=kw.pop("embedder", FakeEmbedder()),  # type: ignore[arg-type]
        reranker=kw.pop("reranker", FakeReranker()),  # type: ignore[arg-type]
        sparse_factory=lambda: SparseEncoder("B"),
        **kw,  # type: ignore[arg-type]
    )


async def _run(sm: async_sessionmaker[AsyncSession], deps: SearchDeps, p: Principal = ALICE_P, **req: object):  # type: ignore[no-untyped-def]
    async with sm() as s:
        return await search(s, deps, p, SearchRequest(**{"mode": "keyword", "top_k": 20, **req}))  # type: ignore[arg-type]


def _docs(res) -> set[str]:  # type: ignore[no-untyped-def]
    return {str(h.document_id) for h in res.hits}


async def test_scope_personal_org_archived_trash(
    world: World, sessionmaker: async_sessionmaker[AsyncSession], qdrant_index: QdrantIndex
) -> None:
    deps = _deps(qdrant_index)
    res = await _run(sessionmaker, deps, query="MX-17")
    # 自分の個人 KB と全社 KB だけ。他人の個人 KB・アーカイブ・ごみ箱は出ない（E4）
    assert _docs(res) == {world.doc_a, world.doc_org}
    res = await _run(sessionmaker, deps, query="MX-17", include_archived=True)
    assert _docs(res) == {world.doc_a, world.doc_org, world.doc_arch}
    # 明示した KB はアーカイブ済みでも対象、見えない KB の ID は黙って除く
    res = await _run(sessionmaker, deps, query="MX-17", kb_ids=[world.archived, str(uuid.uuid4())])
    assert _docs(res) == {world.doc_arch}
    # 他人（bob）からは alice の個人 KB が見えない
    res = await _run(sessionmaker, deps, Principal(user_id="bob"), query="MX-17", kb_ids=[world.personal])
    assert res.hits == []
    # 文書の指定
    res = await _run(sessionmaker, deps, query="MX-17", document_ids=[world.doc_org])
    assert _docs(res) == {world.doc_org}
    res = await _run(sessionmaker, deps, query="MX-17", document_ids=[str(uuid.uuid4())])
    assert res.hits == []


async def test_shared_content_points_to_personal_document(
    world: World, sessionmaker: async_sessionmaker[AsyncSession], qdrant_index: QdrantIndex
) -> None:
    res = await _run(sessionmaker, _deps(qdrant_index), query="GammaVision")
    assert len(res.hits) == 1
    assert str(res.hits[0].document_id) == world.doc_shared_personal
    # 全社 KB だけに絞ればそちらの文書を指す
    res = await _run(sessionmaker, _deps(qdrant_index), query="GammaVision", kb_ids=[world.org])
    assert str(res.hits[0].document_id) == world.doc_shared_org


async def test_must_contain_and_rerank_input(
    world: World, sessionmaker: async_sessionmaker[AsyncSession], qdrant_index: QdrantIndex
) -> None:
    rr = FakeReranker()
    res = await _run(
        sessionmaker, _deps(qdrant_index, reranker=rr), query="MX-17", must_contain=["ｍｘ－17", "停止"]
    )
    assert [h.text for h in res.hits] == ["MX-17 は即時停止を推奨する。"]
    # 見出し（点検 > 判定）にだけある語でも一致とみなす
    by_heading = await _run(
        sessionmaker, _deps(qdrant_index), query="MX-17", must_contain=["判定", "即時停止"]
    )
    assert [h.text for h in by_heading.hits] == ["MX-17 は即時停止を推奨する。"]
    # rerank には文脈 + 本文を渡す（既定）
    assert rr.inputs[0].endswith("MX-17 は即時停止を推奨する。") and rr.inputs[0] != res.hits[0].text
    rr2 = FakeReranker()
    cfg = SearchConfig(rerank_input="text")
    await _run(
        sessionmaker, _deps(qdrant_index, reranker=rr2, config=cfg), query="MX-17", must_contain=["停止"]
    )
    assert rr2.inputs == ["MX-17 は即時停止を推奨する。"]


async def test_rerank_and_dense_degrade(
    world: World, sessionmaker: async_sessionmaker[AsyncSession], qdrant_index: QdrantIndex
) -> None:
    res = await _run(sessionmaker, _deps(qdrant_index, reranker=FakeReranker(fail=True)), query="MX-17")
    assert res.degraded == ["rerank"] and res.hits
    assert all(h.score == h.fused_score for h in res.hits)
    # hybrid で埋め込みが落ちたら keyword で続行
    deps = _deps(qdrant_index, embedder=FailingEmbedder())
    res = await _run(sessionmaker, deps, query="MX-17", mode="hybrid")
    assert res.degraded == ["dense"] and _docs(res) == {world.doc_a, world.doc_org}
    with pytest.raises(ApiError) as e:
        await _run(sessionmaker, deps, query="MX-17", mode="dense")
    assert e.value.status == 503


async def test_hybrid_and_dense_modes_return_hits(
    world: World, sessionmaker: async_sessionmaker[AsyncSession], qdrant_index: QdrantIndex
) -> None:
    for mode in ("hybrid", "dense"):
        res = await _run(sessionmaker, _deps(qdrant_index), query="MX-17", mode=mode, top_k=3)
        assert 0 < len(res.hits) <= 3
        assert [h.rank for h in res.hits] == list(range(1, len(res.hits) + 1))
    res = await _run(
        sessionmaker, _deps(qdrant_index, config=SearchConfig(fusion="dbsf")), query="MX-17", mode="hybrid"
    )
    assert res.hits


async def test_order_is_deterministic_on_ties(
    world: World, sessionmaker: async_sessionmaker[AsyncSession], qdrant_index: QdrantIndex
) -> None:
    deps = _deps(qdrant_index, reranker=FakeReranker(constant=0.5))
    a = await _run(sessionmaker, deps, query="MX-17")
    b = await _run(sessionmaker, deps, query="MX-17")
    ids = [str(h.chunk_id) for h in a.hits]
    assert ids == [str(h.chunk_id) for h in b.hits] == sorted(ids)


async def test_include_section_once_per_section_and_trace(
    world: World, sessionmaker: async_sessionmaker[AsyncSession], qdrant_index: QdrantIndex
) -> None:
    res = await _run(sessionmaker, _deps(qdrant_index), query="MX-17", include_section=True, debug=True)
    seen: set[uuid.UUID] = set()
    for h in res.hits:
        if h.section_id in seen:
            assert h.section_text is None
        else:
            assert h.section_text and h.text in h.section_text
            seen.add(h.section_id)
    names = [s.name for s in res.trace.stages]
    assert names[:4] == ["scope", "embed", "query", "hydrate"] and "section" in names
    # debug（keyword）は sparse 経路の一覧だけ
    assert res.trace.sparse and res.trace.dense is None
    res = await _run(sessionmaker, _deps(qdrant_index), query="MX-17", mode="hybrid", debug=True)
    assert res.trace.dense and res.trace.sparse


async def test_search_api_admin_only(
    world: World,
    make_client: Callable[..., Awaitable[httpx.AsyncClient]],
    qdrant_index: QdrantIndex,
) -> None:
    client = await make_client(index=qdrant_index, search_deps=_deps(qdrant_index))
    body = {"query": "MX-17", "mode": "keyword", "kb_ids": [world.org]}
    assert (await client.post("/v1/search", json=body, headers=ALICE)).status_code == 403
    res = await client.post("/v1/search", json=body, headers=ADMIN)
    assert res.status_code == 200
    assert {h["document_id"] for h in res.json()["hits"]} == {world.doc_org}
    bad = await client.post("/v1/search", json={"query": " "}, headers=ADMIN)
    assert bad.status_code == 422
