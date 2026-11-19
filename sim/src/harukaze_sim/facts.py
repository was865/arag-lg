"""スナップショット（world.db）への問い合わせ（specs/034 R8・R12）。

文書の生成（docs/generate.py）と答えの計算（answers.py）は、どちらもここを通す。
同じ問いに同じ答えを返すため、数字を別々に数えない。日付は ISO の文字列（YYYY-MM-DD）で比べる。
"""

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REVISED = date(2026, 10, 1)  # 標準単価を改めた日（下期）


def connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def usable_warehouses(con: sqlite3.Connection) -> list[str]:
    return [r["code"] for r in con.execute("SELECT code FROM warehouses WHERE usable = 1 ORDER BY code DESC")]


@dataclass(frozen=True)
class PartRow:
    part_no: str
    name: str
    models: str
    std_price: int  # その時点の標準単価
    reorder_point: int
    supplier_code: str
    status: str  # その時点の状態
    successor: str
    uom: str
    purchase_uom: str
    purchase_ratio: int
    category: str


def parts_at(con: sqlite3.Connection, day: date) -> dict[str, PartRow]:
    """その時点の部品（状態・標準単価をその日の値にする）。"""
    out: dict[str, PartRow] = {}
    for r in con.execute("SELECT * FROM parts ORDER BY part_no"):
        retired = r["retired_on"] is not None and date.fromisoformat(r["retired_on"]) <= day
        price = r["old_std_price"] if day < REVISED and r["old_std_price"] is not None else r["std_price"]
        out[r["part_no"]] = PartRow(
            r["part_no"], r["name"], r["models"], int(price), int(r["reorder_point"]), r["supplier_code"] or "",
            "廃止" if retired else "通常", r["successor"] or "", r["uom"], r["purchase_uom"], int(r["purchase_ratio"]),
            r["category"],
        )  # fmt: skip
    return out


def stock_at(con: sqlite3.Connection, day: date, warehouses: list[str]) -> dict[str, float]:
    """その日の終わりの在庫（在庫の単位）。倉庫を合わせた数。"""
    marks = ",".join("?" for _ in warehouses)
    rows = con.execute(
        f"SELECT part_no, SUM(qty) AS q FROM stock_moves WHERE date <= ? AND warehouse IN ({marks}) GROUP BY part_no",
        [day.isoformat(), *warehouses],
    )
    return {r["part_no"]: float(r["q"]) for r in rows}


@dataclass(frozen=True)
class Shortage:
    part_no: str
    name: str
    stock: float
    reorder_point: int


def below_reorder(con: sqlite3.Connection, day: date) -> list[Shortage]:
    """その日、使える倉庫の在庫が発注点を下回っている部品（廃止を除く）。"""
    parts = parts_at(con, day)
    stock = stock_at(con, day, usable_warehouses(con))
    out = [
        Shortage(p.part_no, p.name, stock.get(p.part_no, 0.0), p.reorder_point)
        for p in parts.values()
        if p.status == "通常" and stock.get(p.part_no, 0.0) < p.reorder_point
    ]
    return sorted(out, key=lambda s: s.part_no)


def month_range(year: int, month: int) -> tuple[str, str]:
    first = date(year, month, 1)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return first.isoformat(), nxt.isoformat()


def production(con: sqlite3.Connection, year: int, month: int) -> dict[str, int]:
    """月の製品の製造台数（製造入庫）。"""
    a, b = month_range(year, month)
    rows = con.execute(
        "SELECT part_no, SUM(qty) AS q FROM stock_moves WHERE kind = '製造入庫' AND date >= ? AND date < ?"
        " GROUP BY part_no ORDER BY part_no",
        (a, b),
    )
    return {r["part_no"]: int(r["q"]) for r in rows}


def shipped(con: sqlite3.Connection, year: int, month: int) -> tuple[int, float]:
    """月の出荷（受注の行の数・数量）。"""
    a, b = month_range(year, month)
    r = con.execute(
        "SELECT COUNT(DISTINCT so_no) AS n, COALESCE(SUM(qty), 0) AS q FROM shipments WHERE date >= ? AND date < ?",
        (a, b),
    ).fetchone()
    return int(r["n"]), float(r["q"])


def ordered(con: sqlite3.Connection, year: int, month: int) -> tuple[int, int]:
    """月に出した発注（件数・金額。取り消したものを除く）。"""
    a, b = month_range(year, month)
    r = con.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(qty * unit_cost), 0) AS amt FROM purchase_orders"
        " WHERE ordered_on >= ? AND ordered_on < ? AND status != '取消'",
        (a, b),
    ).fetchone()
    return int(r["n"]), int(r["amt"])


def received_by(con: sqlite3.Connection, po_no: str, day: date) -> float:
    r = con.execute(
        "SELECT COALESCE(SUM(qty), 0) AS q FROM receipts WHERE po_no = ? AND date <= ?", (po_no, day.isoformat())
    ).fetchone()
    return float(r["q"])


@dataclass(frozen=True)
class OverduePo:
    po_no: str
    part_no: str
    supplier_code: str
    qty: int
    received: float
    due_on: str
    uom: str  # 発注の単位


def overdue_pos(con: sqlite3.Connection, day: date) -> list[OverduePo]:
    """その日、納期を過ぎて入荷し終えていない発注（その日までに取り消したものは数えない）。

    取り消しの日は記録に無いので、取り消した発注は除く（題に使うのは今日のときだけ）。
    """
    out: list[OverduePo] = []
    for r in con.execute(
        "SELECT * FROM purchase_orders WHERE ordered_on <= ? AND due_on < ? AND status != '取消' ORDER BY po_no",
        (day.isoformat(), day.isoformat()),
    ):
        got = received_by(con, r["po_no"], day)
        if got < float(r["qty"]):
            out.append(
                OverduePo(r["po_no"], r["part_no"], r["supplier_code"], int(r["qty"]), got, r["due_on"], r["uom"])
            )
    return out


def issued_top(con: sqlite3.Connection, year: int, month: int, n: int = 5) -> list[tuple[str, str, float]]:
    """月にラインへ払い出した数の多い部品（部品番号・名称・数）。"""
    a, b = month_range(year, month)
    rows = con.execute(
        "SELECT m.part_no, p.name, -SUM(m.qty) AS q FROM stock_moves m JOIN parts p USING (part_no)"
        " WHERE m.kind = '出庫' AND m.ref LIKE 'IS-%' AND m.date >= ? AND m.date < ?"
        " GROUP BY m.part_no ORDER BY q DESC, m.part_no LIMIT ?",
        (a, b, n),
    )
    return [(r["part_no"], r["name"], float(r["q"])) for r in rows]


@dataclass(frozen=True)
class Upkeep:
    records: int
    breakdowns: int
    downtime_min: int


def upkeep(con: sqlite3.Connection, year: int, month: int) -> Upkeep:
    a, b = month_range(year, month)
    r = con.execute(
        "SELECT COUNT(*) AS n, SUM(work = '故障修理') AS br, COALESCE(SUM(downtime_min), 0) AS dt FROM work_records"
        " WHERE date >= ? AND date < ?",
        (a, b),
    ).fetchone()
    return Upkeep(int(r["n"]), int(r["br"] or 0), int(r["dt"]))


def scrapped(con: sqlite3.Connection, a: date, b: date) -> list[tuple[str, str, float, str]]:
    """期間（a 以上 b 未満）の廃棄（部品番号・名称・数・倉庫）。"""
    rows = con.execute(
        "SELECT m.part_no, p.name, -m.qty AS q, m.warehouse FROM stock_moves m JOIN parts p USING (part_no)"
        " WHERE m.kind = '廃棄' AND m.date >= ? AND m.date < ? ORDER BY m.date, m.part_no",
        (a.isoformat(), b.isoformat()),
    )
    return [(r["part_no"], r["name"], float(r["q"]), r["warehouse"]) for r in rows]


@dataclass(frozen=True)
class SupplierScore:
    code: str
    name: str
    orders: int
    on_time: int
    late_days_avg: float

    @property
    def rate(self) -> float:
        return self.on_time / self.orders if self.orders else 0.0

    @property
    def grade(self) -> str:
        return "A" if self.rate >= 0.85 else "B" if self.rate >= 0.70 else "C"


def supplier_scores(con: sqlite3.Connection, a: date, b: date) -> list[SupplierScore]:
    """納期が期間（a 以上 b 未満）の、入荷し終えた発注の納期の守り方（仕入先ごと）。

    納期どおり = 最後の入荷の日が納期以前。遅れの日数は遅れた発注だけで平均する。
    """
    out: list[SupplierScore] = []
    rows = con.execute(
        "SELECT o.supplier_code AS code, s.name, o.due_on, o.received_on FROM purchase_orders o"
        " JOIN suppliers s ON s.code = o.supplier_code"
        " WHERE o.status = '入荷済み' AND o.due_on >= ? AND o.due_on < ? ORDER BY o.supplier_code",
        (a.isoformat(), b.isoformat()),
    ).fetchall()
    by: dict[str, list[sqlite3.Row]] = {}
    for r in rows:
        by.setdefault(r["code"], []).append(r)
    for code, rs in by.items():
        late = [
            (date.fromisoformat(r["received_on"]) - date.fromisoformat(r["due_on"])).days
            for r in rs
            if r["received_on"] > r["due_on"]
        ]
        avg = round(sum(late) / len(late), 1) if late else 0.0
        out.append(SupplierScore(code, rs[0]["name"], len(rs), len(rs) - len(late), avg))
    return out
