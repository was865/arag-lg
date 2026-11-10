"""回答末尾の言い直しを落とす。"""

# ruff: noqa: E501 — 実際の回答をそのまま使うため

from arag.agent.answer_text import drop_repeated_tail

# 実際に出た回答（Qwen3 8B）。最後の段落は 1 つ目の箇条書きの言い直し
MX17 = """MX-17 の異常時の対応は以下の通りです：

- **異常の判定**: MX-17 は「停止候補」と判定され、注記コード N9 により即時停止推奨に該当しています。ただし、部品到着予定が翌営業日AMであるため、夜間停止枠までの運転継続を例外的に認める [1]。
- **対応手順**: 点検で異常が見つかった場合は、直ちに設備を停止し、保全課（内線 2417）に連絡する必要があります [2]。
- **再点検**: 判定が「要注意」の場合は、7日以内に再点検を行い、結果を月次点検票に記録する必要があります [2]。

MX-17 は「停止候補」と判定され、部品到着予定が翌営業日AMであるため、夜間停止枠までの運転継続が許可されています [1]。"""


def test_drops_restated_closing_paragraph() -> None:
    out = drop_repeated_tail(MX17)
    assert out.endswith("月次点検票に記録する必要があります [2]。")
    assert out.count("夜間停止枠") == 1


def test_keeps_new_information_and_short_closings() -> None:
    new_tail = (
        MX17.rsplit("\n\n", 1)[0] + "\n\n部品が届かない場合は、保全課長の判断で翌日の停止枠に回します [3]。"
    )
    assert drop_repeated_tail(new_tail) == new_tail
    short = "- A は 3 日 [1]。\n- B は 5 日 [2]。\n\n以上です。"
    assert drop_repeated_tail(short) == short


def test_leaves_tables_code_and_short_answers_alone() -> None:
    table = "| 設備 | 判定 |\n|---|---|\n| MX-17 | 停止候補 |\n\nMX-17 は停止候補です。MX-17 は停止候補です。"
    assert drop_repeated_tail(table) == table
    two = "MX-17 は停止候補と判定された [1]。\nMX-17 は停止候補と判定された [1]。"
    assert drop_repeated_tail(two) == two
