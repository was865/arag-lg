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
