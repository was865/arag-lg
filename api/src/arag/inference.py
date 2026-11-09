"""推論の部品を設定から組み立てる（specs/016-inference-modules）。

役割（埋め込み・並べ替え・図の説明・文脈の付与・解析）ごとに、自前のサービスか外部 API かを
起動時の設定だけで選ぶ。入庫・検索・readiness はすべてここを通す。
"""

from typing import Any
from urllib.parse import urlparse

from arag.agent.query_image import QueryImageReader
from arag.health import Check, http_check
from arag.ingest.embedder import OpenAIEmbedder, TeiEmbedder
from arag.ingest.figures import LlmFigureDescriber
from arag.llm import chat_model
from arag.search.rerank import CohereReranker, TeiReranker
from arag.settings import Settings


def embed_endpoint(settings: Settings) -> str:
    return settings.embed_url or settings.tei_embed_url


def rerank_endpoint(settings: Settings) -> str:
    return settings.rerank_url or settings.tei_rerank_url


def build_embedder(settings: Settings, **overrides: Any) -> TeiEmbedder | None:
    """URL が無ければ None（検索は密ベクトルなしで縮退、入庫は起動しない）。"""
    url = embed_endpoint(settings)
    if not url:
        return None
    kw: dict[str, Any] = {
        "model": settings.embed_model,
        "document_prefix": settings.embed_document_prefix,
        "query_prefix": settings.embed_query_prefix,
        "batch_size": settings.embed_batch_size,
        "timeout_sec": settings.http_timeout_sec,
        **overrides,
    }
    if settings.embed_provider == "openai":
        return OpenAIEmbedder(
            url,
            api_key=settings.embed_api_key.get_secret_value(),
            dimensions=settings.embed_dimensions,
            **kw,
        )
    return TeiEmbedder(url, **kw)


def build_reranker(settings: Settings) -> TeiReranker | None:
    url = rerank_endpoint(settings)
    if not url:
        return None
    kw: dict[str, Any] = {"model": settings.rerank_model, "timeout_sec": settings.rerank_timeout_sec}
    if settings.rerank_provider == "cohere":
        return CohereReranker(url, api_key=settings.rerank_api_key.get_secret_value(), **kw)
    return TeiReranker(url, **kw)


def build_figure_describer(settings: Settings) -> LlmFigureDescriber | None:
    if not settings.vlm_model:
        return None
    return LlmFigureDescriber(
        chat_model(settings.vlm_model, base_url=settings.vlm_base_url, kwargs=settings.vlm_model_kwargs)
    )


def build_query_image_reader(settings: Settings) -> QueryImageReader | None:
    """質問に添えた画像を読む（図の説明と同じモデル。specs/017）。"""
    if not settings.vlm_model:
        return None
    return QueryImageReader(
        chat_model(settings.vlm_model, base_url=settings.vlm_base_url, kwargs=settings.vlm_model_kwargs)
    )


def _host(url: str) -> str:
    return urlparse(url).netloc or url


def describe_inference(settings: Settings) -> dict[str, dict[str, str]]:
    """起動ログ用の構成（鍵は含めない。R5）。"""

    def llm(model: str, base_url: str) -> dict[str, str]:
        if not model:
            return {"provider": "off"}
        if base_url:
            return {"provider": "self-hosted", "model": model, "where": _host(base_url)}
        return {"provider": model.split(":", 1)[0], "model": model}

    embed = embed_endpoint(settings)
    rerank = rerank_endpoint(settings)
    return {
        "parse": {"provider": "docling-serve", "where": _host(settings.docling_url)}
        if settings.docling_url
        else {"provider": "off"},
        "embed": {"provider": settings.embed_provider, "model": settings.embed_model, "where": _host(embed)}
        if embed
        else {"provider": "off"},
        "rerank": {
            "provider": settings.rerank_provider,
            "model": settings.rerank_model,
            "where": _host(rerank),
        }
        if rerank
        else {"provider": "off"},
        "context": llm(settings.context_model, settings.context_base_url),
        "vlm": llm(settings.vlm_model, settings.vlm_base_url),
    }


def inference_checks(settings: Settings) -> list[Check]:
    """readiness: 自前のサービスだけ /health を確かめる。外部 API は external（課金・鍵の露出を避ける）。"""

    def role(name: str, url: str, external: bool) -> Check:
        if not url:
            return Check(name, None)
        if external:
            return Check(name, None, external=True)
        return Check(name, http_check(url.rstrip("/") + "/health"))

    return [
        role("embed", embed_endpoint(settings), settings.embed_provider != "tei"),
        role("rerank", rerank_endpoint(settings), settings.rerank_provider != "tei"),
        role("docling", settings.docling_url, False),  # R40
    ]
