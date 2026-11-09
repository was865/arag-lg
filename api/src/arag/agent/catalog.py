"""会話で使うモデル目録の合成（specs/013-llm-keys R5）。

DB の有効なモデル（並び順）→ .env の ARAG_CHAT_MODELS のうち DB に同じ id が無いもの。
要求ごと・実行ごとに読むので、画面での変更は再起動なしで効く。
"""

from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arag.agent.config import ModelCatalog, ModelSpec
from arag.db.models import LlmCredential, LlmModel
from arag.llm import has_credentials
from arag.secrets import SecretBox
from arag.settings import Settings

# provider → model 文字列の接頭辞
PROVIDER_PREFIX = {
    "openai": "openai",
    "anthropic": "anthropic",
    "deepseek": "deepseek",
    "google_genai": "google_genai",
    "openai_compatible": "openai",
}


def secret_box(settings: Settings) -> SecretBox | None:
    return SecretBox.from_setting(settings.secret_key.get_secret_value())


def db_spec(m: LlmModel, cred: LlmCredential | None, box: SecretBox | None) -> ModelSpec:
    spec = ModelSpec(
        id=m.id,
        label=m.label,
        model=m.model,
        kwargs=dict(m.kwargs or {}),
        tags=tuple(m.tags or ()),
        source="db",
    )
    if cred is None:
        return replace(spec, available=has_credentials(spec.model))
    key = ""
    if cred.secret_enc:
        plain = box.try_decrypt(cred.secret_enc) if box else None
        if plain is None:
            return replace(spec, base_url=cred.base_url)  # 復号できない＝使えない
        key = plain
    ok = bool(key) or cred.provider == "openai_compatible"
    return replace(spec, base_url=cred.base_url, api_key=key, available=ok)


async def load_catalog(s: AsyncSession, settings: Settings) -> ModelCatalog:
    box = secret_box(settings)
    rows = (
        await s.execute(
            select(LlmModel, LlmCredential)
            .outerjoin(LlmCredential, LlmCredential.id == LlmModel.credential_id)
            .order_by(LlmModel.position, LlmModel.created_at)
        )
    ).all()
    seen = {m.id for m, _ in rows}  # 無効にしたものも .env の同じ id を隠す
    specs = [db_spec(m, c, box) for m, c in rows if m.enabled]
    env = ModelCatalog.from_raw([r for r in settings.chat_models if str(r.get("id")) not in seen])
    return ModelCatalog((*specs, *env.models))
