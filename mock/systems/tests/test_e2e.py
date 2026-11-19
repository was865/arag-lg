"""本物の HTTP と MCP の client で、身元・読み取り専用の印・障害の注入を確かめる（R6・R7・R13）。"""

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from mock_systems.common import issue_identity
from mock_systems.servers import FAULTS, asgi_app

from .conftest import KEY


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def urls(data_dir: Path) -> Iterator[dict[str, str]]:
    servers, out = [], {}
    for name in ("erp", "cmms"):
        port = _free_port()
        srv = uvicorn.Server(
            uvicorn.Config(asgi_app(name, data_dir, KEY), host="127.0.0.1", port=port, log_level="warning")
        )
        threading.Thread(target=srv.run, daemon=True).start()
        servers.append(srv)
        out[name] = f"http://127.0.0.1:{port}"
    for s in servers:
        for _ in range(100):
            if s.started:
                break
            time.sleep(0.05)
    yield out
    for s in servers:
        s.should_exit = True


async def _session(url: str, system: str, depts: list[str]):  # type: ignore[no-untyped-def]
    tok = issue_identity("u-e2e", depts, audience=system, key=KEY)
    return httpx.AsyncClient(headers={"Authorization": f"Bearer {tok}"}, timeout=5)


async def _call(url: str, system: str, depts: list[str], tool: str | None = None, args: dict | None = None):  # type: ignore[no-untyped-def,type-arg]
    async with (
        await _session(url, system, depts) as http,
        streamable_http_client(f"{url}/mcp", http_client=http) as (r, w, _),
        ClientSession(r, w) as s,
    ):
        await s.initialize()
        if tool is None:
            return await s.list_tools()
        return await s.call_tool(tool, args or {})


async def test_tools_are_read_only(urls: dict[str, str]) -> None:
    tools = (await _call(urls["erp"], "erp", [])).tools
    assert {t.name for t in tools} == {"find_parts", "get_stock", "list_stock_moves", "list_purchase_orders"}
    assert all(t.annotations and t.annotations.readOnlyHint for t in tools)
    assert all(t.description for t in tools)


async def test_call_with_identity(urls: dict[str, str]) -> None:
    res = await _call(urls["erp"], "erp", ["製造課"], "get_stock", {"part": "SK-300"})
    assert res.structuredContent is not None
    data = res.structuredContent.get("result", res.structuredContent)
    assert data["rows"][0][2] == 15
    res = await _call(urls["cmms"], "cmms", ["購買課"], "list_work_orders", {})
    data = res.structuredContent.get("result", res.structuredContent)  # type: ignore[union-attr]
    assert data["error"] == "forbidden"


async def test_rejects_without_identity(urls: dict[str, str]) -> None:
    async with httpx.AsyncClient() as http:
        r = await http.post(f"{urls['erp']}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert r.status_code == 401
    # 別のシステム宛の身元も通さない
    tok = issue_identity("u", [], audience="cmms", key=KEY)
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {tok}"}) as http:
        r = await http.post(f"{urls['erp']}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert r.status_code == 401


async def test_fault_down_and_deny(urls: dict[str, str]) -> None:
    FAULTS.set_spec("erp=down,cmms=deny")
    try:
        async with httpx.AsyncClient() as http:
            assert (await http.post(f"{urls['erp']}/mcp", json={})).status_code == 503
        res = await _call(urls["cmms"], "cmms", ["保全課"], "list_equipment", {})
        data = res.structuredContent.get("result", res.structuredContent)  # type: ignore[union-attr]
        assert data["error"] == "forbidden"
    finally:
        FAULTS.set_spec("")
