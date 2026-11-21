"""表の集計（specs/026 R12・R13）。"""

import pytest

from arag.agent.domain.table import TableError, parse_tables, render, run_query, summarize, to_value

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


@pytest.mark.parametrize("where", ["true", "True", "TRUE", "1", "*", "all", "全部", "すべて", "全行"])
def test_all_rows_spellings_mean_no_condition(where: str) -> None:
    """「全部の行を数える」つもりの書き方は条件なしとして扱う。

    3100 の試走で where="true" が誤りになり、表を数え直せなかった。
    """
    assert len(run_query(ledger(), where).matched) == 4


# ── 集計関数（T11） ──


@pytest.mark.parametrize(
    ("compute", "value"),
    [
        ("max(単価)", "24800"),
        ("MIN(単価)", "900"),
        ("sum(在庫 * 単価)", "256220"),
        ("avg(在庫)", "7.75"),
        ("count()", "4"),
        ("Sum(在庫) / COUNT()", "7.75"),
    ],
)
def test_aggregate_functions_compute_one_value_over_matched_rows(compute: str, value: str) -> None:
    r = run_query(ledger(), "", compute)
    assert r.aggregate is not None and str(r.aggregate) == value
    assert r.computed == []  # 行ごとの計算列は作らない


def test_aggregate_respects_the_condition() -> None:
    r = run_query(ledger(), "在庫 < 発注点", "sum((発注点 - 在庫) * 単価)")
    assert str(r.aggregate) == "85540"


def test_max_and_min_show_the_rows_that_hold_the_value() -> None:
    r = run_query(ledger(), "", "max(単価)")
    text = render(r, "", "max(単価)")
    assert "max(単価) = 24800" in text
    holder = text.split("max(単価) = 24800", 1)[1]
    assert "P-1043" in holder and "P-1042" not in holder
    # 先頭行（件数）は今までどおり（ステップの要約が読む）
    assert text.startswith("表「部品台帳")


def test_row_wise_compute_still_works_alongside_aggregates() -> None:
    r = run_query(ledger(), "在庫 < 発注点", "(発注点 - 在庫) * 単価")
    assert r.aggregate is None and [str(v) for v in r.computed] == ["73600", "11940"]


@pytest.mark.parametrize("compute", ["max(単価) - 単価", "max(max(単価))", "median(単価)", "max()"])
def test_bad_aggregates_are_rejected(compute: str) -> None:
    with pytest.raises(TableError):
        run_query(ledger(), "", compute)


# ── 誤りの案内（T12） ──


def test_every_error_carries_columns_and_an_example() -> None:
    from arag.agent.domain.table import error_hint

    hint = error_hint(ledger())
    assert "使える列: 部品番号" in hint and "例" in hint and "max(" in hint


def test_total_rows_are_not_data_rows() -> None:
    """表に書かれた「合計」の行を足し込むと二重に数える（hm21・hm23: 停止時間の合計が 1200 になった）。"""
    text = "| 設備 | 停止時間（分） |\n|---|---|\n| A | 250 |\n| B | 350 |\n| 合　計 | 600 |\n| Total | 600 |"
    t = parse_tables(text)[0]
    assert len(t.rows) == 2 and len(t.totals) == 2
    r = run_query(t, "", "sum(停止時間)")
    out = render(r, "", "sum(停止時間)")
    assert "600" in out and "1200" not in out and "合計の行 2 つは" in out
    assert [row[0] for row in run_query(t, "", "max(停止時間)").matched] == ["A", "B"]


def test_summarize_gives_rows_and_aggregates_for_the_step() -> None:
    """記録に出す構造（specs/028 R10）。モデルに渡す文（render）は変えない。"""
    r = run_query(ledger(), "在庫 < 発注点", "(発注点 - 在庫) * 単価")
    before = render(r, "在庫 < 発注点", "(発注点 - 在庫) * 単価")
    out = summarize(r, "(発注点 - 在庫) * 単価")
    assert out["rows_total"] == 4 and out["rows_matched"] == 2
    assert out["columns"][-1] == "計算" and out["rows"][0][-1] == "73600"
    assert out["compute_label"] == "計算（(発注点 - 在庫) * 単価）"
    assert out["aggregates"]["計算（(発注点 - 在庫) * 単価）"] == {
        "sum": "85540", "avg": "42770", "max": "73600", "min": "11940",
    }  # fmt: skip
    # ほかの数値の列も集計する（「すべての集計」で見せる）
    assert out["aggregates"]["在庫"] == {"sum": "15", "avg": "7.5", "max": "9", "min": "6"}
    assert render(r, "在庫 < 発注点", "(発注点 - 在庫) * 単価") == before


def test_summarize_aggregate_function_value() -> None:
    r = run_query(ledger(), "", "max(単価)")
    out = summarize(r, "max(単価)")
    assert out["compute_label"] == "計算（max(単価)）" and out["compute_value"] == "24800"
    assert out["rows_matched"] == 4 and "計算" not in out["columns"]


X01 = """| 部品台帳（2026年9月30日現在）　浜松第二工場 資材係 |  |  |  |  |  |  |
|---|---|---|---|---|---|---|
| 部品番号 | 名称 | 適用機種 | 単価（円） | 在庫 | 発注点 | 仕入先コード |
| P-1042 | シールキット SK-300 | HP-300 / HP-320 | 18400 | 6 | 10 | S-07 |
| P-1043 | メカニカルシール MS-30 |  | 24800 | 4 | 4 | S-07 |
| P-2010 | 軸受 6308ZZ | HP-300 | 3150 | 22 | 12 | S-02 |
| P-2011 | 軸受 6309ZZ | HP-320 | 3980 | 9 | 12 | S-02 |
| P-3100 | 羽根車 IM-300 | HP-300 | 56000 | 2 | 1 | S-11 |
| P-3120 | 羽根車 IM-320 | HP-320 | 61500 | 1 | 1 | S-11 |
| P-4001 | グリス KG-5（400g） | 共通 | 2200 | 35 | 20 | S-02 |
| P-4002 | グリス KG-2（400g） | 共通（廃止予定） | 1800 | 12 | 0 | S-02 |
|  |  |  |  |  |  |  |
| 注: 在庫が発注点を下回ったら、資材係が仕入先に発注する。 |  |  |  |  |  |  |
"""


def test_blank_and_note_rows_are_not_data_rows() -> None:
    """x01: 空の行と「注:」の行を「全 10 行」に数えていた（specs/026 T30）。"""
    t = parse_tables(X01)[0]
    assert len(t.rows) == 8
    assert t.notes == ["注: 在庫が発注点を下回ったら、資材係が仕入先に発注する。"]
    r = run_query(t, "在庫 < 発注点", "(発注点 - 在庫) * 単価")
    assert [row[0] for row in r.matched] == ["P-1042", "P-2011"]
    out = render(r, "在庫 < 発注点", "(発注点 - 在庫) * 単価")
    assert "（8 行）" in out and "85540" in out and "注記: 注: 在庫が発注点を下回ったら" in out
    s = summarize(r, "(発注点 - 在庫) * 単価")
    assert s["rows_total"] == 8 and s["notes"] == t.notes
    assert s["aggregates"]["計算（(発注点 - 在庫) * 単価）"]["sum"] == "85540"
    # 索引の本文（Docling）では、注記が 1 列の表になり、区切りの行が続く。区切りの行も数えない
    indexed = X01.replace("|  |  |  |  |  |  |  |\n", "").replace(
        "発注する。 |  |  |  |  |  |  |\n", "発注する。 |\n|----------------------------------|\n"
    )
    t3 = parse_tables(indexed)[0]
    assert len(t3.rows) == 8 and len(t3.notes) == 1
    # 先頭のセルだけでも、注記の言い方でなければデータの行のまま
    t2 = parse_tables("| 名称 | 数 |\n|---|---|\n| A | 1 |\n| B |  |")[0]
    assert len(t2.rows) == 2 and t2.notes == []


# ── 分かれたシート（3100 の試走: 部品台帳が 12 の章に分かれ、2 つ目からは見出しの行が無かった） ──

PART1 = """| 部品台帳（10月末） |  |  |
|---|---|---|
| 部品番号 | 状態 | 在庫 |
| P-1 | 通常 | 3 |
| P-2 | 廃止 | 0 |
"""
PART2 = """| 部品台帳（10月末） |  |  |
|---|---|---|
| P-3 | 廃止 | 0 |
| P-4 | 通常 | 5 |
| P-5 | 廃止 | 1 |
"""


def test_split_sheet_parts_are_joined_under_the_first_header() -> None:
    from arag.agent.domain.table import merge_parts

    joined = merge_parts([parse_tables(PART1), parse_tables(PART2)])
    t = joined[0]
    assert t.header == ["部品番号", "状態", "在庫"]
    assert [r[0] for r in t.rows] == ["P-1", "P-2", "P-3", "P-4", "P-5"]
    assert len(run_query(t, "状態 == '廃止'").matched) == 3


def test_continuing_tables_inside_one_section_are_joined_too() -> None:
    """1 つの章の中でも、チャンクごとに題名の行が繰り返され、表が 4 つに分かれていた（8 行ずつ）。"""
    from arag.agent.domain.table import merge_parts

    t = merge_parts([parse_tables(PART1 + "\n" + PART2)])
    assert len(t) == 1 and len(t[0].rows) == 5


def test_tables_that_do_not_continue_are_kept_separately() -> None:
    from arag.agent.domain.table import merge_parts

    other = parse_tables("| 別の表 |  |\n|---|---|\n| a | b |\n| 1 | 2 |\n")
    out = merge_parts([parse_tables(PART1), other])
    assert [r[0] for r in out[0].rows] == ["P-1", "P-2"] and out[1].header == ["a", "b"]
