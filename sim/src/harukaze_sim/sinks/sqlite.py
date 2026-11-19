"""出力先 SQLite（specs/034 R6・design §1）: 032 の模擬の表（parts・suppliers・stock_moves・purchase_orders）に、
大きい世界の表（倉庫・入荷・受注・出荷・顧客・社員・設備・作業）を足して書く。在庫などは模擬器が計算した動きの和。

032 の列は同じ名前・同じ順で先に置く（032 の問い合わせがそのまま読める。R14）。
"""

import sqlite3
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from mock_systems import seed as fixed

from harukaze_sim.events import (
    Event,
    Move,
    PurchaseCancelled,
    PurchaseChanged,
    PurchaseOrdered,
    SalesCancelled,
    SalesOrdered,
    WorkOrderClosed,
    WorkOrderOpened,
    WorkRecorded,
)
from harukaze_sim.world import TODAY, WAREHOUSES, World

FIXED_WO_STATUS = {w[0]: w[3] for w in fixed.WORK_ORDERS}

SCHEMA = {
    "parts": "part_no, name, models, std_price, reorder_point, supplier_code, status,"
    " name_en, category, uom, purchase_uom, purchase_ratio, successor, retired_on, old_std_price",
    "suppliers": "code, name, location, lead_days, contact, overseas",
    "warehouses": "code, name, usable, plant",
    "stock_moves": "date, part_no, kind, qty, ref, note, warehouse",
    "purchase_orders": "po_no, part_no, qty, unit_cost, ordered_on, due_on, received_on, status,"
    " supplier_code, uom, received_qty, warehouse, buyer, note",
    "receipts": "po_no, date, qty",
    "customers": "code, name, location",
    "sales_orders": "so_no, customer_code, part_no, qty, unit_price, ordered_on, due_on, shipped_qty, status, note",
    "shipments": "so_no, date, qty",
    "employees": "emp_no, name, dept, title, extension",
    "equipment": "id, name, location, installed",
    "work_records": "date, equipment_id, work, staff, downtime_min, procedure, record_no, work_order",
    "work_orders": "wo_no, equipment_id, title, status, assignee, opened_on, due_on, closed_on",
}


def tables(world: World, events: list[Event]) -> dict[str, Sequence[Sequence[object]]]:
    po: dict[str, dict[str, object]] = {}
    so: dict[str, dict[str, object]] = {}
    wo: dict[str, dict[str, object]] = {}
    moves, receipts, shipments, records = [], [], [], []
    got: dict[str, float] = defaultdict(float)
    for ev in events:
        if isinstance(ev, PurchaseOrdered):
            po[ev.po_no] = {"ev": ev, "qty": ev.qty, "cancelled": False, "last": None}
        elif isinstance(ev, PurchaseChanged):
            po[ev.po_no]["qty"] = ev.qty
        elif isinstance(ev, PurchaseCancelled):
            po[ev.po_no]["cancelled"] = True
        elif isinstance(ev, SalesOrdered):
            so[ev.so_no] = {"ev": ev, "cancelled": False}
        elif isinstance(ev, SalesCancelled):
            so[ev.so_no]["cancelled"] = True
        elif isinstance(ev, Move):
            moves.append((ev.day.isoformat(), ev.part, ev.kind, ev.qty, ev.ref, ev.note, ev.warehouse))
            if ev.po_no and ev.kind == "入庫":
                ratio = world.parts[ev.part].purchase_ratio
                receipts.append((ev.po_no, ev.day.isoformat(), ev.qty / ratio))
                got[ev.po_no] += ev.qty / ratio
                po[ev.po_no]["last"] = ev.day.isoformat()
            if ev.so_no and ev.kind == "出庫":
                shipments.append((ev.so_no, ev.day.isoformat(), -ev.qty))
                got[ev.so_no] += -ev.qty
        elif isinstance(ev, WorkRecorded):
            records.append(
                (ev.day.isoformat(), ev.equipment, ev.work, ev.staff, ev.downtime_min, ev.procedure, ev.record_no,
                 ev.work_order)
            )  # fmt: skip
        elif isinstance(ev, WorkOrderOpened):
            wo[ev.wo_no] = {"ev": ev, "closed": None}
        elif isinstance(ev, WorkOrderClosed):
            wo[ev.wo_no]["closed"] = ev.day.isoformat()

    po_rows = []
    for no, d in po.items():
        e: PurchaseOrdered = d["ev"]  # type: ignore[assignment]
        qty = int(d["qty"])  # type: ignore[call-overload]
        rec = round(got[no], 3)
        if d["cancelled"]:
            status = "取消"
        elif rec >= qty:
            status = "入荷済み"
        elif rec > 0:
            status = "一部入荷"
        else:
            status = "発注済み"
        p = world.parts[e.part]
        po_rows.append(
            (no, e.part, qty, e.unit_cost, e.day.isoformat(), e.due_on.isoformat(),
             d["last"] if status == "入荷済み" else None, status, e.supplier, p.purchase_uom, rec, e.warehouse,
             e.buyer, e.note)
        )  # fmt: skip
    so_rows = []
    for no, d in so.items():
        s: SalesOrdered = d["ev"]  # type: ignore[assignment]
        shipped = round(got[no], 3)
        status = (
            "取消" if d["cancelled"] else "出荷済み" if shipped >= s.qty else "一部出荷" if shipped > 0 else "受注済み"
        )
        so_rows.append(
            (no, s.customer, s.part, s.qty, s.unit_price, s.day.isoformat(), s.due_on.isoformat(), shipped, status,
             s.note)
        )  # fmt: skip
    wo_rows = []
    for no, d in wo.items():
        w: WorkOrderOpened = d["ev"]  # type: ignore[assignment]
        closed = d["closed"]
        if closed:
            status = "完了"
        elif no in FIXED_WO_STATUS:
            status = FIXED_WO_STATUS[no]
        else:
            status = "未着手" if (TODAY - w.day).days < 3 else "作業中"
        wo_rows.append((no, w.equipment, w.title, status, w.assignee, w.day.isoformat(), w.due_on.isoformat(), closed))
    parts = []
    for p in world.parts.values():
        status = "廃止" if p.retired_on is not None and p.retired_on <= TODAY else p.status
        parts.append(
            (p.part_no, p.name, p.models, p.std_price, p.reorder_point, p.supplier_code, status, p.name_en,
             p.category, p.uom, p.purchase_uom, p.purchase_ratio, p.successor,
             p.retired_on.isoformat() if p.retired_on else None, p.old_std_price)
        )  # fmt: skip
    return {
        "parts": parts,
        "suppliers": [
            (s.code, s.name, s.location, s.lead_days, s.contact, int(s.overseas)) for s in world.suppliers.values()
        ],
        "warehouses": [(c, n, int(u), pl) for c, n, u, pl in WAREHOUSES],
        "stock_moves": moves,
        "purchase_orders": po_rows,
        "receipts": receipts,
        "customers": [(c.code, c.name, c.location) for c in world.customers.values()],
        "sales_orders": so_rows,
        "shipments": shipments,
        "employees": [(e.emp_no, e.name, e.dept, e.title, e.extension) for e in world.employees],
        "equipment": [(e.id, e.name, e.location, e.installed) for e in world.equipment],
        "work_records": records,
        "work_orders": wo_rows,
    }


def write(path: Path, world: World, events: list[Event]) -> Path:
    """1 つの SQLite のファイルに書く（あれば作り直す）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    con = sqlite3.connect(path)
    try:
        for name, rows in tables(world, events).items():
            cols = SCHEMA[name]
            con.execute(f"CREATE TABLE {name} ({cols})")
            marks = ", ".join("?" for _ in cols.split(","))
            con.executemany(f"INSERT INTO {name} VALUES ({marks})", rows)
        con.execute("CREATE INDEX moves_part ON stock_moves (part_no, date)")
        con.execute("CREATE INDEX po_part ON purchase_orders (part_no)")
        con.commit()
    finally:
        con.close()
    return path
