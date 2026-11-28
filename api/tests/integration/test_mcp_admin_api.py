"""社内システム（MCP サーバ）の登録の管理 API（specs/032 R8〜R11）。"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.db.models import AuditLog, McpServer, McpTool
from arag.mcp.client import Caller
from arag.mcp.registry import load_held, load_tools, usable_server_ids
from arag.mcp.service import refresh_server
from arag.settings import Settings

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


async def _review(api: httpx.AsyncClient, srv: dict[str, Any], tool: str, **kw: Any) -> httpx.Response:
    cur = next(t for t in srv["tools"] if t["name"] == tool)
    body = {"tool": tool, "def_hash": cur["def_hash"], "side_effect": "read", "enabled": True} | kw
    return await api.post(f"/v1/admin/mcp-servers/{srv['id']}/tools/review", json=body, headers=ADMIN)


async def test_new_tools_are_unreviewed_until_admin_reviews(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    with running() as (url, _):
        srv = await _create(api, url)
    assert srv["check_error"] is None and srv["pending_review"] == 2
    tools = {t["name"]: t for t in srv["tools"]}
    # 新しいツールは未審査で渡さない（specs/038 R5）。サーバの印は参考として返す
    assert tools["get_stock"]["status"] == "unreviewed" and not tools["get_stock"]["usable"]
    assert tools["get_stock"]["read_only_hint"] and not tools["place_order"]["read_only_hint"]
    assert len(tools["get_stock"]["def_hash"]) == 64
    r = await api.put(
        f"/v1/admin/mcp-servers/{srv['id']}/tools", json={"enabled": ["get_stock"]}, headers=ADMIN
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_reviewed"
    async with sessionmaker() as s:
        assert await load_tools(s) == []
    # 審査: 副作用は管理者が決め、説明を書き換えられる（R7・R11）
    r = await _review(api, srv, "get_stock", model_description="部品番号で今の在庫を引く。")
    assert r.status_code == 200, r.text
    got = {t["name"]: t for t in r.json()["tools"]}["get_stock"]
    assert got["status"] == "approved" and got["usable"] and got["side_effect"] == "read"
    assert got["approved_hash"] == got["def_hash"] and got["approved_by"] and r.json()["pending_review"] == 1
    # 書き込みと決めたツールは使えない（R8）。印が無くても管理者が読み取りと決めれば使える
    w = await _review(api, srv, "place_order", side_effect="write", enabled=True)
    assert w.status_code == 422 and w.json()["error"]["code"] == "not_read"
    assert (await _review(api, srv, "place_order", side_effect="write", enabled=False)).status_code == 200
    r = await api.put(
        f"/v1/admin/mcp-servers/{srv['id']}/tools",
        json={"enabled": ["get_stock", "place_order"]},
        headers=ADMIN,
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_read"
    # 見ていた定義と違う指紋では審査できない（R9）
    moved = await _review(api, srv, "get_stock", def_hash="0" * 64)
    assert moved.status_code == 409 and moved.json()["error"]["code"] == "definition_moved"
    async with sessionmaker() as s:
        loaded = await load_tools(s)
        assert [t.agent_name for t in loaded] == ["erp__get_stock"]
        assert loaded[0].description == "部品番号で今の在庫を引く。"  # R12
        actions = set((await s.execute(select(AuditLog.action))).scalars())
        assert {"mcp.server.create", "mcp.tool.review"} <= actions


async def test_changed_definition_is_held_until_reviewed_again(
    api: httpx.AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    with running() as (url, _):
        srv = await _create(api, url)
        await _review(api, srv, "get_stock")
        # 審査した後に定義が変わったことにする（審査した指紋を別の値に）
        async with sessionmaker() as s:
            row = await s.get(McpTool, (uuid.UUID(srv["id"]), "get_stock"))
            assert row is not None
            row.def_hash = row.approved_hash = "f" * 64
            row.approved_description = "古い説明"
            await s.commit()
        r = await api.post(f"/v1/admin/mcp-servers/{srv['id']}/refresh", headers=ADMIN)
    out = r.json()
    got = {t["name"]: t for t in out["tools"]}["get_stock"]
    # 渡さないが「使う」の選択は残し、変わったことは接続の誤りに書かない（R4）
    assert got["status"] == "changed" and got["enabled"] and not got["usable"]
    assert got["approved_description"] == "古い説明" and out["check_error"] is None
    async with sessionmaker() as s:
        assert await load_tools(s) == []
        assert [(h.server, h.name) for h in await load_held(s)] == [("erp", "get_stock")]
        assert "mcp.tool.changed" in set((await s.execute(select(AuditLog.action))).scalars())
    # 審査し直すと戻る
    again = await _review(api, out, "get_stock")
    assert {t["name"]: t for t in again.json()["tools"]}["get_stock"]["usable"]
    async with sessionmaker() as s:
        assert await load_held(s) == []


async def test_cli_registration_approves_read_only_tools(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """登録の CLI は管理者の確認として扱い、印のあるツールを読み取りで使う（R6）。"""
    settings = Settings(mcp_identity_key=KEY)
    with running() as (url, _):
        async with sessionmaker() as s:
            srv = McpServer(name="erp", label="ERP", url=url, auth_kind="identity", created_by="t")
            s.add(srv)
            await s.flush()
            changed = await refresh_server(s, settings, srv, Caller("arag-cli"), accept_changes=True)
            await s.commit()
    assert changed == []
    async with sessionmaker() as s:
        rows = {t.name: t for t in (await s.execute(select(McpTool))).scalars()}
    assert rows["get_stock"].usable and rows["get_stock"].approved_by == "arag-cli"
    assert rows["place_order"].status == "unreviewed" and not rows["place_order"].enabled


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
