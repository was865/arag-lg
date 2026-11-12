"""回答の数字の照合（specs/026 R15）。"""

from arag.agent.numbers import numbers_in, ungrounded

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
