"""模擬のデータの 9/30 の値が評価資料（harukaze_mix の xlsx）と一致すること（R2）。"""

import sqlite3

import openpyxl
import pytest

from mock_systems.seed import COMMENTS, EMPLOYEES

from .conftest import ASSETS


def _rows(path, sheet, start):  # type: ignore[no-untyped-def]
    ws = openpyxl.load_workbook(path, data_only=True)[sheet]
    return [
        r
        for r in ws.iter_rows(min_row=start, values_only=True)
        if r[0] and str(r[0]).startswith(("P-", "S-", "2026", "PM", "AL", "XR", "CR"))
    ]


def test_parts_and_stock_on_0930_match_ledger(con) -> None:  # type: ignore[no-untyped-def]
    erp = con("erp")
    for part_no, name, models, price, stock, rop, supplier in _rows(ASSETS / "x01-部品台帳.xlsx", "部品", 3):
        p = erp.execute("SELECT * FROM parts WHERE part_no = ?", (part_no,)).fetchone()
        assert p["name"] == name
        assert p["std_price"] == price
        assert p["reorder_point"] == rop
        assert p["supplier_code"] == supplier
        if models:  # 結合セルの 2 行目は空
            assert p["models"] == models.replace("（廃止予定）", "")
        on_0930 = erp.execute(
            "SELECT SUM(qty) FROM stock_moves WHERE part_no = ? AND date <= '2026-09-30'", (part_no,)
        ).fetchone()[0]
        assert on_0930 == stock, part_no


def test_suppliers_match(con) -> None:  # type: ignore[no-untyped-def]
    erp = con("erp")
    for code, name, loc, lead, contact in _rows(ASSETS / "x01-部品台帳.xlsx", "仕入先", 2):
        assert tuple(
            erp.execute("SELECT name, location, lead_days, contact FROM suppliers WHERE code = ?", (code,)).fetchone()
        ) == (name, loc, lead, contact)


def test_september_work_records_and_equipment_match(con) -> None:  # type: ignore[no-untyped-def]
    cmms = con("cmms")
    sept = _rows(ASSETS / "x02-保守記録_2026-09.xlsx", "2026年9月", 2)
    got = cmms.execute(
        "SELECT w.date, w.equipment_id, e.name, w.work, w.staff, w.downtime_min FROM work_records w"
        " JOIN equipment e ON e.id = w.equipment_id WHERE w.date <= '2026-09-30' ORDER BY w.date"
    ).fetchall()
    assert len(got) == len(sept)
    for (d, eq, name, work, staff, mins), g in zip(sept, got, strict=True):
        assert (g[0], g[1], g[2], g[4], g[5]) == (d, eq, name, staff, mins)
        # 資料の「（手順書第3版）」は、システムでは「使った手順書」の列に分けている
        assert work.replace("（手順書第3版）", "") == g[3]
    for eid, name, loc, year in _rows(ASSETS / "x02-保守記録_2026-09.xlsx", "設備一覧", 2):
        assert tuple(
            cmms.execute("SELECT name, location, installed FROM equipment WHERE id = ?", (eid,)).fetchone()
        ) == (name, loc, year)


def test_read_only(con) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(sqlite3.OperationalError):
        con("erp").execute("DELETE FROM parts")


def test_has_instruction_like_comment_and_private_phone() -> None:
    # R5: 指示に見える文が 1 件以上。R4: 私用の連絡先はデータにはある（ツールが出さないことを別に確かめる）
    assert any("指示" in c[3] and "無視" in c[3] for c in COMMENTS)
    assert all(e[5] for e in EMPLOYEES)
