"""チャットモデルの生成（init_chat_model の薄い包み。入庫の文脈付与・エージェント・評価で共用）。"""

import os
from typing import Any

from langchain_core.language_models import BaseChatModel


def chat_model(name: str, *, base_url: str = "", kwargs: dict[str, Any] | None = None) -> BaseChatModel:
    from langchain.chat_models import init_chat_model

    extra: dict[str, Any] = dict(kwargs or {})
    if base_url:
        # 自前サーバは鍵を見ないが、クライアントは空の鍵を受け付けない
        extra |= {"base_url": base_url, "api_key": os.environ.get("ARAG_CONTEXT_API_KEY", "EMPTY")}
    model: BaseChatModel = init_chat_model(name, **extra)
    return model


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
