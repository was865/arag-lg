"""表の集計（specs/026 R12・R13）。"""

import pytest

from arag.agent.table import TableError, parse_tables, render, run_query, to_value

LEDGER = """前書き

| 部品台帳（2026年9月30日現在）　浜松第二工場 資材係 |  |  |  |  |  |  |
|---|---|---|---|---|---|---|
| 部品番号 | 名称 | 適用機種 | 単価（円） | 在庫 | 発注点 | 仕入先コード |
| P-1042 | シールキット SK-300 | HP-300 / HP-320 | 18,400 | 6 | 10 | S-07 |
| P-1043 | メカニカルシール MS-30 | HP-300 / HP-320 | 24800 | 4 | 4 | S-07 |
| P-2011 | 軸受 6309ZZ | HP-320 | 3980 | 9 | 12 | S-02 |
| P-4002 | グリス KG-2 | HP-320 | 900 円 | 12 | 0 | S-02 |

後書き

| 月 | 件数 |
|---|---|
| 8月 | 3 |
"""


def ledger():  # type: ignore[no-untyped-def]
    return parse_tables(LEDGER)[0]


def test_title_row_becomes_title_and_next_row_the_header() -> None:
    tables = parse_tables(LEDGER)
    assert len(tables) == 2
    t = tables[0]
    assert t.title.startswith("部品台帳") and len(t.rows) == 4
    # 括弧の単位を除いた名前で式を書ける
    assert t.aliases() == ["部品番号", "名称", "適用機種", "単価", "在庫", "発注点", "仕入先コード"]
    assert tables[1].title == "" and tables[1].header == ["月", "件数"]


def test_cells_are_typed() -> None:
    assert str(to_value("18,400")) == "18400" and str(to_value("900 円")) == "900"
    assert str(to_value("０．８%")) == "0.8"
    assert to_value("P-1042") == "P-1042" and to_value("") is None and to_value("—") is None


def test_rows_are_selected_by_comparing_columns() -> None:
    # 在庫 4・発注点 4 は「下回る」に入らない（小さいモデルが目で比べて誤る行）
    r = run_query(ledger(), "在庫 < 発注点")
    assert [row[0] for row in r.matched] == ["P-1042", "P-2011"]
    assert str(r.totals["在庫"]) == "15" and "部品番号" not in r.totals


def test_compute_gives_per_row_values_and_totals() -> None:
    r = run_query(ledger(), "在庫 < 発注点", "(発注点 - 在庫) * 単価")
    assert [str(v) for v in r.computed] == ["73600", "11940"]
    text = render(r, "在庫 < 発注点", "(発注点 - 在庫) * 単価")
    assert "4 行" in text and "2 行" in text and "合計 85540" in text and "| 73600 |" in text


@pytest.mark.parametrize(
    "where",
    [
        "在庫 ＜ 発注点",
        "在庫<発注点 AND 単価（円） >= 10,000",
        '適用機種 contains "HP-300" かつ 在庫 ≦ 6 and 発注点 = 10',
        '"SK-300" in 名称 or 仕入先コード == "S-99"',
        "not (在庫 >= 発注点) and 単価 > 5000",
    ],
)
def test_common_ways_of_writing_conditions_are_accepted(where: str) -> None:
    assert next(row[0] for row in run_query(ledger(), where).matched) == "P-1042"


def test_unknown_column_lists_the_available_ones() -> None:
    with pytest.raises(TableError, match="列「在庫数」はありません。使える列: 部品番号"):
        run_query(ledger(), "在庫数 < 発注点")


@pytest.mark.parametrize(
    "expr", ["在庫 <", "__import__('os')", "在庫.real < 1", "len(名称) > 1", "在庫 ** 99"]
)
def test_unreadable_or_unsafe_expressions_are_rejected(expr: str) -> None:
    with pytest.raises(TableError):
        run_query(ledger(), expr)


def test_no_condition_returns_all_rows_and_empty_result_is_stated() -> None:
    assert len(run_query(ledger()).matched) == 4
    text = render(run_query(ledger(), "在庫 > 100"), "在庫 > 100", "")
    assert "0 行" in text and "|" not in text.split("\n", 1)[-1] if "\n" in text else True
