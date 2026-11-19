"""社内システム（MCP サーバ）の登録の管理 API（specs/032 R8〜R11）。"""

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.db.models import AuditLog, McpServer
from arag.mcp.registry import load_tools, usable_server_ids

from ..mcp_fake import KEY, running
from .conftest import ADMIN, ALICE

pytestmark = pytest.mark.integration


@pytest.fixture
async def api(make_client: Callable[..., Awaitable[httpx.AsyncClient]]) -> httpx.AsyncClient:
    return await make_client(mcp_identity_key=KEY, secret_key=Fernet.generate_key().decode())


async def _create(api: httpx.AsyncClient, url: str, **kw: Any) -> dict[str, Any]:
    body = {"name": "erp", "label": "ERP", "url": url} | kw
    r = await api.post("/v1/admin/mcp-servers", json=body, headers=ADMIN)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def test_only_admins(api: httpx.AsyncClient) -> None:
    assert (await api.get("/v1/admin/mcp-servers", headers=ALICE)).status_code == 403
    r = await api.post(
        "/v1/admin/mcp-servers", json={"name": "x", "label": "x", "url": "http://x/mcp"}, headers=ALICE
    )
    assert r.status_code == 403


async def test_register_fetches_tools_and_enables_read_only(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    with running() as (url, _):
        srv = await _create(api, url)
    assert srv["check_error"] is None
    tools = {t["name"]: t for t in srv["tools"]}
    assert tools["get_stock"]["read_only"] and tools["get_stock"]["enabled"]
    assert not tools["place_order"]["read_only"] and not tools["place_order"]["enabled"]
    # 書き込みのツールは選べない（R9）
    r = await api.put(
        f"/v1/admin/mcp-servers/{srv['id']}/tools",
        json={"enabled": ["get_stock", "place_order"]},
        headers=ADMIN,
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_read_only"
    async with sessionmaker() as s:
        assert [t.agent_name for t in await load_tools(s)] == ["erp__get_stock"]
        actions = set((await s.execute(select(AuditLog.action))).scalars())
        assert "mcp.server.create" in actions


async def test_unreachable_server_is_kept_with_reason(api: httpx.AsyncClient) -> None:
    srv = await _create(api, "http://127.0.0.1:9/mcp")
    assert srv["tools"] == [] and "McpUnavailable" in srv["check_error"]
    listed = (await api.get("/v1/admin/mcp-servers", headers=ADMIN)).json()
    assert listed["identity_ready"] and listed["encryption_ready"]
    assert [s["name"] for s in listed["servers"]] == ["erp"]


async def test_token_is_encrypted_and_never_returned(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    srv = await _create(api, "http://127.0.0.1:9/mcp", auth_kind="bearer", token="sekret-token-1234")
    assert srv["has_token"] and "token" not in srv and "secret_enc" not in srv
    async with sessionmaker() as s:
        row = (await s.execute(select(McpServer))).scalar_one()
        assert row.secret_enc and "sekret" not in row.secret_enc
    # identity に変えるとトークンは消える
    r = await api.patch(f"/v1/admin/mcp-servers/{srv['id']}", json={"auth_kind": "identity"}, headers=ADMIN)
    assert r.json()["has_token"] is False


async def test_shares_limit_who_can_use(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    srv = await _create(api, "http://127.0.0.1:9/mcp")
    dept = (await api.post("/v1/departments", json={"name": "購買課"}, headers=ADMIN)).json()["id"]
    r = await api.put(
        f"/v1/admin/mcp-servers/{srv['id']}/shares",
        json={"shares": [{"subject_type": "department", "subject_id": dept}]},
        headers=ADMIN,
    )
    assert r.status_code == 200 and r.json()["shares"][0]["name"] == "購買課"
    async with sessionmaker() as s:
        assert await usable_server_ids(s, frozenset()) == set()
        assert len(await usable_server_ids(s, frozenset({dept}))) == 1
    r = await api.put(
        f"/v1/admin/mcp-servers/{srv['id']}/shares",
        json={"shares": [{"subject_type": "everyone"}]},
        headers=ADMIN,
    )
    async with sessionmaker() as s:
        assert len(await usable_server_ids(s, frozenset())) == 1
    bad = await api.put(
        f"/v1/admin/mcp-servers/{srv['id']}/shares",
        json={"shares": [{"subject_type": "department", "subject_id": "nope"}]},
        headers=ADMIN,
    )
    assert bad.status_code == 422


async def test_refresh_drops_vanished_tools_and_delete(api: httpx.AsyncClient) -> None:
    with running() as (url, _):
        srv = await _create(api, url)
    # 止まったサーバの取り直しはエラーを残し、ツールの一覧は変えない
    r = await api.post(f"/v1/admin/mcp-servers/{srv['id']}/refresh", headers=ADMIN)
    assert r.json()["check_error"] and len(r.json()["tools"]) == 2
    assert (await api.delete(f"/v1/admin/mcp-servers/{srv['id']}", headers=ADMIN)).status_code == 204
    assert (await api.get("/v1/admin/mcp-servers", headers=ADMIN)).json()["servers"] == []
