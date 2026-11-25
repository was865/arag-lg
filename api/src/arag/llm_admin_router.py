"""LLM の接続（API キー）とモデル目録の管理（specs/013-llm-keys）。owner・admin のみ。"""

import asyncio
import re
import time
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Response
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select

from arag.agent.catalog import PROVIDER_PREFIX, db_spec, load_catalog
from arag.agent.config import ModelNotFound, ModelSpec
from arag.audit import AuditEvent
from arag.db.models import LlmCredential, LlmModel
from arag.deps import CtxDep, get_settings
from arag.errors import ApiError
from arag.secrets import secret_box
from arag.settings import Settings

router = APIRouter(tags=["llm-admin"])
SettingsDep = Annotated[Settings, Depends(get_settings)]

Provider = Literal["openai", "anthropic", "deepseek", "google_genai", "openai_compatible"]
PROVIDERS: tuple[Provider, ...] = ("openai", "anthropic", "deepseek", "google_genai", "openai_compatible")
MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
PING_TIMEOUT_SEC = 20.0


def _require_admin(ctx: CtxDep) -> None:
    if not ctx.principal.is_admin:
        raise ApiError(403, "forbidden", "管理者だけが使えます")


# --- 入出力 ---


class CredentialIn(BaseModel):
    provider: Provider
    label: str = Field(min_length=1, max_length=100)
    api_key: str | None = Field(default=None, max_length=500)
    base_url: str = Field(default="", max_length=500)


class CredentialPatch(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=100)
    api_key: str | None = Field(default=None, min_length=1, max_length=500)
    base_url: str | None = Field(default=None, max_length=500)


class CredentialOut(BaseModel):
    id: uuid.UUID
    provider: str
    label: str
    key_hint: str | None
    base_url: str
    updated_at: datetime
    models: int


class ModelIn(BaseModel):
    id: str
    label: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=3, max_length=200)
    credential_id: uuid.UUID | None = None
    kwargs: dict[str, Any] = Field(default_factory=dict)
    tags: list[Annotated[str, Field(max_length=20)]] = Field(default_factory=list, max_length=5)
    enabled: bool = True

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not MODEL_ID.match(v):
            raise ValueError("id は英小文字・数字・-・_ で 64 文字まで")
        return v


class ModelPatch(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=100)
    model: str | None = Field(default=None, min_length=3, max_length=200)
    credential_id: uuid.UUID | None = None
    clear_credential: bool = False
    kwargs: dict[str, Any] | None = None
    tags: list[Annotated[str, Field(max_length=20)]] | None = Field(default=None, max_length=5)
    enabled: bool | None = None


class ModelRow(BaseModel):
    id: str
    label: str
    model: str
    credential_id: uuid.UUID | None
    credential_label: str | None
    kwargs: dict[str, Any]
    tags: list[str]
    enabled: bool
    source: Literal["db", "env"]
    available: bool
    is_default: bool
    base_url: str | None = Field(default=None, description="接続先（.env の base_url か接続の base_url）")


class LlmAdminOut(BaseModel):
    encryption_ready: bool
    providers: list[str]
    credentials: list[CredentialOut]
    models: list[ModelRow]


class OrderIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=200)


class CheckOut(BaseModel):
    ok: bool
    latency_ms: int
    error: str | None


# --- 一覧 ---


@router.get("/v1/admin/llm", response_model=LlmAdminOut)
async def overview(ctx: CtxDep, settings: SettingsDep) -> LlmAdminOut:
    _require_admin(ctx)
    s = ctx.session
    creds = list((await s.execute(select(LlmCredential).order_by(LlmCredential.created_at))).scalars())
    usage = dict(
        (
            await s.execute(
                select(LlmModel.credential_id, func.count())
                .where(LlmModel.credential_id.is_not(None))
                .group_by(LlmModel.credential_id)
            )
        ).all()
    )
    labels = {c.id: c.label for c in creds}
    urls = {c.id: c.base_url for c in creds}
    catalog = await load_catalog(s, settings)
    try:
        default_id: str | None = catalog.default().id
    except ModelNotFound:
        default_id = None
    live = {m.id: m for m in catalog.models}
    db_models = list(
        (await s.execute(select(LlmModel).order_by(LlmModel.position, LlmModel.created_at))).scalars()
    )
    rows = [
        ModelRow(
            id=m.id,
            label=m.label,
            model=m.model,
            credential_id=m.credential_id,
            credential_label=labels.get(m.credential_id) if m.credential_id else None,
            kwargs=m.kwargs or {},
            tags=list(m.tags or []),
            enabled=m.enabled,
            source="db",
            available=bool(live.get(m.id) and live[m.id].available),
            is_default=m.id == default_id,
            base_url=(urls.get(m.credential_id) or None) if m.credential_id else None,
        )
        for m in db_models
    ]
    rows += [
        ModelRow(
            id=m.id,
            label=m.label,
            model=m.model,
            credential_id=None,
            credential_label=None,
            kwargs=m.kwargs,
            tags=list(m.tags),
            enabled=True,
            source="env",
            available=m.available,
            is_default=m.id == default_id,
            base_url=m.base_url or None,
        )
        for m in catalog.models
        if m.source == "env"
    ]
    return LlmAdminOut(
        encryption_ready=secret_box(settings) is not None,
        providers=list(PROVIDERS),
        credentials=[_cred_out(c, usage.get(c.id, 0)) for c in creds],
        models=rows,
    )


def _cred_out(c: LlmCredential, models: int) -> CredentialOut:
    return CredentialOut(
        id=c.id,
        provider=c.provider,
        label=c.label,
        key_hint=c.key_hint,
        base_url=c.base_url,
        updated_at=c.updated_at,
        models=models,
    )


# --- 接続 ---


def _check_credential(provider: str, api_key: str | None, base_url: str) -> None:
    if provider == "openai_compatible" and not base_url.strip():
        raise ApiError(422, "base_url_required", "OpenAI 互換サーバには URL が必要です")
    if provider != "openai_compatible" and not api_key:
        raise ApiError(422, "api_key_required", "API キーを入力してください")
    if base_url and not re.match(r"^https?://", base_url):
        raise ApiError(422, "invalid_base_url", "URL は http:// か https:// で始めてください")


@router.post("/v1/admin/llm/credentials", response_model=CredentialOut, status_code=201)
async def create_credential(ctx: CtxDep, settings: SettingsDep, body: CredentialIn) -> CredentialOut:
    _require_admin(ctx)
    api_key = (body.api_key or "").strip() or None
    base_url = body.base_url.strip()
    _check_credential(body.provider, api_key, base_url)
    box = secret_box(settings)
    if box is None:
        raise ApiError(503, "secret_key_missing", "暗号化の鍵（ARAG_SECRET_KEY）が設定されていません")
    c = LlmCredential(
        provider=body.provider,
        label=body.label.strip(),
        secret_enc=box.encrypt(api_key) if api_key else None,
        key_hint=box.hint(api_key) if api_key else None,
        base_url=base_url,
        created_by=ctx.principal.user_id,
    )
    ctx.session.add(c)
    await ctx.session.flush()
    await ctx.audit(
        AuditEvent(
            action="llm.credential.create",
            resource_type="llm_credential",
            resource_id=str(c.id),
            detail={"provider": c.provider, "label": c.label},
        )
    )
    await ctx.session.commit()
    await ctx.session.refresh(c)
    return _cred_out(c, 0)


async def _get_cred(ctx: CtxDep, cred_id: uuid.UUID) -> LlmCredential:
    c = await ctx.session.get(LlmCredential, cred_id)
    if c is None:
        raise ApiError(404, "not_found", "接続が見つかりません")
    return c


@router.patch("/v1/admin/llm/credentials/{cred_id}", response_model=CredentialOut)
async def update_credential(
    ctx: CtxDep, settings: SettingsDep, cred_id: uuid.UUID, body: CredentialPatch
) -> CredentialOut:
    _require_admin(ctx)
    c = await _get_cred(ctx, cred_id)
    changed: list[str] = []
    if body.label is not None and body.label.strip() != c.label:
        c.label = body.label.strip()
        changed.append("label")
    if body.base_url is not None and body.base_url.strip() != c.base_url:
        c.base_url = body.base_url.strip()
        changed.append("base_url")
    rotated = False
    if body.api_key is not None and body.api_key.strip():
        box = secret_box(settings)
        if box is None:
            raise ApiError(503, "secret_key_missing", "暗号化の鍵（ARAG_SECRET_KEY）が設定されていません")
        key = body.api_key.strip()
        c.secret_enc, c.key_hint, rotated = box.encrypt(key), box.hint(key), True
    _check_credential(c.provider, "x" if c.secret_enc else None, c.base_url)
    c.updated_at = datetime.now(UTC)
    await ctx.audit(
        AuditEvent(
            action="llm.credential.update",
            resource_type="llm_credential",
            resource_id=str(c.id),
            detail={"label": c.label, "changed": changed, "key_rotated": rotated},
        )
    )
    await ctx.session.commit()
    used = await ctx.session.scalar(select(func.count()).where(LlmModel.credential_id == c.id))
    return _cred_out(c, used or 0)


@router.delete("/v1/admin/llm/credentials/{cred_id}", status_code=204)
async def delete_credential(ctx: CtxDep, cred_id: uuid.UUID) -> Response:
    _require_admin(ctx)
    c = await _get_cred(ctx, cred_id)
    used = await ctx.session.scalar(select(func.count()).where(LlmModel.credential_id == c.id))
    if used:
        raise ApiError(409, "credential_in_use", f"この接続は {used} 件のモデルで使われています")
    await ctx.session.delete(c)
    await ctx.audit(
        AuditEvent(
            action="llm.credential.delete",
            resource_type="llm_credential",
            resource_id=str(c.id),
            detail={"provider": c.provider, "label": c.label},
        )
    )
    await ctx.session.commit()
    return Response(status_code=204)


# --- モデル ---


async def _check_model(ctx: CtxDep, model: str, credential_id: uuid.UUID | None) -> None:
    if ":" not in model:
        raise ApiError(422, "invalid_model", "モデルは「provider:モデル名」の形で入力してください")
    if credential_id is None:
        return
    c = await ctx.session.get(LlmCredential, credential_id)
    if c is None:
        raise ApiError(422, "credential_not_found", "接続が見つかりません")
    prefix = PROVIDER_PREFIX[c.provider]
    if model.split(":", 1)[0] != prefix:
        raise ApiError(422, "provider_mismatch", f"この接続のモデルは「{prefix}:」で始めてください")


def _row(m: LlmModel) -> ModelRow:
    return ModelRow(
        id=m.id,
        label=m.label,
        model=m.model,
        credential_id=m.credential_id,
        credential_label=None,
        kwargs=m.kwargs or {},
        tags=list(m.tags or []),
        enabled=m.enabled,
        source="db",
        available=False,  # 一覧（GET /v1/admin/llm）で確かめる
        is_default=False,
    )


@router.post("/v1/admin/llm/models", response_model=ModelRow, status_code=201)
async def create_model(ctx: CtxDep, body: ModelIn) -> ModelRow:
    _require_admin(ctx)
    if await ctx.session.get(LlmModel, body.id):
        raise ApiError(409, "model_exists", f"id「{body.id}」のモデルは既にあります")
    await _check_model(ctx, body.model.strip(), body.credential_id)
    last = await ctx.session.scalar(select(func.max(LlmModel.position)))
    m = LlmModel(
        id=body.id,
        label=body.label.strip(),
        model=body.model.strip(),
        credential_id=body.credential_id,
        kwargs=body.kwargs,
        tags=[t.strip() for t in body.tags if t.strip()],
        enabled=body.enabled,
        position=(last + 1) if last is not None else 0,
    )
    ctx.session.add(m)
    await ctx.audit(
        AuditEvent(
            action="llm.model.create",
            resource_type="llm_model",
            resource_id=m.id,
            detail={"label": m.label, "model": m.model},
        )
    )
    await ctx.session.commit()
    return _row(m)


async def _get_model(ctx: CtxDep, model_id: str) -> LlmModel:
    m = await ctx.session.get(LlmModel, model_id)
    if m is None:
        raise ApiError(404, "not_found", "モデルが見つかりません")
    return m


@router.patch("/v1/admin/llm/models/{model_id}", response_model=ModelRow)
async def update_model(ctx: CtxDep, model_id: str, body: ModelPatch) -> ModelRow:
    _require_admin(ctx)
    m = await _get_model(ctx, model_id)
    fields = body.model_dump(exclude_unset=True)
    cred = None if body.clear_credential else (body.credential_id or m.credential_id)
    model = (body.model or m.model).strip()
    await _check_model(ctx, model, cred)
    m.model, m.credential_id = model, cred
    if body.label is not None:
        m.label = body.label.strip()
    if body.kwargs is not None:
        m.kwargs = body.kwargs
    if body.tags is not None:
        m.tags = [t.strip() for t in body.tags if t.strip()]
    if body.enabled is not None:
        m.enabled = body.enabled
    m.updated_at = datetime.now(UTC)
    await ctx.audit(
        AuditEvent(
            action="llm.model.update",
            resource_type="llm_model",
            resource_id=m.id,
            detail={"changed": sorted(k for k in fields if k != "clear_credential"), "enabled": m.enabled},
        )
    )
    await ctx.session.commit()
    return _row(m)


@router.delete("/v1/admin/llm/models/{model_id}", status_code=204)
async def delete_model(ctx: CtxDep, model_id: str) -> Response:
    _require_admin(ctx)
    m = await _get_model(ctx, model_id)
    await ctx.session.delete(m)
    await ctx.audit(
        AuditEvent(
            action="llm.model.delete", resource_type="llm_model", resource_id=m.id, detail={"label": m.label}
        )
    )
    await ctx.session.commit()
    return Response(status_code=204)


@router.put("/v1/admin/llm/models/order", status_code=204)
async def reorder_models(ctx: CtxDep, body: OrderIn) -> Response:
    _require_admin(ctx)
    models = {m.id: m for m in (await ctx.session.execute(select(LlmModel))).scalars()}
    if len(set(body.ids)) != len(body.ids) or any(i not in models for i in body.ids):
        raise ApiError(422, "invalid_order", "並び順に知らない id か重複があります")
    rest = sorted((m for i, m in models.items() if i not in body.ids), key=lambda m: m.position)
    for pos, m in enumerate([models[i] for i in body.ids] + rest):
        m.position = pos
    await ctx.audit(
        AuditEvent(action="llm.model.reorder", resource_type="llm_model", detail={"ids": body.ids})
    )
    await ctx.session.commit()
    return Response(status_code=204)


# --- 接続の確認 ---


async def _ping(spec: ModelSpec) -> None:
    """短い問い合わせを 1 回送る（テストで差し替える）。"""
    model = spec.build()
    await model.ainvoke([HumanMessage("Reply with just: ok")])


def _redact(msg: str, secret: str) -> str:
    if secret:
        msg = msg.replace(secret, "****")
    return msg[:300]


@router.post("/v1/admin/llm/models/{model_id}/test", response_model=CheckOut)
async def check_model(ctx: CtxDep, settings: SettingsDep, model_id: str) -> CheckOut:
    _require_admin(ctx)
    catalog = await load_catalog(ctx.session, settings)
    spec = next((m for m in catalog.models if m.id == model_id), None)
    if spec is None:
        # 無効にした DB のモデルも確かめられるようにする
        row = await ctx.session.get(LlmModel, model_id)
        if row is None:
            raise ApiError(404, "not_found", "モデルが見つかりません")
        cred = await ctx.session.get(LlmCredential, row.credential_id) if row.credential_id else None
        spec = db_spec(row, cred, secret_box(settings))
    started = time.perf_counter()
    try:
        await asyncio.wait_for(_ping(spec), timeout=PING_TIMEOUT_SEC)
        ok, err = True, None
    except TimeoutError:
        ok, err = False, f"{int(PING_TIMEOUT_SEC)} 秒以内に応答がありませんでした"
    except Exception as e:
        ok, err = False, _redact(f"{type(e).__name__}: {e}", spec.api_key)
    return CheckOut(ok=ok, latency_ms=int((time.perf_counter() - started) * 1000), error=err)
