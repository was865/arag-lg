"""契約のテスト（specs/033 R6・design §2）: mock と Odoo のアダプタが、同じ問いに同じ列・同じ値を返す。

Odoo は compose で起こした結合テスト（ERP_ODOO_TEST=1、`make sim-odoo` か `make erp-reset` の後）。CI では mock だけ。
"""

import os
from typing import Any

import pytest

from erp_mcp import config
from erp_mcp.audit import Audit
from erp_mcp.backends.mock import MockBackend
from erp_mcp.model import PoQuery, SoQuery
from erp_mcp.tools import Service

from .conftest import WORLD

ODOO = os.environ.get("ERP_ODOO_TEST") == "1"
PARTS = ["P-1042", "P-1043", "P-2010", "P-2011", "P-3100", "P-3120", "P-4001", "P-4002"]


def _mock() -> Service:
    c = config.load("mock")
    return Service(MockBackend(WORLD, c["rights"], c["usable_warehouses"]), config.user_map(), Audit(None))


def _odoo() -> Service:
    from erp_mcp.backends.odoo import OdooBackend

    os.environ.setdefault("ERP_ODOO_URL", "http://localhost:8069")
    os.environ.setdefault("ERP_ODOO_DB", "harukaze")
    return Service(OdooBackend.from_config(config.load("odoo")), config.user_map(), Audit(None))


def _rows(t: dict[str, Any]) -> list[list[Any]]:
    return [[round(v, 3) if isinstance(v, float) else v for v in r] for r in t.get("rows", [])]


async def _both(fn: Any) -> tuple[dict[str, Any], dict[str, Any] | None]:
    a = await fn(_mock())
    b = await fn(_odoo()) if ODOO else None
    return a, b


def _same(a: dict[str, Any], b: dict[str, Any] | None, *, drop: tuple[str, ...] = ()) -> None:
    assert "error" not in a, a
    if b is None:
        return
    assert "error" not in b, b
    assert a["columns"] == b["columns"]
    keep = [i for i, c in enumerate(a["columns"]) if c not in drop]
    pick = lambda rows: sorted([[r[i] for i in keep] for r in rows], key=repr)  # noqa: E731
    assert pick(_rows(a)) == pick(_rows(b))


@pytest.mark.parametrize("part", [*PARTS, "6308", "M10", "グリス", "P-5005", "P-5028"])
async def test_stock(part: str) -> None:
    a, b = await _both(lambda s: s.get_stock(s.users.pick(frozenset({"購買課"})), part))
    _same(a, b)


async def test_below_reorder() -> None:
    a, b = await _both(lambda s: s.list_below_reorder(s.users.pick(frozenset({"購買課"}))))
    _same(a, b)


@pytest.mark.parametrize("part", ["P-1042", "P-2011", "P-4002", "P-5028", "P-5110"])
async def test_moves(part: str) -> None:
    a, b = await _both(lambda s: s.list_stock_moves(s.users.pick(frozenset({"購買課"})), part, None, None))
    _same(a, b, drop=("備考",))


@pytest.mark.parametrize(
    "q",
    [PoQuery(part="P-1043"), PoQuery(part="P-2011"), PoQuery(supplier="S-07"), PoQuery(part="M8"),
     PoQuery(status="未完了"), PoQuery(po_no="PO-2026-2241")],
)  # fmt: skip
async def test_purchase(q: PoQuery) -> None:
    a, b = await _both(lambda s: s.list_purchase_orders(s.users.pick(frozenset({"購買課"})), q, False))
    _same(a, b, drop=("備考",))


async def test_purchase_overdue_hidden_cost() -> None:
    a, b = await _both(lambda s: s.list_purchase_orders(s.users.pick(frozenset({"製造課"})), PoQuery(), True))
    _same(a, b, drop=("備考",))
    assert a["restricted"] == ["仕入単価（円）"]


@pytest.mark.parametrize("term", ["6308", "SK-300", "Ball bearing", "HP-400"])
async def test_parts(term: str) -> None:
    a, b = await _both(lambda s: s.find_parts(s.users.pick(frozenset({"購買課"})), term, ""))
    _same(a, b)


@pytest.mark.parametrize("q", [SoQuery(customer="C-001"), SoQuery(part="FG-400"), SoQuery(status="未完了")])
async def test_sales(q: SoQuery) -> None:
    a, b = await _both(lambda s: s.list_sales_orders(s.users.pick(frozenset({"営業課"})), q, False))
    _same(a, b)


async def test_suppliers() -> None:
    a, b = await _both(lambda s: s.list_suppliers(s.users.pick(frozenset()), ""))
    _same(a, b)


@pytest.mark.skipif(not ODOO, reason="Odoo が要る")
async def test_odoo_denies_purchases_to_viewer() -> None:
    """Odoo の在庫の利用者は発注を読めるので、部門の無い人の拒否は users.yaml の deny で決める（Service が止める）。"""
    from erp_mcp.model import ErpForbidden

    s = _odoo()
    with pytest.raises(ErpForbidden):
        await s.list_purchase_orders(s.users.pick(frozenset({"総務課"})), PoQuery(), False)
