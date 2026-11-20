"""模擬のアダプタ（specs/033 R6）: 034 の大きい世界の SQLite（032 の表の上位の形）を読む。

ERP の権限は設定（mock.yaml の rights）で真似る。Odoo のアダプタと同じ契約のテストを通る。
"""

import asyncio
import sqlite3
import time
from datetime import date
from pathlib import Path
from typing import Any

from erp_mcp import querylog
from erp_mcp.clock import today
from erp_mcp.model import (
    ErpForbidden,
    ErpUser,
    Fetch,
    Health,
    LastMoves,
    MoveRec,
    Part,
    PoLine,
    PoQuery,
    SoLine,
    SoQuery,
    StockLine,
    Supplier,
    TooMany,
)

OPEN_PO = ("発注済み", "一部入荷")
OPEN_SO = ("受注済み", "一部出荷")


def _like(term: str) -> str:
    return "%" + term.replace("%", "").replace("_", "").strip() + "%"


def _d(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


class MockBackend:
    name = "mock"

    def __init__(self, db: Path, rights: dict[str, list[str]], usable: list[str]) -> None:
        self.con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        # 発行した SQL（値を埋め込んだ文）を呼び出しごとに記録する（specs/036 R3）
        self.con.set_trace_callback(querylog.sql_trace)
        self.rights = {k: frozenset(v) for k, v in rights.items()}
        self.usable = frozenset(usable)

    def _check(self, who: ErpUser, area: str) -> None:
        if area not in self.rights.get(who.login, frozenset()):
            raise ErpForbidden(f"ERP の利用者 {who.login} には {area} を読む権限がありません")

    def _rows(self, sql: str, args: list[Any]) -> list[sqlite3.Row]:
        return list(self.con.execute(sql, args))

    async def find_parts(self, who: ErpUser, term: str, status: str, cap: int) -> Fetch[Part]:
        self._check(who, "parts")
        sql = " FROM parts p LEFT JOIN suppliers s ON s.code = p.supplier_code WHERE 1 = 1"
        args: list[Any] = []
        if term.strip():
            q = _like(term)
            sql += " AND (p.part_no LIKE ? OR p.name LIKE ? OR p.name_en LIKE ? OR p.models LIKE ?)"
            args += [q, q, q, q]
        if status:
            sql += " AND p.status = ?"
            args.append(status)
        total = self.con.execute("SELECT COUNT(*)" + sql, args).fetchone()[0]
        if total > cap:
            raise TooMany(total, cap, "部品番号・名称の一部・状態で絞ってください")
        rows = self._rows("SELECT p.*, s.name AS supplier_name" + sql + " ORDER BY p.part_no", args)
        return Fetch(
            [
                Part(
                    r["part_no"],
                    r["name"],
                    r["name_en"] or "",
                    r["models"] or "",
                    r["category"] or "",
                    None if "std_price" in who.hide else r["std_price"],
                    r["reorder_point"],
                    r["supplier_code"] or "",
                    r["supplier_name"] or "",
                    r["status"],
                    r["successor"] or "",
                    r["uom"],
                    r["purchase_uom"],
                )
                for r in rows
            ]
        )

    async def stock(self, who: ErpUser, part_nos: list[str]) -> Fetch[StockLine]:
        self._check(who, "stock")
        if not part_nos:
            return Fetch([])
        marks = ",".join("?" for _ in part_nos)
        rows = self._rows(
            f"SELECT part_no, warehouse, SUM(qty) AS q FROM stock_moves WHERE part_no IN ({marks}) AND date <= ?"
            " GROUP BY part_no, warehouse",
            [*part_nos, today().isoformat()],
        )
        return Fetch([StockLine(r["part_no"], r["warehouse"], round(r["q"], 3)) for r in rows if abs(r["q"]) > 1e-9])

    def _po(self, who: ErpUser, r: sqlite3.Row) -> PoLine:
        return PoLine(
            r["po_no"], r["part_no"], r["name"], r["supplier_code"], r["supplier_name"], r["qty"], r["uom"],
            r["received_qty"], None if "unit_cost" in who.hide else r["unit_cost"], date.fromisoformat(r["ordered_on"]),
            date.fromisoformat(r["due_on"]), _d(r["received_on"]), r["status"], r["note"] or "",
        )  # fmt: skip

    _PO_SQL = (
        " FROM purchase_orders o JOIN parts p USING (part_no) JOIN suppliers s ON s.code = o.supplier_code WHERE 1 = 1"
    )

    async def on_order(self, who: ErpUser, part_nos: list[str]) -> Fetch[PoLine]:
        """入荷の予定（在庫の単位に直した残り）。購買の権限が無くても在庫の権限で見える（Odoo の入荷予定と同じ）。"""
        self._check(who, "stock")
        if not part_nos:
            return Fetch([])
        marks = ",".join("?" for _ in part_nos)
        rows = self._rows(
            "SELECT o.po_no, o.part_no, (o.qty - o.received_qty) * p.purchase_ratio AS left, o.ordered_on, o.due_on, p.uom"
            f" FROM purchase_orders o JOIN parts p USING (part_no) WHERE o.part_no IN ({marks}) AND o.status IN (?, ?)"
            " ORDER BY o.ordered_on",
            [*part_nos, *OPEN_PO],
        )
        return Fetch(
            [
                PoLine(
                    r["po_no"],
                    r["part_no"],
                    "",
                    "",
                    "",
                    r["left"],
                    r["uom"],
                    0.0,
                    None,
                    date.fromisoformat(r["ordered_on"]),
                    date.fromisoformat(r["due_on"]),
                    None,
                    "発注済み",
                )
                for r in rows
            ]
        )

    async def last_moves(self, who: ErpUser, part_nos: list[str]) -> LastMoves:
        self._check(who, "moves")
        out: dict[str, MoveRec] = {}
        for no in part_nos:
            r = self.con.execute(
                "SELECT m.*, p.name FROM stock_moves m JOIN parts p USING (part_no) WHERE m.part_no = ? AND m.date <= ?"
                " ORDER BY m.date DESC, m.rowid DESC LIMIT 1",
                (no, today().isoformat()),
            ).fetchone()
            if r is not None:
                out[no] = MoveRec(
                    date.fromisoformat(r["date"]), no, r["name"], r["kind"], r["qty"], r["ref"] or "", r["note"] or "",
                    r["warehouse"],
                )  # fmt: skip
        return LastMoves(out)

    async def moves(
        self, who: ErpUser, part_nos: list[str], since: date | None, until: date | None, cap: int
    ) -> Fetch[MoveRec]:
        self._check(who, "moves")
        if not part_nos:
            return Fetch([])
        marks = ",".join("?" for _ in part_nos)
        sql = (
            f" FROM stock_moves m JOIN parts p USING (part_no) WHERE m.part_no IN ({marks}) AND m.date BETWEEN ? AND ?"
        )
        args = [*part_nos, (since or date(1, 1, 1)).isoformat(), (until or date(9999, 12, 31)).isoformat()]
        total = self.con.execute("SELECT COUNT(*)" + sql, args).fetchone()[0]
        if total > cap:
            raise TooMany(total, cap, "期間（since・until）を短くしてください")
        rows = self._rows("SELECT m.*, p.name" + sql + " ORDER BY m.date, m.part_no, m.rowid", args)
        return Fetch(
            [
                MoveRec(
                    date.fromisoformat(r["date"]),
                    r["part_no"],
                    r["name"],
                    r["kind"],
                    r["qty"],
                    r["ref"] or "",
                    r["note"] or "",
                    r["warehouse"],
                )
                for r in rows
            ]
        )

    async def purchase_lines(self, who: ErpUser, q: PoQuery, part_nos: list[str] | None, cap: int) -> Fetch[PoLine]:
        self._check(who, "purchase")
        sql = self._PO_SQL
        args: list[Any] = []
        if part_nos is not None:
            sql += f" AND o.part_no IN ({','.join('?' for _ in part_nos) or 'NULL'})"
            args += part_nos
        if q.po_no.strip():
            sql += " AND o.po_no = ?"
            args.append(q.po_no.strip().upper())
        if q.supplier.strip():
            sql += " AND (s.code = ? OR s.name LIKE ?)"
            args += [q.supplier.strip(), _like(q.supplier)]
        if q.status == "未完了":
            sql += " AND o.status IN (?, ?)"
            args += list(OPEN_PO)
        elif q.status:
            sql += " AND o.status = ?"
            args.append(q.status)
        sql += " AND o.ordered_on BETWEEN ? AND ?"
        args += [(q.since or date(1, 1, 1)).isoformat(), (q.until or today()).isoformat()]
        total = self.con.execute("SELECT COUNT(*)" + sql, args).fetchone()[0]
        if total > cap:
            raise TooMany(total, cap, "部品・仕入先・状態・期間で絞ってください")
        rows = self._rows("SELECT o.*, p.name, s.name AS supplier_name" + sql + " ORDER BY o.ordered_on, o.po_no", args)
        return Fetch([self._po(who, r) for r in rows])

    async def sales_lines(self, who: ErpUser, q: SoQuery, part_nos: list[str] | None, cap: int) -> Fetch[SoLine]:
        self._check(who, "sales")
        sql = (
            " FROM sales_orders o JOIN parts p USING (part_no) JOIN customers c ON c.code = o.customer_code WHERE 1 = 1"
        )
        args: list[Any] = []
        if part_nos is not None:
            sql += f" AND o.part_no IN ({','.join('?' for _ in part_nos) or 'NULL'})"
            args += part_nos
        if q.customer.strip():
            sql += " AND (c.code = ? OR c.name LIKE ?)"
            args += [q.customer.strip(), _like(q.customer)]
        if q.status == "未完了":
            sql += " AND o.status IN (?, ?)"
            args += list(OPEN_SO)
        elif q.status:
            sql += " AND o.status = ?"
            args.append(q.status)
        sql += " AND o.ordered_on BETWEEN ? AND ?"
        args += [(q.since or date(1, 1, 1)).isoformat(), (q.until or today()).isoformat()]
        total = self.con.execute("SELECT COUNT(*)" + sql, args).fetchone()[0]
        if total > cap:
            raise TooMany(total, cap, "顧客・部品・状態・期間で絞ってください")
        rows = self._rows("SELECT o.*, p.name, c.name AS customer" + sql + " ORDER BY o.ordered_on, o.so_no", args)
        return Fetch(
            [
                SoLine(
                    r["so_no"],
                    r["customer"],
                    r["part_no"],
                    r["name"],
                    r["qty"],
                    r["shipped_qty"],
                    date.fromisoformat(r["ordered_on"]),
                    date.fromisoformat(r["due_on"]),
                    r["status"],
                )
                for r in rows
            ]
        )

    async def suppliers(self, who: ErpUser, term: str) -> Fetch[Supplier]:
        self._check(who, "suppliers")
        q = _like(term)
        rows = self._rows(
            "SELECT * FROM suppliers WHERE code LIKE ? OR name LIKE ? OR location LIKE ? ORDER BY code", [q, q, q]
        )
        return Fetch([Supplier(r["code"], r["name"], r["location"], r["lead_days"], r["contact"] or "") for r in rows])

    async def health(self) -> Health:
        t = time.perf_counter()
        n = await asyncio.to_thread(lambda: self.con.execute("SELECT COUNT(*) FROM parts").fetchone()[0])
        return Health(True, "mock (sqlite)", int((time.perf_counter() - t) * 1000), f"{n} 部品")

    async def aclose(self) -> None:
        self.con.close()
