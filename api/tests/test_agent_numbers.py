"""回答の数字の照合（specs/026 R15）。"""

from arag.agent.domain.numbers import numbers_in, ungrounded

SRC = ["| P-1042 | SK-300 | 18400 | 6 | 10 |", "保存は五年間。再点検は十四日以内。不良率 0.8 %。合計 = 73600"]


def test_numbers_written_differently_still_match() -> None:
    answer = (
        "単価は 18,400 円（1万8,400円）[1]。再点検は 14 日以内、不良率は ０．８０％、合計 73,600 円 [2]。"
    )
    assert ungrounded(answer, SRC) == []


def test_numbers_not_in_sources_are_listed_in_order() -> None:
    assert ungrounded("単価は ¥17,800、送料 2,100 円です[1]。在庫 6。", SRC) == ["17,800", "2,100"]


def test_citation_marks_list_heads_and_single_digits_are_ignored() -> None:
    answer = "次の 3 点です[12]。\n1. 在庫を見る[15]\n2) 発注する\n12. 記録する"
    assert ungrounded(answer, SRC) == []


def test_numbers_from_the_question_and_models_count_as_known() -> None:
    assert ungrounded("HP-300 は 2026 年の 45 N·m です", ["HP-300 の 2026 年版", "45 N·m"]) == []
    assert ungrounded("45 N·m から 52 N·m", ["45 N·m"]) == ["52"]


def test_number_extraction() -> None:
    assert numbers_in("1,2 と 1,200 と 3.50") == {"1", "2", "1200", "3.5"}
    assert "250" in numbers_in("二百五十", kanji=True) and "30" in numbers_in("三〇", kanji=True)


def test_numbers_right_after_japanese_text_are_read() -> None:
    # 「温度64」「9月2日」の数字は、前が日本語でも数として拾う（hm43・hm63 の誤検知）
    assert "64" in numbers_in("軸受温度64℃") and "2" in numbers_in("9月2日")
    assert ungrounded("軸受温度は64℃でした[1]", ["軸受温度64℃（要注意）"]) == []
    assert ungrounded("前回は9月12日の点検です", ["前回 9月2日"]) == ["12"]
    # 型番の中の数字は今までどおり数えない
    assert numbers_in("SK300 と v1.25") == set()


# ── 回答の中の内訳から出せる合計・差（specs/026 T24、hm22） ──

PM04 = [
    "| 2026-09-02 | PM-04 | 30 |\n| 2026-09-12 | PM-04 | 25 |\n| 2026-09-19 | PM-04 | 80 |\n| 合計 | | 600 |"
]


def test_sum_of_grounded_numbers_in_the_answer_is_derived() -> None:
    from arag.agent.domain.numbers import check_numbers

    answer = "停止時間は合計 135 分です。\n- 30 分 [1]\n- 25 分 [1]\n- 80 分 [1]"
    assert ungrounded(answer, PM04) == []
    res = check_numbers(answer, PM04)
    assert res.missing == []
    assert res.derived == [{"value": "135", "op": "sum", "from": ["30", "25", "80"]}]


def test_sum_is_not_derived_when_a_part_is_not_grounded() -> None:
    # 70 は資料に無いので材料にしない → 135 も 70 も未確認のまま
    answer = "合計 135 分です（30 分・25 分・70 分）"
    assert ungrounded(answer, PM04) == ["135", "70"]


def test_difference_of_two_grounded_numbers_is_derived() -> None:
    from arag.agent.domain.numbers import check_numbers

    res = check_numbers("80 分と 25 分で、差は 55 分です", PM04)
    assert res.missing == [] and res.derived == [{"value": "55", "op": "diff", "from": ["80", "25"]}]


def test_no_rescue_when_answer_has_more_than_twelve_grounded_numbers() -> None:
    src = [" ".join(str(n) for n in range(10, 23))]  # 10〜22 の 13 個
    answer = " ".join(str(n) for n in range(10, 23)) + " の合計は 21 + 22 = 43"
    assert ungrounded(answer, src) == ["43"]


def test_products_are_not_derived() -> None:
    # 25 × 30 = 750 は和でも差でもないので未確認のまま（calculate を使わせる）
    assert ungrounded("25 分 × 30 回 = 750 分", PM04) == ["750"]
