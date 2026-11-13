"""エージェントの system prompt の決まりごと。"""

from arag.prompts import load_prompt


def test_system_prompt_prefers_special_provisions() -> None:
    """一般の規定と特例が両方出たら、質問の対象に当てはまる特例で答える（harukaze_mix hm04）。"""
    p = load_prompt("agent_system")
    assert "特例" in p and "にかかわらず" in p


def test_system_prompt_sums_matching_rows_only() -> None:
    """表の一部の行を集計するときは、表の合計行を使わず自分で足す（harukaze_mix hm22）。"""
    p = load_prompt("agent_system")
    assert "「合計」行" in p and "calculate" in p


def test_system_prompt_puts_answer_language_first() -> None:
    """言語の規則は「回答」の先頭。日本語の資料・注意書きがあっても英語の質問には英語で（hm52・hm60）。"""
    p = load_prompt("agent_system")
    answer = p.split("## 回答", 1)[1].strip().splitlines()
    assert "同じ言語で答える" in answer[0]
    assert "英語の質問には英語で答える" in p


def test_system_prompt_cites_only_sources_that_state_the_value() -> None:
    """1 つの文に付ける番号は、その値がそのまま書いてある資料だけ（hm09・hm20・hm48）。"""
    p = load_prompt("agent_system")
    assert "52 N·m です [1][2][3]" in p and "52 N·m です [1]" in p
    assert "別の拠点" in p and "別の版" in p
