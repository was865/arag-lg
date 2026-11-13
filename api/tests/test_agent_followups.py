"""続けて聞く質問の候補（specs/028 R1〜R4）。"""

import asyncio
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from arag.agent.followups import MAX_CHARS, parse, suggest

from .agent_fakes import FakeToolModel, script


def test_parse_takes_up_to_three_and_drops_duplicates_question_and_long_ones() -> None:
    long = "あ" * (MAX_CHARS + 1)
    text = (
        '{"questions": ["SK-300 の単価は？", "SK-300 の単価は？", "在庫は？", "'
        + long
        + '", "仕入先はどこですか？", "リードタイムは？"]}'
    )
    qs, err = parse(text, "在庫は？")
    assert err == "" and qs == ["SK-300 の単価は？", "仕入先はどこですか？", "リードタイムは？"]


def test_parse_counts_half_width_as_half() -> None:
    # 半角は 1 字を半分に数える（全角 40 字 ≒ 半角 80 字）。
    # 実際の Gemma の英語の候補が 40 字を超えて全部落ちたため
    en = "What were the main reasons for production fluctuations in September 2026?"  # 74 字
    too_long = "x" * (MAX_CHARS * 2 + 1)
    qs, _ = parse('{"questions": ["' + en + '", "' + too_long + '"]}', "q")
    assert qs == [en]


def test_parse_reads_json_after_thinking_preamble_and_code_fence() -> None:
    text = (
        '<think>考える</think>はい、次のとおりです。\n```json\n{"questions": ["What is the lead time?"]}\n```'
    )
    assert parse(text, "q") == (["What is the lead time?"], "")


def test_parse_fails_when_not_json_or_not_a_list() -> None:
    assert parse("候補はありません", "q")[0] == [] and parse("候補はありません", "q")[1]
    assert parse('{"questions": "在庫は？"}', "q")[1]
    assert parse('["在庫は？"]', "q")[1]


async def test_suggest_sends_question_answer_and_titles_only() -> None:
    reply = AIMessage(content='{"questions": ["補充の期限は？", "発注先は？"]}')
    model = FakeToolModel(messages=script(reply))
    out = await suggest(model, "在庫は？", "在庫は 6 個です[1]。" + "x" * 3000, ["x01-部品台帳.xlsx"])
    assert out.questions == ("補充の期限は？", "発注先は？") and out.error == "" and out.ms >= 0
    system, human = model.calls[0]
    assert isinstance(system, SystemMessage) and isinstance(human, HumanMessage)
    assert "在庫は？" in human.text and "x01-部品台帳.xlsx" in human.text
    # 回答は先頭 1500 字まで
    assert "x" * 1600 not in human.text


async def test_suggest_times_out_and_reports_errors_without_raising() -> None:
    class Slow(FakeToolModel):
        async def ainvoke(self, *a: Any, **k: Any) -> Any:
            await asyncio.sleep(1)
            return AIMessage(content='{"questions": ["a"]}')

    out = await suggest(Slow(messages=script()), "q", "a", [], limit_sec=0.05)
    assert out.questions == () and "打ち切" in out.error

    class Broken(FakeToolModel):
        async def ainvoke(self, *a: Any, **k: Any) -> Any:
            raise RuntimeError("接続できない")

    out = await suggest(Broken(messages=script()), "q", "a", [])
    assert out.questions == () and "接続できない" in out.error
