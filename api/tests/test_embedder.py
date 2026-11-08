"""TEI クライアント（specs/003-ingestion D7）。"""

import json

import httpx
import pytest

from arag.ingest.embedder import EmbedError, TeiEmbedder


def _embedder(handler, **kw) -> TeiEmbedder:  # type: ignore[no-untyped-def]
    return TeiEmbedder("http://tei", model="m", transport=httpx.MockTransport(handler), backoff_sec=0, **kw)


async def test_batches_split_and_order_kept() -> None:
    sizes: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        inputs = json.loads(req.content)["inputs"]
        sizes.append(len(inputs))
        return httpx.Response(200, json=[[float(len(t)), 0.0] for t in inputs])

    texts = ["a" * n for n in range(1, 8)]
    out = await _embedder(handler, batch_size=3).embed(texts)
    assert sizes == [3, 3, 1]
    assert [v[0] for v in out] == [1, 2, 3, 4, 5, 6, 7]


async def test_retries_on_503_then_succeeds() -> None:
    calls = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, json=[[1.0, 2.0, 3.0]])

    e = _embedder(handler)
    assert await e.dimension() == 3
    assert calls == 3


async def test_gives_up_after_max_attempts() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(EmbedError, match="ConnectError"):
        await _embedder(handler, max_attempts=2).embed(["x"])


async def test_4xx_is_not_retried() -> None:
    calls = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(413, text="too large")

    with pytest.raises(EmbedError, match="413"):
        await _embedder(handler).embed(["x"])
    assert calls == 1


async def test_document_and_query_prefixes() -> None:
    seen: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        inputs = json.loads(req.content)["inputs"]
        seen.extend(inputs)
        return httpx.Response(200, json=[[1.0] for _ in inputs])

    e = _embedder(handler, document_prefix="検索文書: ", query_prefix="検索クエリ: ")
    await e.embed(["本文"])
    await e.embed_query(["質問"])
    assert seen == ["検索文書: 本文", "検索クエリ: 質問"]
    # 既定は接頭辞なし（bge-m3）
    seen.clear()
    await _embedder(handler).embed_query(["質問"])
    assert seen == ["質問"]
