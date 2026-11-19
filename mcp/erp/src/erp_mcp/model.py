"""アダプタとツールの層のあいだの型（specs/033 design §2）。

アダプタは ERP の記録を ERP に依らない形（下の dataclass）で返し、ツールの層が 032 と同じ出力の形（列・行）にする。
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol


class ErpError(Exception):
    """ERP の呼び出しの失敗。kind はツールの結果の種類（監査・ARag の記録に出る）。"""

    kind = "error"


class ErpUnavailable(ErpError):
    """ERP が応答しない・止めている（R12）。"""

    kind = "unavailable"


class ErpForbidden(ErpError):
    """ERP の権限で読めない（R9・R10）。"""

    kind = "forbidden"


class TooMany(ErpError):
    """上限を超えた（R5）。黙って切らずに件数と絞り込みの手がかりを返す。"""

    kind = "too_many"

    def __init__(self, total: int, limit: int, hint: str) -> None:
        super().__init__(f"{total} 件あり、上限（{limit} 件）を超えています")
        self.total, self.limit, self.hint = total, limit, hint


@dataclass(frozen=True)
class ErpUser:
    """ERP に入る利用者（部門ごとの技術用の利用者。R9）。"""

    login: str
    hide: frozenset[str] = frozenset()  # 伏せる項目（例 unit_cost）
    hide_note: str = ""
    deny: frozenset[str] = frozenset()  # 見せない業務（例 purchase）。ERP の権限より狭くするときだけ


@dataclass(frozen=True)
class Part:
    part_no: str
    name: str
    name_en: str
    models: str
    category: str
    std_price: float | None
    reorder_point: float
    supplier_code: str
    supplier_name: str
    status: str  # 通常 / 廃止
    successor: str
    uom: str
    purchase_uom: str


@dataclass(frozen=True)
class StockLine:
    part_no: str
    warehouse: str
    qty: float


@dataclass(frozen=True)
class MoveRec:
    date: date
    part_no: str
    name: str
    kind: str
    qty: float
    ref: str
    note: str
    warehouse: str


@dataclass(frozen=True)
class PoLine:
    po_no: str
    part_no: str
    name: str
    supplier_code: str
    supplier_name: str
    qty: float
    uom: str
    received_qty: float
    unit_cost: float | None
    ordered_on: date
    due_on: date
    received_on: date | None
    status: str  # 発注済み / 一部入荷 / 入荷済み / 取消
    note: str = ""


@dataclass(frozen=True)
class SoLine:
    so_no: str
    customer: str
    part_no: str
    name: str
    qty: float
    shipped_qty: float
    ordered_on: date
    due_on: date
    status: str  # 受注済み / 一部出荷 / 出荷済み / 取消


@dataclass(frozen=True)
class Supplier:
    code: str
    name: str
    location: str
    lead_days: int | None
    contact: str


@dataclass(frozen=True)
class PoQuery:
    part: str = ""
    supplier: str = ""
    status: str = ""  # 空 / 発注済み / 一部入荷 / 入荷済み / 取消 / 未完了
    since: date | None = None
    until: date | None = None
    po_no: str = ""  # 発注番号（完全一致。大文字・前後の空白は問わない）


@dataclass(frozen=True)
class SoQuery:
    customer: str = ""
    part: str = ""
    status: str = ""
    since: date | None = None
    until: date | None = None


@dataclass
class Fetch[T]:
    """アダプタの結果: 記録・ERP への呼び出しの回数（ページ送りの数）・読めなかった項目。"""

    items: list[T]
    calls: int = 1
    restricted: list[str] = field(default_factory=list)


@dataclass
class LastMoves:
    """部品ごとの最後の入出庫。"""

    items: dict[str, MoveRec]
    calls: int = 1


@dataclass(frozen=True)
class Health:
    ok: bool
    version: str
    ms: int
    detail: str = ""


class ErpBackend(Protocol):
    """ERP ごとのアダプタの端口（design §2）。上限（cap）を超えたら TooMany を投げる。"""

    name: str

    async def find_parts(self, who: ErpUser, term: str, status: str, cap: int) -> Fetch[Part]: ...

    async def stock(self, who: ErpUser, part_nos: list[str]) -> Fetch[StockLine]: ...

    async def on_order(self, who: ErpUser, part_nos: list[str]) -> Fetch[PoLine]: ...

    async def last_moves(self, who: ErpUser, part_nos: list[str]) -> LastMoves: ...

    async def moves(
        self, who: ErpUser, part_nos: list[str], since: date | None, until: date | None, cap: int
    ) -> Fetch[MoveRec]: ...

    async def purchase_lines(self, who: ErpUser, q: PoQuery, part_nos: list[str] | None, cap: int) -> Fetch[PoLine]: ...

    async def sales_lines(self, who: ErpUser, q: SoQuery, part_nos: list[str] | None, cap: int) -> Fetch[SoLine]: ...

    async def suppliers(self, who: ErpUser, term: str) -> Fetch[Supplier]: ...

    async def health(self) -> Health: ...

    async def aclose(self) -> None: ...
