"""検索の純粋な部品（specs/004-retrieval B1・B3・B4）。"""

import json

import httpx
import pytest
from pydantic import ValidationError
from qdrant_client import models

from arag.ingest.sparse import SparseVector
from arag.search.config import SearchConfig
from arag.search.query import build_filter, build_query
from arag.search.rerank import RerankError, TeiReranker
from arag.search.schemas import SearchRequest

# ---- B1 要求の検証


def test_request_validation() -> None:
    assert SearchRequest(query="  MX-17  ").query == "MX-17"
    for bad in (
        {"query": "  "},
        {"query": "あ" * 1001},
        {"query": "q", "top_k": 0},
        {"query": "q", "top_k": 51},
        {"query": "q", "top_k": 10, "candidate_k": 5},
    ):
        with pytest.raises(ValidationError):
            SearchRequest(**bad)  # type: ignore[arg-type]
    assert SearchRequest(query="q", must_contain=[" ", ""]).must_contain is None


# ---- B3 Qdrant 要求の組み立て


def test_filter_has_kb_and_optional_document_and_block_type() -> None:
    f = build_filter(["k1", "k2"], None, None)
    assert [c.key for c in f.must] == ["kb_ids"]  # type: ignore[union-attr]
    f = build_filter(["k1"], ["d1"], ["table"])
    keys = [c.key for c in f.must]  # type: ignore[union-attr]
    assert keys == ["kb_ids", "document_ids", "block_type"]
    assert f.must[1].match.any == ["d1"]  # type: ignore[index,union-attr]


DENSE = [0.1, 0.2]
SPARSE = SparseVector(indices=[1, 5], values=[1.0, 1.0])


def test_hybrid_rrf_with_weights() -> None:
    q = build_query(
        "hybrid", DENSE, SPARSE, build_filter(["k"], None, None), 50, SearchConfig(weights=(2.0, 1.0))
    )
    assert [p.using for p in q.prefetch] == ["dense", "bm25"]  # type: ignore[union-attr]
    assert all(p.limit == 50 for p in q.prefetch)  # type: ignore[union-attr]
    assert isinstance(q.query, models.RrfQuery)
    assert q.query.rrf.k == 60 and q.query.rrf.weights == [2.0, 1.0]
    assert q.filter is None  # フィルタは prefetch 側に付ける


def test_hybrid_dbsf() -> None:
    q = build_query("hybrid", DENSE, SPARSE, build_filter(["k"], None, None), 50, SearchConfig(fusion="dbsf"))
    assert isinstance(q.query, models.FusionQuery) and q.query.fusion == models.Fusion.DBSF


def test_single_paths() -> None:
    f = build_filter(["k"], None, None)
    d = build_query("dense", DENSE, None, f, 30, SearchConfig())
    assert d.using == "dense" and d.query == DENSE and d.prefetch is None and d.filter == f
    k = build_query("keyword", None, SPARSE, f, 30, SearchConfig())
    assert k.using == "bm25" and isinstance(k.query, models.SparseVector)


# ---- B4 TEI rerank


def _reranker(handler, **kw) -> TeiReranker:  # type: ignore[no-untyped-def]
    return TeiReranker("http://tei", transport=httpx.MockTransport(handler), backoff_sec=0, **kw)


async def test_rerank_batches_and_restores_order() -> None:
    sizes: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        assert body["raw_scores"] is False and body["truncate"] is True and body["query"] == "q"
        sizes.append(len(body["texts"]))
        # TEI はスコア降順で返す
        res = [{"index": i, "score": float(t)} for i, t in enumerate(body["texts"])]
        return httpx.Response(200, json=sorted(res, key=lambda r: -r["score"]))

    texts = [str(i / 100) for i in range(70)]
    scores = await _reranker(handler, batch_size=32).rerank("q", texts)
    assert sizes == [32, 32, 6]
    assert scores == [i / 100 for i in range(70)]


async def test_rerank_retries_then_fails() -> None:
    calls = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, text="busy")

    with pytest.raises(RerankError):
        await _reranker(handler, max_attempts=3).rerank("q", ["a"])
    assert calls == 3


async def test_rerank_empty_input_makes_no_request() -> None:
    def handler(req: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError

    assert await _reranker(handler).rerank("q", []) == []


def test_rerank_text_max_chars() -> None:
    """rerank 入力の文字数上限（長い英語文書で所要時間を抑える）。0 は上限なし。"""
    from types import SimpleNamespace

    from arag.search.service import _rerank_text

    ch = SimpleNamespace(heading_path="", context="文脈", text="x" * 100)
    assert _rerank_text(ch, SearchConfig()) == "文脈\n\n" + "x" * 100  # type: ignore[arg-type]
    capped = _rerank_text(ch, SearchConfig(rerank_max_chars=10))  # type: ignore[arg-type]
    assert capped == "文脈\n\nxxxxxx" and len(capped) == 10
    assert _rerank_text(ch, SearchConfig(rerank_input="text", rerank_max_chars=5)) == "xxxxx"  # type: ignore[arg-type]


def test_rerank_text_with_heading() -> None:
    """見出しパスも渡す（本文に固有名が無い英語資料を日本語の問いで拾うため。specs/019）。"""
    from types import SimpleNamespace

    from arag.search.service import _rerank_text

    cfg = SearchConfig(rerank_input="heading+context+text")
    ch = SimpleNamespace(heading_path="Pump Procedure — Penang > 2. Records", context="文脈", text="本文")
    assert _rerank_text(ch, cfg) == "Pump Procedure — Penang > 2. Records\n文脈\n\n本文"  # type: ignore[arg-type]
    bare = SimpleNamespace(heading_path="", context="", text="本文")
    assert _rerank_text(bare, cfg) == "本文"  # type: ignore[arg-type]


def test_rerank_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    from arag.search.service import build_search_deps
    from arag.settings import Settings

    s = Settings(_env_file=None, tei_rerank_url="http://tei", rerank_max_chars=1500)  # type: ignore[call-arg]
    assert s.rerank_model == "cl-nagoya/ruri-v3-reranker-310m"
    assert SearchConfig.from_settings(s).rerank_max_chars == 1500
    deps = build_search_deps(s, client=None)  # type: ignore[arg-type]
    assert deps.reranker is not None and deps.reranker.model == "cl-nagoya/ruri-v3-reranker-310m"
