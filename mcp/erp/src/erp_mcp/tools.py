"""ツールの層（specs/033 R2〜R5・R9〜R13・design §3）: アダプタの記録を 032 と同じ出力の形にする。

出力: system・title・fetched_at・basis・columns・rows・total・restricted・note に、続きの手がかり（next_cursor）と
呼び出しの記録（trace）を足したもの。失敗は error（forbidden・unavailable・too_many）と message で返す。
"""

import json
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any

from erp_mcp import clock, querylog
from erp_mcp.audit import Audit
from erp_mcp.config import UserMap
from erp_mcp.identity import Identity
from erp_mcp.model import ErpBackend, ErpError, ErpForbidden, ErpUser, PoLine, PoQuery, SoQuery, TooMany
from erp_mcp.ops import Guard, TtlCache

SYSTEM = "ERP"
CAP = 2000  # ERP から取る行の上限（R5）
PART_CAP = 30  # 在庫を見る部品の数の上限
PAGE = 50  # 1 回で返す行の既定の数

Table = dict[str, Any]


def _num(x: float | None) -> float | int | None:
    if x is None:
        return None
    return int(x) if float(x).is_integer() else round(x, 3)


def _qty(x: float, uom: str) -> str:
    n = _num(x)
    return f"{n}" if uom in ("", "個") else f"{n} {uom}"


class Service:
    def __init__(
        self,
        backend: ErpBackend,
        users: UserMap,
        audit: Audit,
        *,
        label: str = "ERP",
        guard: Guard | None = None,
        cache: TtlCache | None = None,
        usable: list[str] | None = None,
    ) -> None:
        self.backend, self.users, self.audit, self.label = backend, users, audit, label
        self.guard = guard or Guard()
        self.cache = cache or TtlCache()
        self.usable = frozenset(usable or ["WH2", "WH1"])

    # ── 共通の包み ──

    async def call(
        self,
        ident: Identity,
        tool: str,
        args: dict[str, Any],
        produce: Callable[[ErpUser], Awaitable[Table]],
        *,
        cursor: str = "",
        limit: int = PAGE,
    ) -> Table:
        who = self.users.pick(ident.depts)
        trace_id = uuid.uuid4().hex[:16]
        key = json.dumps([who.login, tool, args], ensure_ascii=False, sort_keys=True)
        t0 = time.perf_counter()
        cached = self.cache.get(key)
        kind = "ok"
        log = querylog.QueryLog()
        try:
            if cached is None:
                with querylog.collect() as log:
                    full = await self.guard.run(lambda: produce(who))
                full["fetched_at"] = clock.now().isoformat(timespec="seconds")
                full["basis"] = f"{self.label}の現在の値（{full['fetched_at'][:16].replace('T', ' ')} 取得）"
                self.cache.put(key, full)
            else:
                full = cached
            out = self._page(full, cursor, limit)
            rows = out["total"]
        except TooMany as e:
            kind, rows = "too_many", e.total
            out = self._error("too_many", str(e), total=e.total, limit=e.limit, hint=e.hint)
        except ErpError as e:
            kind, rows = e.kind, 0
            out = self._error(e.kind, str(e))
        ms = round((time.perf_counter() - t0) * 1000)
        out["trace"] = {
            "id": trace_id, "erp_user": who.login, "backend": self.backend.name, "ms": ms,
            "cached": cached is not None, "calls": 0 if cached is not None else out.pop("_calls", 1),
            # 発行した問い合わせ（specs/036 R3・R5）。使い回しの答えは何も発行していないので空
            **log.dump(),
        }  # fmt: skip
        out.pop("_calls", None)
        self.audit.write(
            trace=trace_id, user=ident.user_id, depts=sorted(ident.depts), kid=ident.kid, erp_user=who.login,
            backend=self.backend.name, tool=tool, args=args, cursor=cursor, result=kind, rows=rows, ms=ms,
            cached=cached is not None,
        )  # fmt: skip
        return out

    def _page(self, full: Table, cursor: str, limit: int) -> Table:
        rows = full["rows"]
        start = int(cursor) if cursor.isdigit() else 0
        end = start + max(1, min(limit, 200))
        out = {k: v for k, v in full.items() if k != "rows"}
        out["rows"] = rows[start:end]
        out["total"] = len(rows)
        if end < len(rows):
            out["next_cursor"] = str(end)
            extra = f'{start + 1}〜{end} 行目を返しました。続きは cursor="{end}" で呼んでください。'
            out["note"] = f"{out['note']} {extra}" if out.get("note") else extra
        return out

    def _error(self, kind: str, message: str, **extra: Any) -> Table:
        return {
            "system": SYSTEM, "error": kind, "message": message,
            "fetched_at": clock.now().isoformat(timespec="seconds"), **extra,
        }  # fmt: skip

    def _table(
        self, title: str, columns: list[str], rows: list[list[Any]], *, calls: int = 1,
        restricted: list[str] | None = None, note: str | None = None,
    ) -> Table:  # fmt: skip
        out: Table = {"system": SYSTEM, "title": title, "columns": columns, "rows": rows, "_calls": calls}
        if restricted:
            out["restricted"] = restricted
        if note:
            out["note"] = note
        return out

    def _hidden(self, who: ErpUser) -> tuple[list[str], str | None]:
        if "unit_cost" in who.hide:
            return ["仕入単価（円）"], who.hide_note or "仕入単価はこの利用者には見る権限がありません。"
        return [], None

    async def _parts(self, who: ErpUser, term: str, cap: int = PART_CAP) -> list[str]:
        found = await self.backend.find_parts(who, term, "", cap)
        return [p.part_no for p in found.items]

    # ── ツール ──

    async def find_parts(self, who: ErpUser, term: str, status: str) -> Table:
        f = await self.backend.find_parts(who, term, status, CAP)
        rows = [
            [p.part_no, p.name, p.models, _num(p.std_price), _num(p.reorder_point), p.supplier_code, p.status,
             p.successor, p.uom, p.purchase_uom]
            for p in f.items
        ]  # fmt: skip
        return self._table(
            "部品",
            [
                "部品番号",
                "名称",
                "適用機種",
                "標準単価（円）",
                "発注点",
                "仕入先コード",
                "状態",
                "後継",
                "単位",
                "発注の単位",
            ],
            rows,
            calls=f.calls,
            note=None if rows else f"「{term}」に当たる部品はありません",
        )

    async def get_stock(self, who: ErpUser, part: str) -> Table:
        found = await self.backend.find_parts(who, part, "", PART_CAP)
        nos = [p.part_no for p in found.items]
        stock = await self.backend.stock(who, nos)
        pos = await self.backend.on_order(who, nos)
        last = await self.backend.last_moves(who, nos)
        by: dict[str, dict[str, float]] = {}
        for s in stock.items:
            by.setdefault(s.part_no, {})[s.warehouse] = s.qty
        open_qty: dict[str, float] = {}
        for po in pos.items:
            open_qty[po.part_no] = open_qty.get(po.part_no, 0) + max(po.qty - po.received_qty, 0)
        rows = []
        for p in found.items:
            whs = by.get(p.part_no, {})
            usable = sum(q for w, q in whs.items() if w in self.usable)
            other = " / ".join(f"{w} {_num(q)}" for w, q in sorted(whs.items()) if w not in self.usable and q)
            if p.status == "廃止":
                judge = f"廃止（発注しない{'。後継 ' + p.successor if p.successor else ''}）"
            else:
                judge = "発注点を下回っている" if usable < p.reorder_point else "発注点を満たしている"
            m = last.items.get(p.part_no)
            rows.append(
                [
                    p.part_no, p.name, _num(usable), _num(p.reorder_point), judge,
                    _qty(open_qty.get(p.part_no, 0), p.uom),
                    f"{m.date.isoformat()} {m.kind} {_num(m.qty):+}" if m else "", p.uom,
                    f"{other}（使えない倉庫。在庫に数えない）" if other else "", p.purchase_uom,
                ]
            )  # fmt: skip
        return self._table(
            "在庫",
            ["部品番号", "名称", "現在庫", "発注点", "発注点との比較", "未入荷の発注数", "最後の入出庫", "単位",
             "使えない在庫", "発注の単位"],
            rows,
            calls=found.calls + stock.calls + pos.calls + last.calls,
            note=(
                f"「{part}」に当たる部品はありません" if not rows
                else f"現在庫は使える倉庫（{'・'.join(sorted(self.usable))}）の合計。"
            ),
        )  # fmt: skip

    async def list_below_reorder(self, who: ErpUser, without_orders: bool = False) -> Table:
        """使える倉庫の在庫が発注点を下回っている部品（廃止を除く）を全部、不足の大きい順に。

        部品ごとに get_stock を呼ばせない。without_orders なら未入荷の発注が無い部品だけ
        （「下回っていて発注もしていない部品」をモデルに数えさせない。デモの試走）。
        未入荷の発注数は在庫の単位の数（単位の列が別にある）。
        """
        found = await self.backend.find_parts(who, "", "通常", CAP)
        nos = [p.part_no for p in found.items]
        stock = await self.backend.stock(who, nos)
        pos = await self.backend.on_order(who, nos)
        usable: dict[str, float] = {}
        for s in stock.items:
            if s.warehouse in self.usable:
                usable[s.part_no] = usable.get(s.part_no, 0) + s.qty
        open_qty: dict[str, float] = {}
        for po in pos.items:
            open_qty[po.part_no] = open_qty.get(po.part_no, 0) + max(po.qty - po.received_qty, 0)
        short = [
            (p, q, open_qty.get(p.part_no, 0.0))
            for p in found.items
            if (q := usable.get(p.part_no, 0.0)) < p.reorder_point
        ]
        short.sort(key=lambda x: (-(x[0].reorder_point - x[1]), x[0].part_no))
        bare = sum(1 for _, _, o in short if o == 0)
        rows = [
            [p.part_no, p.name, _num(q), _num(p.reorder_point), _num(p.reorder_point - q), _num(o),
             p.supplier_code, p.uom]
            for p, q, o in short
            if not without_orders or o == 0
        ]  # fmt: skip
        return self._table(
            "発注点を下回る部品" + ("（未入荷の発注なし）" if without_orders else ""),
            ["部品番号", "名称", "現在庫", "発注点", "不足", "未入荷の発注数", "仕入先コード", "単位"],
            rows,
            calls=found.calls + stock.calls + pos.calls,
            note=(
                f"発注点を下回っている部品は {len(short)} 件、うち未入荷の発注が無いものは {bare} 件"
                f"（廃止の部品を除く）。{'未入荷の発注が無いものだけを載せた。' if without_orders else ''}"
                f"不足の大きい順。現在庫は使える倉庫（{'・'.join(sorted(self.usable))}）の合計。"
            ),
        )

    async def list_stock_moves(self, who: ErpUser, part: str, since: date | None, until: date | None) -> Table:
        nos = await self._parts(who, part)
        if not nos:
            return self._table("入出庫", [], [], note=f"「{part}」に当たる部品はありません")
        f = await self.backend.moves(who, nos, since, until, CAP)
        rows = [
            [m.date.isoformat(), m.part_no, m.name, m.kind, _num(m.qty), m.ref, m.note, m.warehouse] for m in f.items
        ]
        return self._table(
            "入出庫", ["日付", "部品番号", "名称", "種類", "数量", "参照", "備考", "倉庫"], rows, calls=f.calls + 1
        )

    def _po_status(self, po: PoLine) -> str:
        if po.status in ("発注済み", "一部入荷") and po.due_on < clock.today():
            return f"{po.status}（納期を過ぎて{'残りが' if po.status == '一部入荷' else ''}未入荷）"
        return po.status

    async def list_purchase_orders(self, who: ErpUser, q: PoQuery, overdue: bool) -> Table:
        if "purchase" in who.deny:
            raise ErpForbidden("この利用者には発注を見る権限がありません")
        nos = await self._parts(who, q.part, CAP) if q.part.strip() else None
        f = await self.backend.purchase_lines(who, q, nos, CAP)
        items = [
            po for po in f.items if not overdue or (po.status in ("発注済み", "一部入荷") and po.due_on < clock.today())
        ]
        restricted, note = self._hidden(who)
        cols = [
            "発注番号",
            "部品番号",
            "名称",
            "仕入先",
            "数量",
            "発注日",
            "納期",
            "入荷日",
            "状態",
            "入荷済みの数",
            "備考",
        ]
        if not restricted:
            cols.insert(5, "仕入単価（円）")
        rows = []
        for po in items:
            row: list[Any] = [
                po.po_no, po.part_no, po.name, po.supplier_name, _qty(po.qty, po.uom), po.ordered_on.isoformat(),
                po.due_on.isoformat(), po.received_on.isoformat() if po.received_on else "", self._po_status(po),
                _num(po.received_qty), po.note,
            ]  # fmt: skip
            if not restricted:
                row.insert(5, _num(po.unit_cost))
            rows.append(row)
        return self._table(
            "発注", cols, rows, calls=f.calls + (1 if nos is not None else 0), restricted=restricted,
            note=note if rows or restricted else "条件に当たる発注はありません",
        )  # fmt: skip

    async def list_sales_orders(self, who: ErpUser, q: SoQuery, overdue: bool) -> Table:
        nos = await self._parts(who, q.part, CAP) if q.part.strip() else None
        f = await self.backend.sales_lines(who, q, nos, CAP)
        today = clock.today()
        rows = []
        for so in f.items:
            late = so.status in ("受注済み", "一部出荷") and so.due_on < today
            if overdue and not late:
                continue
            status = f"{so.status}（納期を過ぎて未出荷）" if late else so.status
            rows.append(
                [so.so_no, so.customer, so.part_no, so.name, _num(so.qty), _num(so.shipped_qty),
                 _num(max(so.qty - so.shipped_qty, 0) if so.status != "取消" else 0), so.ordered_on.isoformat(),
                 so.due_on.isoformat(), status]
            )  # fmt: skip
        return self._table(
            "受注",
            ["受注番号", "顧客", "部品番号", "名称", "数量", "出荷済みの数", "残り", "受注日", "納期", "状態"],
            rows,
            calls=f.calls + (1 if nos is not None else 0),
            note=None if rows else "条件に当たる受注はありません",
        )

    async def list_suppliers(self, who: ErpUser, term: str) -> Table:
        f = await self.backend.suppliers(who, term)
        return self._table(
            "仕入先",
            ["仕入先コード", "仕入先名", "所在地", "リードタイム（日）", "担当者"],
            [[s.code, s.name, s.location, s.lead_days, s.contact] for s in f.items],
            calls=f.calls,
            note=None if f.items else f"「{term}」に当たる仕入先はありません",
        )
