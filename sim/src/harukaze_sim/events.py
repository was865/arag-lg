"""出来事の型（specs/034 design §1）。2 つの出力先（SQLite・Odoo）は同じ出来事の列を受け取る（R6）。"""

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Event:
    day: date


@dataclass
class Move(Event):
    """在庫の動き 1 行（在庫の単位、入りは正・出は負）。

    kind: 棚卸・入庫・出庫・製造出庫・製造入庫・保全出庫・廃棄・移動
    """

    part: str
    warehouse: str
    kind: str
    qty: float
    ref: str
    note: str = ""
    po_no: str = ""
    so_no: str = ""


@dataclass
class PurchaseOrdered(Event):
    po_no: str
    part: str
    supplier: str
    qty: int  # 発注の単位で
    unit_cost: int  # 発注の単位 1 つあたり（円）
    due_on: date
    warehouse: str
    buyer: str
    note: str = ""


@dataclass
class PurchaseChanged(Event):
    po_no: str
    qty: int
    note: str = ""


@dataclass
class PurchaseCancelled(Event):
    po_no: str
    note: str = ""


@dataclass
class SalesOrdered(Event):
    so_no: str
    customer: str
    part: str
    qty: float
    unit_price: int
    due_on: date
    note: str = ""


@dataclass
class SalesCancelled(Event):
    so_no: str
    note: str = ""


@dataclass
class WorkRecorded(Event):
    record_no: str
    equipment: str
    work: str
    staff: str
    downtime_min: int
    procedure: str = ""
    parts: list[tuple[str, float]] = field(default_factory=list)
    work_order: str = ""


@dataclass
class WorkOrderOpened(Event):
    wo_no: str
    equipment: str
    title: str
    assignee: str
    due_on: date


@dataclass
class WorkOrderClosed(Event):
    wo_no: str
