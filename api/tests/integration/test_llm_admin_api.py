"""LLM の接続とモデル目録の管理 API（specs/013-llm-keys A3〜A5、R1〜R7）。"""

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag import llm_admin_router
from arag.agent.config import ModelSpec
from arag.db.models import AuditLog, LlmCredential

from .conftest import ADMIN, ALICE

pytestmark = pytest.mark.integration

KEY = Fernet.generate_key().decode()
ENV_MODELS = [
    {"id": "local", "label": "社内", "model": "openai:qwen3-8b", "base_url": "http://llm/v1"},
    {"id": "envds", "label": "DeepSeek（env）", "model": "deepseek:deepseek-chat"},
]
SECRET = "sk-test-0123456789abcd"


@pytest.fixture
async def api(make_client: Callable[..., Awaitable[httpx.AsyncClient]]) -> httpx.AsyncClient:
    return await make_client(chat_models=ENV_MODELS, secret_key=KEY)


async def _cred(api: httpx.AsyncClient, **kw: Any) -> dict[str, Any]:
    body = {"provider": "deepseek", "label": "DeepSeek 本番", "api_key": SECRET} | kw
    r = await api.post("/v1/admin/llm/credentials", json=body, headers=ADMIN)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def _model(api: httpx.AsyncClient, **kw: Any) -> httpx.Response:
    body = {"id": "ds", "label": "DeepSeek", "model": "deepseek:deepseek-chat"} | kw
    return await api.post("/v1/admin/llm/models", json=body, headers=ADMIN)


async def test_only_admins(api: httpx.AsyncClient) -> None:
    assert (await api.get("/v1/admin/llm", headers=ALICE)).status_code == 403
    r = await api.post(
        "/v1/admin/llm/credentials", json={"provider": "openai", "label": "x", "api_key": "k"}, headers=ALICE
    )
    assert r.status_code == 403


async def test_credential_is_encrypted_and_never_returned(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    c = await _cred(api)
    assert c["key_hint"] == "abcd" and "api_key" not in c and "secret_enc" not in c
    async with sessionmaker() as s:
        row = (await s.execute(select(LlmCredential))).scalar_one()
        assert row.secret_enc and SECRET not in row.secret_enc
        dump = (await s.execute(text("select row_to_json(t)::text from app.llm_credentials t"))).scalar_one()
        assert SECRET not in dump
        audit = (await s.execute(select(AuditLog).where(AuditLog.action.like("llm.%")))).scalars().all()
        assert [a.action for a in audit] == ["llm.credential.create"]
        assert SECRET not in str(audit[0].detail)
    listing = (await api.get("/v1/admin/llm", headers=ADMIN)).text
    assert SECRET not in listing and '"encryption_ready":true' in listing


async def test_missing_secret_key_blocks_registration(
    make_client: Callable[..., Awaitable[httpx.AsyncClient]],
) -> None:
    c = await make_client(chat_models=ENV_MODELS, secret_key="")
    assert (await c.get("/v1/admin/llm", headers=ADMIN)).json()["encryption_ready"] is False
    r = await c.post(
        "/v1/admin/llm/credentials", json={"provider": "openai", "label": "x", "api_key": "k"}, headers=ADMIN
    )
    assert r.status_code == 503 and r.json()["error"]["code"] == "secret_key_missing"


async def test_credential_validation(api: httpx.AsyncClient) -> None:
    bad = [
        {"provider": "nope", "label": "x", "api_key": "k"},
        {"provider": "openai", "label": "x"},  # キー必須
        {"provider": "openai_compatible", "label": "x"},  # base_url 必須
        {"provider": "openai", "label": "", "api_key": "k"},
    ]
    for b in bad:
        assert (await api.post("/v1/admin/llm/credentials", json=b, headers=ADMIN)).status_code == 422, b
    ok = {"provider": "openai_compatible", "label": "GPU", "base_url": "http://gpu:8090/v1"}
    r = await api.post("/v1/admin/llm/credentials", json=ok, headers=ADMIN)
    assert r.status_code == 201 and r.json()["key_hint"] is None


async def test_catalog_merge_order_override_and_disable(api: httpx.AsyncClient) -> None:
    c = await _cred(api)
    assert (await _model(api, credential_id=c["id"], tags=["高速"])).status_code == 201
    # .env と同じ id は DB が上書き、無効にすると .env の分も出ない
    assert (await _model(api, id="local", label="無効", model="openai:x", enabled=False)).status_code == 201
    models = (await api.get("/v1/models", headers=ALICE)).json()
    assert [(m["id"], m["available"]) for m in models["models"]] == [("ds", True), ("envds", False)]
    assert models["default_id"] == "ds"

    admin = (await api.get("/v1/admin/llm", headers=ADMIN)).json()
    assert [(m["id"], m["source"], m["enabled"]) for m in admin["models"]] == [
        ("ds", "db", True),
        ("local", "db", False),
        ("envds", "env", True),
    ]
    assert admin["models"][0]["credential_label"] == "DeepSeek 本番"
    assert admin["models"][0]["is_default"] is True


async def test_model_validation_and_conflicts(api: httpx.AsyncClient) -> None:
    c = await _cred(api)
    assert (await _model(api, id="Bad Id")).status_code == 422
    assert (await _model(api, model="openai:gpt", credential_id=c["id"])).status_code == 422  # 接頭辞が違う
    assert (await _model(api, kwargs=[1])).status_code == 422
    assert (await _model(api, credential_id=c["id"])).status_code == 201
    r = await _model(api, credential_id=c["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "model_exists"
    # 使われている接続は消せない
    r = await api.delete(f"/v1/admin/llm/credentials/{c['id']}", headers=ADMIN)
    assert r.status_code == 409 and r.json()["error"]["code"] == "credential_in_use"
    assert (await api.delete("/v1/admin/llm/models/ds", headers=ADMIN)).status_code == 204
    assert (await api.delete(f"/v1/admin/llm/credentials/{c['id']}", headers=ADMIN)).status_code == 204


async def test_update_rotate_and_reorder(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    c = await _cred(api)
    r = await api.patch(
        f"/v1/admin/llm/credentials/{c['id']}",
        json={"label": "新しい名前", "api_key": "sk-new-9999"},
        headers=ADMIN,
    )
    assert r.status_code == 200 and r.json()["key_hint"] == "9999" and r.json()["label"] == "新しい名前"
    await _model(api, id="a", credential_id=c["id"])
    await _model(api, id="b", credential_id=c["id"])
    r = await api.patch(
        "/v1/admin/llm/models/a", json={"label": "A", "tags": ["x"], "enabled": False}, headers=ADMIN
    )
    assert r.status_code == 200 and r.json()["enabled"] is False
    assert (
        await api.put("/v1/admin/llm/models/order", json={"ids": ["b", "a"]}, headers=ADMIN)
    ).status_code == 204
    ids = [m["id"] for m in (await api.get("/v1/admin/llm", headers=ADMIN)).json()["models"]]
    assert ids[:2] == ["b", "a"]
    assert (
        await api.put("/v1/admin/llm/models/order", json={"ids": ["zz"]}, headers=ADMIN)
    ).status_code == 422
    async with sessionmaker() as s:
        actions = (
            await s.execute(
                select(AuditLog.action, AuditLog.detail)
                .where(AuditLog.action.like("llm.%"))
                .order_by(AuditLog.ts)
            )
        ).all()
    assert [a for a, _ in actions] == [
        "llm.credential.create",
        "llm.credential.update",
        "llm.model.create",
        "llm.model.create",
        "llm.model.update",
        "llm.model.reorder",
    ]
    assert actions[1][1]["key_rotated"] is True and "sk-new" not in str(actions[1][1])


async def test_connection_check(api: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    c = await _cred(api)
    await _model(api, credential_id=c["id"])
    seen: list[ModelSpec] = []

    async def fake_ping(spec: ModelSpec) -> None:
        seen.append(spec)
        raise RuntimeError(f"401 invalid key {spec.api_key}")

    monkeypatch.setattr(llm_admin_router, "_ping", fake_ping)
    r = await api.post("/v1/admin/llm/models/ds/test", headers=ADMIN)
    body = r.json()
    assert r.status_code == 200 and body["ok"] is False
    assert SECRET not in body["error"] and "401" in body["error"]  # 失敗理由からキーを伏せる
    assert seen[0].api_key == SECRET

    async def ok_ping(spec: ModelSpec) -> None:
        return None

    monkeypatch.setattr(llm_admin_router, "_ping", ok_ping)
    body = (await api.post("/v1/admin/llm/models/ds/test", headers=ADMIN)).json()
    assert body["ok"] is True and body["latency_ms"] >= 0
    assert (await api.post("/v1/admin/llm/models/nope/test", headers=ADMIN)).status_code == 404
    # .env 由来も確認できる
    monkeypatch.setattr(llm_admin_router, "_ping", ok_ping)
    assert (await api.post("/v1/admin/llm/models/local/test", headers=ADMIN)).json()["ok"] is True
