"""質問の理解（specs/026 R1〜R4）。"""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from arag.agent.understand import guard_table, history_text, parse


def test_json_is_read_even_with_surrounding_text() -> None:
    u = parse('```json\n{"kind": "docs", "queries": ["a", "a", " b "], "table": true}\n```', "質問")
    assert u.kind == "docs" and u.queries == ("a", "b") and u.table is True and not u.error


def test_thinking_is_ignored() -> None:
    u = parse('<think>{"kind": "chat"}</think>{"kind": "docs", "queries": ["x"]}', "質問")
    assert u.queries == ("x",)


def test_chat_has_no_queries_and_docs_always_has_one() -> None:
    assert parse('{"kind": "chat", "queries": ["x"]}', "こんにちは").queries == ()
    assert parse('{"kind": "docs", "queries": []}', "質問").queries == ("質問",)
    assert parse('{"queries": ["a", "b", "c", "d"]}', "質問").queries == ("a", "b", "c")


def test_unreadable_output_falls_back_to_the_question() -> None:
    for text in ["わかりません", "{broken", "[1, 2]"]:
        u = parse(text, " 質問 ")
        assert u.kind == "docs" and u.queries == ("質問",) and u.error


def test_history_keeps_last_turns_without_tool_results() -> None:
    msgs = [
        HumanMessage("一つ目"),
        AIMessage("", tool_calls=[{"name": "search", "args": {}, "id": "c"}]),
        ToolMessage("資料", tool_call_id="c"),
        AIMessage("一つ目の答え"),
        HumanMessage("二つ目"),
        AIMessage("二つ目の答え"),
        HumanMessage("三つ目"),
        AIMessage("三つ目の答え"),
    ]
    text = history_text(msgs)
    assert "一つ目" not in text and "資料" not in text
    assert text.splitlines() == [
        "利用者: 二つ目",
        "アシスタント: 二つ目の答え",
        "利用者: 三つ目",
        "アシスタント: 三つ目の答え",
    ]


def test_prompt_limits_table_and_resolves_references_to_the_last_answer() -> None:
    from arag.prompts import load_prompt

    p = load_prompt("agent_understand")
    # 表の集計は、複数の行を選ぶ・数える・集計する・比べるときだけ（1 つの値を読むだけなら false）
    assert "1 つの値を読むだけ" in p and "false" in p
    # 「そこ」「それ」は、まず直前の回答に出た答えを指すとみなす（hm62）
    assert "直前のアシスタントの回答" in p and "そこのリードタイム" in p
    # 表に載っている 1 つの値（ある拠点・ある月の生産台数）を読むだけも false（hm52）
    assert "浜松第2工場の2026年9月の生産台数は" in p


def test_output_form_alone_is_not_table_aggregation() -> None:
    raw = '{"kind": "docs", "queries": ["HP-300 HP-320 仕様"], "table": true}'
    q = "HP-300 と HP-320 の仕様の違いをすべて表にしてください。"
    u = guard_table(parse(raw, q), q)
    assert u.table is False and u.table_overridden is True
    # 集計の語があれば、表にしての言い方があってもモデルの判断どおり
    q2 = "在庫が発注点を下回る部品を表にしてください"
    assert guard_table(parse(raw, q2), q2).table is True
    q3 = "List the specs of HP-300 and HP-320 in a table"
    assert guard_table(parse(raw, q3), q3).table is False
    # 形の指定が無ければ変えない
    q4 = "HP-300 と HP-320 の違いは？"
    assert guard_table(parse(raw, q4), q4).table_overridden is False
