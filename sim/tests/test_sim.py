"""模擬器（specs/034 R1〜R6・R14）。"""

import hashlib
import sqlite3
from datetime import date
from pathlib import Path

import pytest
from mock_systems import queries as q
from mock_systems import seed as fixed
from mock_systems.common import Identity, open_ro

from harukaze_sim.events import Move, PurchaseOrdered, SalesOrdered
from harukaze_sim.run import simulate
from harukaze_sim.sinks import sqlite as sink


@pytest.fixture(scope="module")
def sim():  # type: ignore[no-untyped-def]
    return simulate()


@pytest.fixture(scope="module")
def world_db(sim, tmp_path_factory: pytest.TempPathFactory) -> Path:  # type: ignore[no-untyped-def]
    return sink.write(tmp_path_factory.mktemp("w") / "world.db", *sim)


@pytest.fixture(scope="module")
def small_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = tmp_path_factory.mktemp("s")
    fixed.build(d)
    return d / "erp.db"


def _digest(events: list[object]) -> str:
    return hashlib.sha256(repr(events).encode()).hexdigest()


def test_same_seed_same_world(sim) -> None:  # type: ignore[no-untyped-def]
    _, again = simulate()
    assert _digest(sim[1]) == _digest(again)


def test_other_seed_other_world(sim) -> None:  # type: ignore[no-untyped-def]
    _, other = simulate(1)
    assert _digest(sim[1]) != _digest(other)


def test_scale(sim) -> None:  # type: ignore[no-untyped-def]
    world, events = sim
    assert 300 <= len(world.parts) <= 500
    assert len(world.suppliers) == 30 and len(world.customers) == 40 and len(world.employees) == 60
    pos = sum(isinstance(e, PurchaseOrdered) for e in events)
    moves = sum(isinstance(e, Move) for e in events)
    sos = sum(isinstance(e, SalesOrdered) for e in events)
    assert 1200 <= pos <= 1800, pos
    assert 8000 <= moves <= 14000, moves
    assert 500 <= sos <= 1000, sos


def test_new_numbers_do_not_overlap_fixed(sim) -> None:  # type: ignore[no-untyped-def]
    world, _ = sim
    fixed_parts = {p[0] for p in fixed.PARTS}
    new = [p for p in world.parts if p not in fixed_parts]
    assert all(p.startswith(("P-5", "FG-")) for p in new)
    assert all(int(s[2:]) >= 20 for s in world.suppliers if s not in {x[0] for x in fixed.SUPPLIERS})


def test_fixed_parts_only_move_by_fixed_events(sim) -> None:  # type: ignore[no-untyped-def]
    _, events = sim
    fixed_parts = {p[0] for p in fixed.PARTS}
    moved = [
        (e.day.isoformat(), e.part, e.kind, e.qty, e.ref)
        for e in events
        if isinstance(e, Move) and e.part in fixed_parts
    ]
    expected = [("2026-09-30", p, "棚卸", qty, "INV-2026-09") for p, qty in fixed.OPENING.items()]
    expected += [(d, p, k, qty, ref) for d, p, k, qty, ref, _ in fixed.MOVES]
    assert sorted(moved) == sorted(expected)


def test_realism(world_db: Path) -> None:
    con = sqlite3.connect(world_db)
    one = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
    total = one("SELECT COUNT(*) FROM purchase_orders")
    split = one("SELECT COUNT(*) FROM (SELECT po_no FROM receipts GROUP BY po_no HAVING COUNT(*) > 1)")
    assert 0.08 < split / total < 0.25  # 分けて届く入荷
    late = one("SELECT COUNT(*) FROM purchase_orders WHERE received_on > due_on")
    assert late > 50  # 納期の遅れ
    assert one("SELECT COUNT(*) FROM purchase_orders WHERE status = '取消'") > 0
    assert one("SELECT COUNT(*) FROM parts WHERE status = '廃止' AND successor != ''") >= 5
    assert (
        one(
            "SELECT COUNT(DISTINCT unit_cost) FROM purchase_orders WHERE part_no = (SELECT part_no FROM purchase_orders GROUP BY part_no ORDER BY COUNT(*) DESC LIMIT 1)"
        )
        > 1
    )
    assert one("SELECT COUNT(*) FROM parts WHERE name LIKE '%6308%'") >= 3  # 似た名前
    assert one("SELECT COUNT(*) FROM parts WHERE purchase_uom LIKE '箱%'") > 10  # 単位
    assert one("SELECT COUNT(*) FROM stock_moves WHERE warehouse = 'DEAD'") > 0  # 呆滞
    assert one("SELECT COUNT(*) FROM purchase_orders WHERE note LIKE '%AI%'") == 1  # 指示に見える備考は 1 件だけ
    # 在庫は負にならない
    assert (
        one(
            "SELECT COUNT(*) FROM (SELECT part_no, warehouse, SUM(qty) s FROM stock_moves GROUP BY 1, 2 HAVING s < -0.001)"
        )
        == 0
    )


@pytest.mark.parametrize("part", [p[0] for p in fixed.PARTS])
def test_small_suite_answers_are_the_same(part: str, world_db: Path, small_db: Path) -> None:
    """harukaze_systems が頼る値（032 の問い合わせ）は、大きい世界でも同じ（R14）。"""
    who = Identity("u", frozenset({"購買課"}))
    big, small = open_ro(world_db), open_ro(small_db)
    for fn, kw in [
        (q.get_stock, {"part": part}),
        (q.list_stock_moves, {"part": part}),
        (q.list_purchase_orders, {"part": part}),
        (q.find_parts, {"term": part}),
    ]:
        a, b = fn(big, who, **kw), fn(small, who, **kw)  # type: ignore[operator]
        assert a["columns"] == b["columns"]
        assert [r for r in a["rows"] if r[1] == part or r[0] == part] == [
            r for r in b["rows"] if r[1] == part or r[0] == part
        ], fn.__name__


def test_today_is_fixed() -> None:
    from harukaze_sim.world import TODAY

    assert date(2026, 11, 18) == TODAY
