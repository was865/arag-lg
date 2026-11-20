"""4 つの模擬の社内システムを MCP サーバ（Streamable HTTP）として出す（specs/032 R6・R7・R13）。

どのツールも読み取りだけ（readOnlyHint）。要求ごとに `Authorization: Bearer <身元>` を確かめ、身元で列・行を絞る。
障害の注入（R7）: MOCK_FAULTS="cmms=down,erp=slow:15,tickets=deny" か、MOCK_ADMIN=1 のとき POST /_faults。
"""

import asyncio
import json
import os
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from mock_systems import queries as q
from mock_systems.common import Identity, IdentityError, forbidden, open_ro, traced, verify_identity

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

# サーバ名（身元の aud）→ 表示名・DB のファイル・ポート
SYSTEMS: dict[str, tuple[str, str, int]] = {
    "erp": (q.ERP, "erp.db", 8201),
    "cmms": (q.CMMS, "cmms.db", 8202),
    "directory": (q.DIRECTORY, "directory.db", 8203),
    "tickets": (q.TICKETS, "tickets.db", 8204),
}


# ── 障害の注入 ──


class Faults:
    """システムごとの障害: down（503）・slow:N（N 秒待つ）・deny（すべて権限なし）。"""

    def __init__(self, spec: str = "") -> None:
        self.state: dict[str, str] = {}
        self.set_spec(spec)

    def set_spec(self, spec: str) -> None:
        self.state = {}
        for part in spec.split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                self.state[k.strip()] = v.strip()

    def get(self, system: str) -> str:
        return self.state.get(system, "")


FAULTS = Faults(os.environ.get("MOCK_FAULTS", ""))


def _identity(ctx: Context[Any, Any, Any]) -> Identity:
    req = ctx.request_context.request
    ident = getattr(getattr(req, "state", None), "identity", None)
    if not isinstance(ident, Identity):
        raise IdentityError("身元がありません")
    return ident


class Gate:
    """ASGI の前段: 障害の注入・身元の確認・評価用の管理口。"""

    def __init__(self, app: ASGIApp, system: str, key: str) -> None:
        self.app, self.system, self.key = app, system, key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path == "/healthz":
            await _json(send, 200, {"ok": True, "system": self.system})
            return
        if path == "/_faults" and os.environ.get("MOCK_ADMIN") == "1":
            req = Request(scope, receive)
            if scope["method"] == "POST":
                body = await req.body()
                data = json.loads(body or b"{}")
                FAULTS.set_spec(",".join(f"{k}={v}" for k, v in data.items() if v))
            await _json(send, 200, FAULTS.state)
            return
        fault = FAULTS.get(self.system)
        if fault == "down":
            await _json(send, 503, {"error": "unavailable"})
            return
        if fault.startswith("slow:"):
            await asyncio.sleep(float(fault.split(":", 1)[1]))
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        try:
            ident = verify_identity(headers.get("authorization"), audience=self.system, key=self.key)
        except IdentityError as e:
            await _json(send, 401, {"error": "unauthorized", "message": str(e)})
            return
        scope.setdefault("state", {})["identity"] = ident
        scope["state"]["deny"] = fault == "deny"
        await self.app(scope, receive, send)


async def _json(send: Send, status: int, body: dict[str, Any]) -> None:
    raw = json.dumps(body, ensure_ascii=False).encode()
    await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": raw})


# ── サーバ ──


def _call(
    ctx: Context[Any, Any, Any], system: str, con: sqlite3.Connection, fn: Callable[..., dict[str, Any]], **kw: Any
) -> dict[str, Any]:
    ident = _identity(ctx)
    req = ctx.request_context.request
    if getattr(getattr(req, "state", None), "deny", False):
        return forbidden(SYSTEMS[system][0], "この利用者にはこのシステムを見る権限がありません。")
    return traced(fn, con, ident, **kw)


def create(system: str, data_dir: Path) -> FastMCP:
    label, db, _ = SYSTEMS[system]
    con = open_ro(data_dir / db)
    mcp = FastMCP(
        name=f"harukaze-{system}",
        instructions=f"株式会社ハルカゼ精工 浜松第二工場の{label}（模擬）。読み取りだけ。",
        host="0.0.0.0",
        stateless_http=True,
        json_response=True,
    )

    def tool(fn: Callable[..., Any]) -> Callable[..., Any]:
        return mcp.tool(annotations=READ_ONLY)(fn)

    if system == "erp":

        @tool
        def find_parts(ctx: Context[Any, Any, Any], term: str = "") -> dict[str, Any]:
            """部品の一覧（部品番号・名称・適用機種・標準単価・発注点・仕入先・状態）。

            Args:
                term: 部品番号・名称・適用機種の一部（例 "SK-300"、"軸受"、"HP-320"）。空なら全部品
            """
            return _call(ctx, system, con, q.find_parts, term=term)

        @tool
        def get_stock(ctx: Context[Any, Any, Any], part: str) -> dict[str, Any]:
            """部品の現在の在庫・発注点・発注点との比較・未入荷の発注数。今の在庫を問われたらこれを使う。
            単価は出さない（発注の仕入単価は list_purchase_orders）。

            Args:
                part: 部品番号か名称の一部（例 "P-1042"、"SK-300"、"6309ZZ"）
            """
            return _call(ctx, system, con, q.get_stock, part=part)

        @tool
        def list_stock_moves(
            ctx: Context[Any, Any, Any], part: str, since: str = "", until: str = ""
        ) -> dict[str, Any]:
            """部品の入出庫の履歴（棚卸・入庫・出庫・廃棄）。

            Args:
                part: 部品番号か名称の一部
                since: この日以降（YYYY-MM-DD。省略可）
                until: この日まで（YYYY-MM-DD。省略可）
            """
            return _call(ctx, system, con, q.list_stock_moves, part=part, since=since, until=until)

        @tool
        def list_purchase_orders(
            ctx: Context[Any, Any, Any], part: str = "", status: str = "", since: str = "", until: str = ""
        ) -> dict[str, Any]:
            """購買の発注（発注番号・部品・仕入先・数量・発注日・納期・入荷日・状態）。仕入単価は権限のある人だけに出る。

            Args:
                part: 部品番号か名称の一部（省略可）
                status: 「発注済み」（未入荷）か「入荷済み」（省略可）
                since: 発注日がこの日以降（YYYY-MM-DD。省略可）
                until: 発注日がこの日まで（YYYY-MM-DD。省略可）
            """
            return _call(ctx, system, con, q.list_purchase_orders, part=part, status=status, since=since, until=until)

    elif system == "cmms":

        @tool
        def list_equipment(ctx: Context[Any, Any, Any]) -> dict[str, Any]:
            """設備の一覧（設備ID・設備名・設置場所・導入年）。"""
            return _call(ctx, system, con, q.list_equipment)

        @tool
        def list_work_records(
            ctx: Context[Any, Any, Any], equipment: str = "", since: str = "", until: str = ""
        ) -> dict[str, Any]:
            """設備の保全作業の記録（日付・作業内容・担当・停止時間・使った手順書）。

            Args:
                equipment: 設備ID か設備名の一部（例 "PM-04"。省略可）
                since: この日以降（YYYY-MM-DD。省略可）
                until: この日まで（YYYY-MM-DD。省略可）
            """
            return _call(ctx, system, con, q.list_work_records, equipment=equipment, since=since, until=until)

        @tool
        def list_work_orders(ctx: Context[Any, Any, Any], equipment: str = "", status: str = "") -> dict[str, Any]:
            """作業指示（これからの作業・作業中のものを含む）。保全課・製造課の人だけが見られる。

            Args:
                equipment: 設備ID（省略可）
                status: 「未着手」「作業中」「完了」か「未完了」（省略可）
            """
            return _call(ctx, system, con, q.list_work_orders, equipment=equipment, status=status)

    elif system == "directory":

        @tool
        def find_people(ctx: Context[Any, Any, Any], term: str) -> dict[str, Any]:
            """社員を探す（氏名・部署・役職・内線）。

            Args:
                term: 氏名・部署・役職の一部（例 "高梨"、"保全課"、"課長"）
            """
            return _call(ctx, system, con, q.find_people, term=term)

    elif system == "tickets":

        @tool
        def search_issues(ctx: Context[Any, Any, Any], term: str = "", status: str = "") -> dict[str, Any]:
            """課題（会議の決定事項・不具合の対策・不良率などの目標）を探す。件名・出どころ・担当・期限・状態・最新の経過。
            決定事項や目標の今の進み具合・達成の状況はここで確かめる。経過のすべては get_issue で読む。

            Args:
                term: 件名・出どころ・課題番号の一部（例 "品質会議"、"不良率"、"SK-300"。空なら全件）
                status: 「完了」「対応中」「継続中」か「未完了」（省略可）
            """
            return _call(ctx, system, con, q.search_issues, term=term, status=status)

        @tool
        def get_issue(ctx: Context[Any, Any, Any], issue: str) -> dict[str, Any]:
            """課題 1 件と、その経過のコメント（会議での確認の結果・実績の値など）。

            Args:
                issue: 課題番号（例 "Q-002"）
            """
            return _call(ctx, system, con, q.get_issue, issue=issue)

    return mcp


def asgi_app(system: str, data_dir: Path, key: str) -> ASGIApp:
    return Gate(create(system, data_dir).streamable_http_app(), system, key)
