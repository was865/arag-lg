"""テスト用の小さな MCP サーバ（本物の HTTP。specs/032）。身元のヘッダを確かめ、受け取った身元を返す。"""

import asyncio
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import jwt
import uvicorn
from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from starlette.types import ASGIApp, Receive, Scope, Send

KEY = "test-mcp-identity-key-0123456789abcdef"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class _Gate:
    def __init__(self, app: ASGIApp, audience: str, state: dict[str, Any]) -> None:
        self.app, self.audience, self.state = app, audience, state

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            if self.state.get("down"):
                await send({"type": "http.response.start", "status": 503, "headers": []})
                await send({"type": "http.response.body", "body": b""})
                return
            if self.state.get("slow"):
                await asyncio.sleep(float(self.state["slow"]))
            headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            auth = headers.get("authorization", "")
            try:
                claims = jwt.decode(auth.split(" ", 1)[1], KEY, algorithms=["HS256"], audience=self.audience)
            except Exception:
                await send({"type": "http.response.start", "status": 401, "headers": []})
                await send({"type": "http.response.body", "body": b""})
                return
            scope.setdefault("state", {})["claims"] = claims
        await self.app(scope, receive, send)


def make_server(state: dict[str, Any]) -> FastMCP:
    mcp = FastMCP(name="fake", host="0.0.0.0", stateless_http=True, json_response=True)
    ro = ToolAnnotations(readOnlyHint=True)

    @mcp.tool(annotations=ro)
    def get_stock(ctx: Context[Any, Any, Any], part: str) -> dict[str, Any]:
        """部品の現在の在庫。

        Args:
            part: 部品番号
        """
        claims = ctx.request_context.request.state.claims  # type: ignore[union-attr]
        if state.get("deny"):
            return {"system": "ERP", "error": "forbidden", "message": "見る権限がありません"}
        if state.get("too_many"):
            msg = "2400 件あり、上限（2000 件）を超えています"
            return {
                "system": "ERP",
                "error": "too_many",
                "message": msg,
                "total": 2400,
                "limit": 2000,
                "hint": "期間で絞ってください",
                "trace": {"id": "t1"},
            }
        if state.get("erp_down"):
            return {"system": "ERP", "error": "unavailable", "message": "ERP が 8 秒以内に応答しません"}
        rows = [[part, int(state.get("stock", 15)), 10]] * int(state.get("rows", 1))
        return {
            "system": "ERP",
            "title": "在庫",
            "fetched_at": "2026-11-18T10:32",
            "basis": "ERP の現在の値（2026-11-18 10:32 取得）",
            "columns": ["部品番号", "現在庫", "発注点"],
            "rows": rows,
            "total": len(rows),
            "caller": {"sub": claims["sub"], "depts": claims.get("depts", [])},
            **({"next_cursor": "50", "trace": {"id": "t2", "ms": 12}} if state.get("more") else {}),
            **(
                {"restricted": ["仕入単価（円）"], "note": "仕入単価を見る権限がありません"}
                if state.get("hide")
                else {}
            ),
        }

    @mcp.tool()
    def place_order(part: str, qty: int) -> str:
        """発注する（書き込み。読み取り専用の印なし）。"""
        return "ok"

    return mcp


@contextmanager
def running(audience: str = "erp") -> Iterator[tuple[str, dict[str, Any]]]:
    """(URL, 状態) を返す。状態の down / slow / deny / rows / hide でふるまいを変える。"""
    state: dict[str, Any] = {}
    port = free_port()
    app = _Gate(make_server(state).streamable_http_app(), audience, state)
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(200):
        if srv.started:
            break
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}/mcp", state
    finally:
        srv.should_exit = True
        t.join(timeout=5)
