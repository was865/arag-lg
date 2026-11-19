"""ある時点の文書（specs/034 R8）: 文書の数字はその時点のデータと一致する。"""

from datetime import date, timedelta
from pathlib import Path

import pytest
from docx import Document
from openpyxl import load_workbook
from pptx import Presentation

from harukaze_sim import facts
from harukaze_sim.docs import generate
from harukaze_sim.run import simulate
from harukaze_sim.sinks import sqlite as sink

COMMITTED = Path(__file__).resolve().parents[2] / "eval/assets/harukaze_plant/world.db"


@pytest.fixture(scope="module")
def db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return sink.write(tmp_path_factory.mktemp("w") / "world.db", *simulate())


@pytest.fixture(scope="module")
def docs(db: Path, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    out = tmp_path_factory.mktemp("docs")
    return {p.name[:3]: p for p in generate.all_docs(db, out)}


def test_committed_world_is_reproducible(db: Path) -> None:
    """コミットした world.db は模擬器から作り直せる（評価の答えの元）。"""
    a, b = facts.connect(COMMITTED), facts.connect(db)
    for table in ("parts", "stock_moves", "purchase_orders", "receipts", "sales_orders", "work_records"):
        q = f"SELECT * FROM {table} ORDER BY 1, 2"
        assert [tuple(r) for r in a.execute(q)] == [tuple(r) for r in b.execute(q)], table


def test_ledger_matches_stock_of_wh2_at_month_end(db: Path, docs: dict[str, Path]) -> None:
    con = facts.connect(db)
    stock = facts.stock_at(con, generate.LEDGER_DAY, ["WH2"])
    parts = facts.parts_at(con, generate.LEDGER_DAY)
    ws = load_workbook(docs["g01"])["部品"]
    rows = [[c.value for c in r] for r in ws.iter_rows(min_row=3) if r[0].value and str(r[0].value).startswith("P-")]
    assert len(rows) == sum(1 for p in parts.values() if p.category != "製品")
    for no, _name, _m, price, qty, *_ in rows:
        assert qty == pytest.approx(stock.get(no, 0.0)), no
        assert price == parts[no].std_price
    # 9 月 30 日の台帳（harukaze_mix x01）と同じ部品は、10 月の動きのぶんだけ違う
    by = {r[0]: r for r in rows}
    assert by["P-4002"][8] == "廃止" and by["P-4002"][4] == 0


def test_stock_report_lists_parts_below_reorder_point(db: Path, docs: dict[str, Path]) -> None:
    con = facts.connect(db)
    wb = load_workbook(docs["g03"])
    for day in generate.REPORT_WEEKS:
        ws = wb[f"{day.month}月{day.day}日"]
        got = [r[0].value for r in ws.iter_rows(min_row=3) if r[0].value and str(r[0].value).startswith("P-")]
        assert got == [s.part_no for s in facts.below_reorder(con, day - timedelta(days=1))]
        assert got


def test_monthly_report_counts(db: Path, docs: dict[str, Path]) -> None:
    con = facts.connect(db)
    text = " ".join(
        sh.text_frame.text for s in Presentation(str(docs["g02"])).slides for sh in s.shapes if sh.has_text_frame
    )
    made = facts.production(con, 2026, 10)
    assert f"生産台数: {sum(made.values())} 台" in text
    n_po, amount = facts.ordered(con, 2026, 10)
    assert f"出した発注: {n_po} 件（金額の合計 {amount:,} 円" in text
    assert f"入荷し終えていない発注: {len(facts.overdue_pos(con, date(2026, 10, 31)))} 件" in text


def test_minutes_follow_seal_kit_stock(db: Path, docs: dict[str, Path]) -> None:
    con = facts.connect(db)
    for key, day in (("g04", generate.MEETINGS[0]), ("g05", generate.MEETINGS[1])):
        text = "\n".join(p.text for p in Document(str(docs[key])).paragraphs)
        n = facts.stock_at(con, day - timedelta(days=1), facts.usable_warehouses(con)).get("P-1042", 0)
        assert f"会議の前日の終わりで {int(n)} 個" in text


def test_supplier_scores_cover_first_half() -> None:
    con = facts.connect(COMMITTED)
    scores = facts.supplier_scores(con, date(2026, 4, 1), date(2026, 10, 1))
    assert {s.grade for s in scores} == {"A", "B", "C"}
    assert all(0 <= s.on_time <= s.orders for s in scores)


def test_conflicts_are_real() -> None:
    """conflicts.yaml の「システムの値」は今のデータのとおりで、文書の記述とは違う。"""
    con = facts.connect(COMMITTED)
    one = lambda q, *a: tuple(con.execute(q, a).fetchone())  # noqa: E731
    assert one("SELECT extension FROM employees WHERE name = '佐伯 美穂'") == ("2210",)
    assert one("SELECT reorder_point FROM parts WHERE part_no = 'P-2011'") == (12,)
    assert one("SELECT lead_days FROM suppliers WHERE code = 'S-07'") == (21,)
    assert one("SELECT status, successor, retired_on FROM parts WHERE part_no = 'P-5009'") == (
        "廃止", "P-5010", "2026-10-04",
    )  # fmt: skip
    assert one("SELECT std_price, old_std_price FROM parts WHERE part_no = 'P-5002'") == (22400, 21571)
    text = (COMMITTED.parent / "conflicts.yaml").read_text()
    for needle in ("2201", "発注点は 10", "14 日", "P-5009", "21,571"):
        assert needle in text
