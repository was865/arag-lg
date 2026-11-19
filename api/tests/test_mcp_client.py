"""MCP の client（specs/032 R6・R13・R17）。本物の HTTP の小さなサーバに繋ぐ。"""

import jwt
import pytest

from arag.mcp.client import (
    Caller,
    Endpoint,
    McpAuthError,
    McpTimeout,
    McpUnavailable,
    auth_headers,
    call_tool,
    list_tools,
)
from arag.mcp.registry import agent_tool_name, is_mcp_tool, server_of

from .mcp_fake import KEY, free_port, running

CALLER = Caller("u1", ("保全課",))


def _ep(url: str, name: str = "erp") -> Endpoint:
    return Endpoint(name=name, url=url, auth_kind="identity")


def test_identity_header_is_signed_for_the_server() -> None:
    h = auth_headers(_ep("http://x/mcp"), CALLER, KEY)
    claims = jwt.decode(h["Authorization"].split()[1], KEY, algorithms=["HS256"], audience="erp")
    assert claims["sub"] == "u1" and claims["depts"] == ["保全課"] and claims["exp"] - claims["iat"] <= 60
    with pytest.raises(McpAuthError):
        auth_headers(_ep("http://x/mcp"), CALLER, "")
    assert (
        auth_headers(Endpoint("x", "http://x", "bearer", "tok"), CALLER, "")["Authorization"] == "Bearer tok"
    )
    assert auth_headers(Endpoint("x", "http://x", "none"), CALLER, "") == {}


def test_agent_tool_names() -> None:
    assert agent_tool_name("erp", "get_stock") == "erp__get_stock"
    assert agent_tool_name("erp", "a.b/c") == "erp__a_b_c"
    assert is_mcp_tool("erp__get_stock") and not is_mcp_tool("search")
    assert server_of("erp__get_stock") == "erp"


async def test_list_and_call() -> None:
    with running() as (url, _state):
        ep = _ep(url)
        tools = {t.name: t for t in await list_tools(ep, auth_headers(ep, CALLER, KEY), 5)}
        assert tools["get_stock"].read_only and not tools["place_order"].read_only
        assert "part" in tools["get_stock"].input_schema["properties"]
        res = await call_tool(ep, auth_headers(ep, CALLER, KEY), "get_stock", {"part": "P-1042"}, 5)
        assert not res.is_error and res.data is not None
        assert res.data["rows"] == [["P-1042", 15, 10]]
        assert res.data["caller"] == {"sub": "u1", "depts": ["保全課"]}


async def test_wrong_audience_is_auth_error() -> None:
    with running("cmms") as (url, _):
        ep = _ep(url, "erp")
        with pytest.raises(McpAuthError):
            await list_tools(ep, auth_headers(ep, CALLER, KEY), 5)


async def test_down_and_closed_port_are_unavailable() -> None:
    with running() as (url, state):
        state["down"] = True
        ep = _ep(url)
        with pytest.raises(McpUnavailable):
            await list_tools(ep, auth_headers(ep, CALLER, KEY), 5)
    ep = _ep(f"http://127.0.0.1:{free_port()}/mcp")
    with pytest.raises(McpUnavailable):
        await list_tools(ep, auth_headers(ep, CALLER, KEY), 5)


async def test_slow_is_timeout() -> None:
    with running() as (url, state):
        state["slow"] = 2
        ep = _ep(url)
        with pytest.raises(McpTimeout):
            await call_tool(ep, auth_headers(ep, CALLER, KEY), "get_stock", {"part": "x"}, 0.5)
