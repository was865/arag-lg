"""チャットモデルの生成（init_chat_model の薄い包み。入庫の文脈付与・エージェント・評価で共用）。"""

import os
from typing import Any

from langchain_core.language_models import BaseChatModel


def chat_model(
    name: str, *, base_url: str = "", kwargs: dict[str, Any] | None = None, api_key: str = ""
) -> BaseChatModel:
    from langchain.chat_models import init_chat_model

    extra: dict[str, Any] = dict(kwargs or {})
    if api_key:
        # 画面で登録した接続の鍵（specs/013-llm-keys）。環境変数より優先する
        extra["api_key"] = api_key
    if base_url:
        # 自前サーバは鍵を見ないが、クライアントは空の鍵を受け付けない
        extra["base_url"] = base_url
        extra.setdefault("api_key", os.environ.get("ARAG_CONTEXT_API_KEY", "EMPTY"))
        if name.startswith("openai:"):
            # 自前サーバでは stream_usage が既定で切れ、ストリーミング時のトークン数が 0 になる
            extra.setdefault("stream_usage", True)
        if name.startswith("openai:"):
            # vLLM などは考えた過程を別の欄で返す。ChatOpenAI はそれを捨てるので拾う版を使う
            return _compatible_chat(name.removeprefix("openai:"), extra)
    model: BaseChatModel = init_chat_model(name, **extra)
    return model


def _reasoning_of(obj: Any) -> str | None:
    """応答・差分から考えた過程を取り出す（vLLM: reasoning_content / reasoning）。"""
    for key in ("reasoning_content", "reasoning"):
        v = obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
        if v is None and not isinstance(obj, dict):
            v = (getattr(obj, "model_extra", None) or {}).get(key)
        if isinstance(v, str) and v:
            return v
    return None


def _compatible_chat(model: str, extra: dict[str, Any]) -> BaseChatModel:
    from langchain_core.outputs import ChatGenerationChunk, ChatResult
    from langchain_openai import ChatOpenAI

    class CompatibleChat(ChatOpenAI):
        """OpenAI 互換サーバー向け。考えた過程を additional_kwargs["reasoning_content"] に残す。"""

        def _create_chat_result(
            self, response: Any, generation_info: dict[str, Any] | None = None
        ) -> ChatResult:
            result = super()._create_chat_result(response, generation_info)
            choices = getattr(response, "choices", None)
            if choices and (r := _reasoning_of(choices[0].message)):
                result.generations[0].message.additional_kwargs["reasoning_content"] = r
            return result

        def _convert_chunk_to_generation_chunk(
            self,
            chunk: dict[str, Any],
            default_chunk_class: type,
            base_generation_info: dict[str, Any] | None,
        ) -> ChatGenerationChunk | None:
            gen = super()._convert_chunk_to_generation_chunk(chunk, default_chunk_class, base_generation_info)
            choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices") or []
            if gen and choices and (r := _reasoning_of(choices[0].get("delta") or {})):
                gen.message.additional_kwargs["reasoning_content"] = r
            return gen

    return CompatibleChat(model=model, **extra)


# provider（"<provider>:<model>" の接頭辞）→ 鍵の環境変数
PROVIDER_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "google_genai": "GOOGLE_API_KEY",
}


def has_credentials(model: str, base_url: str = "") -> bool:
    """自前サーバ（base_url あり）か、provider の鍵が環境にあるか。"""
    if base_url:
        return True
    provider = model.split(":", 1)[0] if ":" in model else ""
    env = PROVIDER_KEY_ENV.get(provider)
    return bool(env and os.environ.get(env))
