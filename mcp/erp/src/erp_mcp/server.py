"""ERP の MCP サーバ（specs/033 R1〜R3・R8・R14、design §3）。Streamable HTTP・要求をまたぐ状態を持たない。

道具は業務の単位の読み取りだけ（readOnlyHint）。汎用の検索・SQL・項目名を自由に指定する問い合わせ・書き込みは出さない。
入口（Gate）で身元の JWT（aud・exp・kid）を確かめ、無い・不正なら何も返さない。死活の確認は GET /health。
"""

import json
import os
import time
from datetime import date
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.types import ASGIApp, Receive, Scope, Send

from erp_mcp.identity import Identity, IdentityError, verify
from erp_mcp.model import PoQuery, SoQuery
from erp_mcp.tools import Service

NAME = "erp"  # 身元の aud
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

Day = Annotated[str, Field(pattern=r"^(\d{4}-\d{2}-\d{2})?$", description="YYYY-MM-DD（省略可）")]
Cursor = Annotated[str, Field(pattern=r"^\d*$", description="続きの手がかり（前の結果の next_cursor。省略可）")]
Limit = Annotated[int, Field(ge=1, le=200, description="1 回で返す行の数（既定 50）")]
Term = Annotated[str, Field(max_length=80)]


def _day(s: str) -> date | None:
    return date.fromisoformat(s) if s else None


def _identity(ctx: Context[Any, Any, Any]) -> Identity:
    req = ctx.request_context.request
    ident = getattr(getattr(req, "state", None), "identity", None)
    if not isinstance(ident, Identity):
        raise IdentityError("身元がありません")
    return ident


def create(service: Service, *, label: str) -> FastMCP:
    mcp = FastMCP(
        name=f"harukaze-{NAME}",
        instructions=(
            f"株式会社ハルカゼ精工の ERP（{label}）。部品・在庫・入出庫・発注・受注・仕入先を、いまの値として読み取るだけ。"
        ),
        host="0.0.0.0",
        stateless_http=True,
        json_response=True,
    )

    def tool(fn: Any) -> Any:
        return mcp.tool(annotations=READ_ONLY)(fn)

    # 道具は決まった順で登録する（一覧の順が変わらない）

    @tool
    async def find_parts(
        ctx: Context[Any, Any, Any],
        term: Term = "",
        status: Literal["", "通常", "廃止"] = "",
        cursor: Cursor = "",
        limit: Limit = 50,
    ) -> dict[str, Any]:
        """部品を探す（部品番号・名称・適用機種・標準単価・発注点・仕入先コード・状態・後継・単位）。
        部品番号が分からないとき、似た名前（6308ZZ と 6308ZZ-C3 など）を見分けるときに使う。在庫の数は出さない（get_stock）。

        Args:
            term: 部品番号・名称（日本語か英語）・適用機種の一部（例 "SK-300"、"軸受 6308"、"HP-400"）。空なら全部品
            status: 「通常」か「廃止」（省略可）
        """
        args = {"term": term, "status": status}
        return await service.call(
            _identity(ctx), "find_parts", args, lambda who: service.find_parts(who, term, status),
            cursor=cursor, limit=limit,
        )  # fmt: skip

    @tool
    async def get_stock(ctx: Context[Any, Any, Any], part: Term) -> dict[str, Any]:
        """部品のいまの在庫（使える倉庫の合計）・発注点との比較・未入荷の発注数・最後の入出庫・使えない倉庫の在庫。
        今の在庫・足りているかを問われたらこれを使う。単価は出さない（発注の仕入単価は list_purchase_orders）。

        Args:
            part: 部品番号か名称の一部（例 "P-1042"、"SK-300"、"6309ZZ"）。当たる部品が 30 を超えるときは絞る
        """
        return await service.call(_identity(ctx), "get_stock", {"part": part}, lambda who: service.get_stock(who, part))

    @tool
    async def list_below_reorder(
        ctx: Context[Any, Any, Any], without_orders: bool = False, cursor: Cursor = "", limit: Limit = 50
    ) -> dict[str, Any]:
        """今、発注点を下回っている部品の一覧（現在庫・発注点・不足・未入荷の発注数・仕入先）。不足の大きい順。
        廃止の部品は除く。「発注点を下回っている部品は何件・どれ」と問われたらこれを 1 回だけ使う
        （部品ごとに get_stock を呼ばない）。件数は total を答える。1 つの部品の詳しい在庫は get_stock。

        Args:
            without_orders: true なら未入荷の発注が無い部品だけ（「下回っていて発注もしていない部品」）
        """
        return await service.call(
            _identity(ctx), "list_below_reorder", {"without_orders": without_orders},
            lambda who: service.list_below_reorder(who, without_orders), cursor=cursor, limit=limit,
        )  # fmt: skip

    @tool
    async def list_stock_moves(
        ctx: Context[Any, Any, Any],
        part: Term,
        since: Day = "",
        until: Day = "",
        cursor: Cursor = "",
        limit: Limit = 50,
    ) -> dict[str, Any]:
        """部品の入出庫の履歴（棚卸・入庫・出庫・製造出庫・製造入庫・保全出庫・廃棄・移動）と倉庫。

        Args:
            part: 部品番号か名称の一部
            since: この日以降（YYYY-MM-DD。省略可）
            until: この日まで（YYYY-MM-DD。省略可）
        """
        args = {"part": part, "since": since, "until": until}
        return await service.call(
            _identity(ctx), "list_stock_moves", args,
            lambda who: service.list_stock_moves(who, part, _day(since), _day(until)), cursor=cursor, limit=limit,
        )  # fmt: skip

    @tool
    async def list_purchase_orders(
        ctx: Context[Any, Any, Any],
        po_no: Term = "",
        part: Term = "",
        supplier: Term = "",
        status: Literal["", "発注済み", "一部入荷", "入荷済み", "取消", "未完了"] = "",
        since: Day = "",
        until: Day = "",
        overdue: bool = False,
        cursor: Cursor = "",
        limit: Limit = 50,
    ) -> dict[str, Any]:
        """購買の発注（発注番号・部品・仕入先・数量・発注日・納期・入荷日・状態・入荷済みの数・備考）。
        仕入単価は権限のある人だけに出る。未入荷・納期遅れ・分けて届いた入荷・仕入単価の変化はこれで確かめる。

        Args:
            po_no: 発注番号（例 "PO-2026-2241"。1 件の発注の今の状態を問われたら、これだけを渡す。省略可）
            part: 部品番号か名称の一部（省略可）
            supplier: 仕入先コードか仕入先名の一部（例 "S-07"、"Aster"。省略可）
            status: 「未完了」は発注済みと一部入荷（省略可）
            since: 発注日がこの日以降（YYYY-MM-DD。省略可）
            until: 発注日がこの日まで（YYYY-MM-DD。省略可）
            overdue: true なら、納期を過ぎても入荷していない（残りがある）発注だけ
        """
        q = PoQuery(part, supplier, status, _day(since), _day(until), po_no)
        args = {
            "po_no": po_no,
            "part": part,
            "supplier": supplier,
            "status": status,
            "since": since,
            "until": until,
            "overdue": overdue,
        }
        return await service.call(
            _identity(ctx), "list_purchase_orders", args, lambda who: service.list_purchase_orders(who, q, overdue),
            cursor=cursor, limit=limit,
        )  # fmt: skip

    @tool
    async def list_sales_orders(
        ctx: Context[Any, Any, Any],
        customer: Term = "",
        part: Term = "",
        status: Literal["", "受注済み", "一部出荷", "出荷済み", "取消", "未完了"] = "",
        since: Day = "",
        until: Day = "",
        overdue: bool = False,
        cursor: Cursor = "",
        limit: Limit = 50,
    ) -> dict[str, Any]:
        """受注（受注番号・顧客・部品・数量・出荷済みの数・残り・受注日・納期・状態）。製品（ポンプ）と補修部品の注文。

        Args:
            customer: 顧客コードか顧客名の一部（省略可）
            part: 部品番号か名称の一部（例 "FG-300"、"HP-300"。省略可）
            status: 「未完了」は受注済みと一部出荷（省略可）
            since: 受注日がこの日以降（YYYY-MM-DD。省略可）
            until: 受注日がこの日まで（YYYY-MM-DD。省略可）
            overdue: true なら、納期を過ぎても出荷していない受注だけ
        """
        q = SoQuery(customer, part, status, _day(since), _day(until))
        args = {
            "customer": customer,
            "part": part,
            "status": status,
            "since": since,
            "until": until,
            "overdue": overdue,
        }
        return await service.call(
            _identity(ctx), "list_sales_orders", args, lambda who: service.list_sales_orders(who, q, overdue),
            cursor=cursor, limit=limit,
        )  # fmt: skip

    @tool
    async def list_suppliers(ctx: Context[Any, Any, Any], term: Term = "") -> dict[str, Any]:
        """仕入先（仕入先コード・名前・所在地・リードタイム・担当者）。

        Args:
            term: 仕入先コード・名前・所在地の一部（空なら全件）
        """
        return await service.call(
            _identity(ctx), "list_suppliers", {"term": term}, lambda who: service.list_suppliers(who, term)
        )

    return mcp


class Gate:
    """ASGI の前段: 死活の確認・身元の確認。"""

    def __init__(self, app: ASGIApp, service: Service, keys: dict[str, str]) -> None:
        self.app, self.service, self.keys = app, service, keys

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path == "/healthz":
            await _json(send, 200, {"ok": True})
            return
        if path == "/health":
            await _json(send, 200, await health(self.service))
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        try:
            ident = verify(headers.get("authorization"), audience=NAME, keys=self.keys)
        except IdentityError as e:
            await _json(send, 401, {"error": "unauthorized", "message": str(e)})
            return
        scope.setdefault("state", {})["identity"] = ident
        await self.app(scope, receive, send)


async def health(service: Service) -> dict[str, Any]:
    """ERP までつながるか・所要時間・止める仕組みの状態（R14）。"""
    t = time.perf_counter()
    try:
        h = await service.guard.run(service.backend.health)
        return {
            "ok": h.ok, "backend": service.backend.name, "version": h.version, "ms": h.ms, "detail": h.detail,
            "breaker": service.guard.breaker.state,
        }  # fmt: skip
    except Exception as e:
        return {
            "ok": False, "backend": service.backend.name, "error": str(e),
            "ms": round((time.perf_counter() - t) * 1000), "breaker": service.guard.breaker.state,
        }  # fmt: skip


async def _json(send: Send, status: int, body: dict[str, Any]) -> None:
    raw = json.dumps(body, ensure_ascii=False).encode()
    await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": raw})


def asgi_app(service: Service, keys: dict[str, str], *, label: str) -> ASGIApp:
    return Gate(create(service, label=label).streamable_http_app(), service, keys)


def env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))
