"""推論の部品を設定で選ぶ（specs/016-inference-modules）。"""

import json

import httpx
import pytest

from arag.inference import (
    build_embedder,
    build_figure_describer,
    build_reranker,
    describe_inference,
    inference_checks,
)
from arag.ingest.embedder import EmbedError, OpenAIEmbedder, TeiEmbedder
from arag.search.rerank import CohereReranker, RerankError, TeiReranker
from arag.settings import Settings


def _settings(**kw: object) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[call-arg]


# ---- A1 OpenAI 互換の埋め込み


def _openai_embedder(handler, **kw) -> OpenAIEmbedder:  # type: ignore[no-untyped-def]
    return OpenAIEmbedder(
        "https://api.example.com/v1",
        model="text-embedding-3-small",
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
        backoff_sec=0,
        **kw,
    )


async def test_openai_embedder_request_and_order() -> None:
    seen: list[dict[str, object]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/v1/embeddings"
        assert req.headers["authorization"] == "Bearer sk-test"
        body = json.loads(req.content)
        seen.append(body)
        # index の逆順で返しても元の順に戻す
        data = [{"index": i, "embedding": [float(len(t)), 1.0]} for i, t in enumerate(body["input"])]
        return httpx.Response(200, json={"data": list(reversed(data))})

    e = _openai_embedder(handler, batch_size=2, document_prefix="doc: ", dimensions=256)
    out = await e.embed(["a", "bb", "ccc"])
    assert [v[0] for v in out] == [6.0, 7.0, 8.0]  # "doc: " + 本文の長さ
    assert [len(b["input"]) for b in seen] == [2, 1]  # type: ignore[arg-type]
    assert seen[0]["model"] == "text-embedding-3-small" and seen[0]["dimensions"] == 256
    assert seen[0]["encoding_format"] == "float"


async def test_openai_embedder_omits_dimensions_and_auth_when_unset() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert "authorization" not in req.headers
        body = json.loads(req.content)
        assert "dimensions" not in body
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]})

    e = OpenAIEmbedder("http://vllm/v1", model="m", transport=httpx.MockTransport(handler), backoff_sec=0)
    assert await e.dimension() == 3


async def test_openai_embedder_retries_then_fails_on_4xx() -> None:
    calls = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, text="slow down")
        return httpx.Response(401, text="bad key")

    with pytest.raises(EmbedError, match="401"):
        await _openai_embedder(handler).embed(["a"])
    assert calls == 2


async def test_openai_embedder_count_mismatch() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    with pytest.raises(EmbedError, match="件数"):
        await _openai_embedder(handler).embed(["a"])


# ---- A2 Cohere 互換の並べ替え


def _cohere(handler, **kw) -> CohereReranker:  # type: ignore[no-untyped-def]
    return CohereReranker(
        "https://api.example.com/v1",
        model="rerank-v3.5",
        api_key="key",
        transport=httpx.MockTransport(handler),
        backoff_sec=0,
        **kw,
    )


@pytest.mark.parametrize("field", ["results", "data"])
async def test_cohere_reranker_restores_order(field: str) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/v1/rerank"
        assert req.headers["authorization"] == "Bearer key"
        body = json.loads(req.content)
        assert body["model"] == "rerank-v3.5" and body["query"] == "q"
        assert body["top_n"] == len(body["documents"])
        res = [{"index": i, "relevance_score": float(t)} for i, t in enumerate(body["documents"])]
        return httpx.Response(200, json={field: sorted(res, key=lambda r: -r["relevance_score"])})

    texts = [str(i / 10) for i in range(5)]
    assert await _cohere(handler).rerank("q", texts) == [0.0, 0.1, 0.2, 0.3, 0.4]


async def test_cohere_reranker_batches_and_errors() -> None:
    sizes: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        docs = json.loads(req.content)["documents"]
        sizes.append(len(docs))
        return httpx.Response(
            200, json={"results": [{"index": i, "relevance_score": 0.5} for i in range(len(docs))]}
        )

    assert len(await _cohere(handler, batch_size=4).rerank("q", ["x"] * 9)) == 9
    assert sizes == [4, 4, 1]

    def short(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    with pytest.raises(RerankError, match="件数"):
        await _cohere(short).rerank("q", ["x"])


# ---- A3 組み立て


def test_build_embedder_by_provider() -> None:
    assert build_embedder(_settings()) is None
    tei = build_embedder(_settings(tei_embed_url="http://tei:8081"))
    assert isinstance(tei, TeiEmbedder) and not isinstance(tei, OpenAIEmbedder)
    # 新しい URL が従来の TEI の URL より優先
    tei2 = build_embedder(_settings(tei_embed_url="http://old", embed_url="http://new"))
    assert tei2 is not None and tei2.base_url == "http://new"
    oa = build_embedder(
        _settings(embed_provider="openai", embed_url="https://api/v1", embed_model="m", embed_api_key="k")
    )
    assert isinstance(oa, OpenAIEmbedder) and oa.model == "m"


def test_build_reranker_by_provider() -> None:
    assert build_reranker(_settings()) is None
    assert isinstance(build_reranker(_settings(tei_rerank_url="http://tei")), TeiReranker)
    co = build_reranker(_settings(rerank_provider="cohere", rerank_url="https://api/v1", rerank_model="r"))
    assert isinstance(co, CohereReranker) and co.model == "r"


def test_build_figure_describer_uses_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_chat_model(name: str, **kw: object) -> object:
        calls.append({"name": name, **kw})
        return object()

    monkeypatch.setattr("arag.inference.chat_model", fake_chat_model)
    assert build_figure_describer(_settings()) is None
    assert build_figure_describer(
        _settings(
            vlm_model="openai:qwen2.5-vl",
            vlm_base_url="http://gpu:8091/v1",
            vlm_model_kwargs={"temperature": 0},
        )
    )
    assert calls == [
        {"name": "openai:qwen2.5-vl", "base_url": "http://gpu:8091/v1", "kwargs": {"temperature": 0}}
    ]


def test_describe_inference_hides_keys() -> None:
    s = _settings(
        embed_provider="openai",
        embed_url="https://api.openai.com/v1",
        embed_model="text-embedding-3-small",
        embed_api_key="sk-secret",
        rerank_provider="cohere",
        rerank_url="https://api.cohere.com/v2",
        rerank_api_key="co-secret",
        docling_url="http://docling:5001",
        vlm_model="openai:qwen2.5-vl",
        vlm_base_url="http://gpu:8091/v1",
    )
    info = describe_inference(s)
    assert info["embed"] == {
        "provider": "openai",
        "model": "text-embedding-3-small",
        "where": "api.openai.com",
    }
    assert info["rerank"]["provider"] == "cohere"
    assert info["vlm"] == {"provider": "self-hosted", "model": "openai:qwen2.5-vl", "where": "gpu:8091"}
    assert info["context"] == {"provider": "off"}
    assert "secret" not in json.dumps(info)


def test_inference_checks_skip_external_apis() -> None:
    names = {
        c.name: c for c in inference_checks(_settings(tei_embed_url="http://tei", docling_url="http://d"))
    }
    assert names["embed"].run is not None and names["rerank"].run is None
    ext = {
        c.name: c
        for c in inference_checks(
            _settings(
                embed_provider="openai",
                embed_url="https://api/v1",
                rerank_provider="cohere",
                rerank_url="https://x",
            )
        )
    }
    assert ext["embed"].external and ext["rerank"].external
