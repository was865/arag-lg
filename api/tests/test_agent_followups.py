"""続けて聞く質問の候補（specs/028 R1〜R4・T23）。"""

import asyncio
import json
import uuid
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from arag.agent.domain.citations import Cited
from arag.agent.followups import (
    EXCERPT_CHARS,
    EXCERPT_TOTAL,
    MAX_CHARS,
    check_candidates,
    excerpts,
    parse,
    suggest,
)

from .agent_fakes import FakeToolModel, script


def reply(*pairs: tuple[str, str]) -> AIMessage:
    return AIMessage(
        content=json.dumps({"questions": [{"q": q, "evidence": e} for q, e in pairs]}, ensure_ascii=False)
    )


def test_parse_takes_up_to_three_and_drops_duplicates_question_and_long_ones() -> None:
    long = "あ" * (MAX_CHARS + 1)
    text = reply(
        ("SK-300 の単価は？", "18,400"),
        ("SK-300 の単価は？", "18,400"),
        ("在庫は？", "6"),
        (long, "x"),
        ("仕入先はどこですか？", "S-07"),
        ("リードタイムは？", "21 日"),
    ).text
    cands, err = parse(text, "在庫は？")
    assert err == "" and [c.q for c in cands] == [
        "SK-300 の単価は？",
        "仕入先はどこですか？",
        "リードタイムは？",
    ]
    assert cands[1].evidence == "S-07"


def test_parse_counts_half_width_as_half() -> None:
    # 半角は 1 字を半分に数える（全角 40 字 ≒ 半角 80 字）
    en = "What were the main reasons for production fluctuations in September 2026?"  # 74 字
    cands, _ = parse(reply((en, "a"), ("x" * (MAX_CHARS * 2 + 1), "b")).text, "q")
    assert [c.q for c in cands] == [en]


def test_parse_reads_json_after_thinking_preamble_and_code_fence() -> None:
    body = '{"questions": [{"q": "What is the lead time?", "evidence": "21 days"}]}'
    text = f"<think>考える</think>はい。\n```json\n{body}\n```"
    cands, err = parse(text, "q")
    assert err == "" and cands[0].q == "What is the lead time?" and cands[0].evidence == "21 days"


def test_parse_fails_when_not_json_or_old_form() -> None:
    assert parse("候補はありません", "q")[0] == [] and parse("候補はありません", "q")[1]
    assert parse('{"questions": "在庫は？"}', "q")[1]
    assert parse('["在庫は？"]', "q")[1]
    # 古い形（文字列の配列）は失敗として扱う（根拠が無いので確かめられない）
    cands, err = parse('{"questions": ["在庫は？"]}', "q")
    assert cands == [] and "古い形" in err


async def test_suggest_sends_question_answer_and_titles_only() -> None:
    docs = ["x01\n補充の期限は 10月31日。発注先は S-07。"]
    model = FakeToolModel(messages=script(reply(("補充の期限は？", "10月31日"), ("発注先は？", "S-07"))))
    out = await suggest(model, "在庫は？", "在庫は 6 個です[1]。" + "x" * 3000, ["x01-部品台帳.xlsx"], docs)
    assert out.questions == ("補充の期限は？", "発注先は？") and out.error == "" and out.ms >= 0
    assert out.evidence == (
        {"question": "補充の期限は？", "evidence": "10月31日"},
        {"question": "発注先は？", "evidence": "S-07"},
    )
    system, human = model.calls[0]
    assert isinstance(system, SystemMessage) and isinstance(human, HumanMessage)
    assert "在庫は？" in human.text and "x01-部品台帳.xlsx" in human.text
    # 回答は先頭 1500 字まで
    assert "x" * 1600 not in human.text
    assert "evidence" in system.text


async def test_suggest_times_out_and_reports_errors_without_raising() -> None:
    class Slow(FakeToolModel):
        async def ainvoke(self, *a: Any, **k: Any) -> Any:
            await asyncio.sleep(1)
            return reply(("a", "a"))

    out = await suggest(Slow(messages=script()), "q", "a", [], limit_sec=0.05)
    assert out.questions == () and "打ち切" in out.error

    class Broken(FakeToolModel):
        async def ainvoke(self, *a: Any, **k: Any) -> Any:
            raise RuntimeError("接続できない")

    out = await suggest(Broken(messages=script()), "q", "a", [])
    assert out.questions == () and "接続できない" in out.error


def _cited(n: int, name: str, text: str, score: float | None, heading: str = "") -> Cited:
    i = uuid.uuid4()
    return Cited(
        n=n, item_id=i, document_id=i, document_name=name, section_id=i,
        heading_path=heading, page=None, block_type="text", text=text, score=score,
    )  # fmt: skip


def test_excerpts_take_score_order_up_to_eight_and_cap_length() -> None:
    items = [_cited(n, f"d{n}.pdf", f"本文{n} " + "あ" * 500, score=n / 10) for n in range(1, 11)]
    items.append(_cited(11, "台帳.xlsx", "| 部品 | 在庫 |", score=None, heading="部品台帳 > 一覧"))
    out = excerpts(items)
    # スコアの高い順（d10 から）、最大 8 件、全体で EXCERPT_TOTAL 字まで
    assert out[0].startswith("d10.pdf")
    assert len(out) <= 8 and sum(len(x) for x in out) <= EXCERPT_TOTAL
    assert all(x.count("あ") <= EXCERPT_CHARS for x in out)
    # 見出しがあれば題名の後に付ける。スコアの無いもの（節をまるごと読んだもの）は後ろ
    few = excerpts([_cited(1, "台帳.xlsx", "| 部品 | 在庫 |", None, "一覧"), _cited(2, "a.pdf", "本文", 0.5)])
    assert few[0].startswith("a.pdf") and few[1].startswith("台帳.xlsx（一覧）")


async def test_suggest_wraps_excerpts_as_data() -> None:
    model = FakeToolModel(messages=script(AIMessage(content='{"questions": []}')))
    out = await suggest(model, "q", "a", ["a.pdf"], ["a.pdf\n発注点は 10 個"])
    assert out.questions == () and out.error == ""
    human = model.calls[0][1]
    assert "<資料>" in human.text and "発注点は 10 個" in human.text and "</資料>" in human.text


async def test_suggest_names_the_language_of_the_question() -> None:
    # 抜粋が日本語でも、英語の質問には英語で作らせる（実際の Gemma が日本語で返したため）
    model = FakeToolModel(messages=script(AIMessage(content='{"questions": []}'), AIMessage(content="{}")))
    await suggest(model, "How many units?", "1,284 units.", [], ["月次報告\n生産台数 1,284 台"])
    await suggest(model, "生産台数は？", "1,284 台です。", [], [])
    assert "English" in model.calls[0][1].text
    assert "日本語" in model.calls[1][1].text and "English" not in model.calls[1][1].text


def test_candidates_need_evidence_copied_from_the_excerpts() -> None:
    """検索のスコアでは見分けられなかった「資料に無いことを尋ねる候補」を、根拠の語句で落とす（T23）。"""
    from arag.agent.followups import Candidate

    docs = [
        "x01-部品台帳.xlsx\n| P-1042 | シールキット SK-300 | 18400 | 6 | 10 | S-07 |",
        "w04\n佐伯さんが 10月31日 までに補充する。",
    ]
    kept, dropped = check_candidates(
        [
            Candidate("SK-300 の仕入先コードは？", "S-07"),
            Candidate("SK-300 の保管場所は？", "第2倉庫の棚 B"),  # 抜粋に無い
            Candidate("補充の期限は？", "10 月 31 日 までに"),  # 空白・全角半角の違いは見ない
        ],
        docs=docs,
        question="SK-300 の単価は？",
        answer="SK-300 の単価は 18,400 円です[1]。",
        history=[],
    )
    assert [c.q for c in kept] == ["SK-300 の仕入先コードは？", "補充の期限は？"]
    assert dropped == [
        {"question": "SK-300 の保管場所は？", "reason": "no_evidence", "evidence": "第2倉庫の棚 B"}
    ]


def test_candidates_whose_evidence_is_already_answered_are_dropped() -> None:
    from arag.agent.followups import Candidate

    docs = ["x01\n| P-1042 | シールキット SK-300 | HP-300 / HP-320 | 18400 | 6 | 10 | S-07 |\n在庫は 6 個"]
    history = [("在庫が発注点を下回っている部品は？", "シールキット SK-300（P-1042）の在庫は 6 個です。")]
    kept, dropped = check_candidates(
        [
            Candidate("SK-300 の在庫数は？", "在庫は 6 個"),  # 前の回答の文にそのままある
            Candidate("SK-300 の部品番号は？", "P-1042"),  # 前の回答の文にある
            Candidate("SK-300 の適用機種は？", "HP-300 / HP-320"),  # まだ答えていない
            Candidate(
                "SK-300 の行は？", "P-1042 | シールキット SK-300 | HP-300"
            ),  # 型番・数字がすべて回答にある…ではない
            Candidate("在庫が発注点を下回っている部品は", "S-07"),  # これまでの質問と同じ
        ],
        docs=docs,
        question="SK-300 の単価は？",
        answer="SK-300 の単価は 18,400 円です[1]。",
        history=history,
    )
    assert [c.q for c in kept] == ["SK-300 の適用機種は？", "SK-300 の行は？"]
    reasons = {d["question"]: d["reason"] for d in dropped}
    assert reasons == {
        "SK-300 の在庫数は？": "already_answered",
        "SK-300 の部品番号は？": "already_answered",
        "在庫が発注点を下回っている部品は": "same_question",
    }


def test_long_evidence_is_already_answered_when_all_codes_and_numbers_are_in_the_answer() -> None:
    from arag.agent.followups import Candidate

    docs = ["x01\n| P-1042 | シールキット SK-300 | 18400 |"]
    kept, dropped = check_candidates(
        [Candidate("SK-300 の単価は？", "P-1042 | シールキット SK-300 | 18400")],
        docs=docs,
        question="SK-300 は？",
        answer="シールキット SK-300（部品番号 P-1042）の単価は 18,400 円です。",
        history=[],
    )
    assert kept == [] and dropped[0]["reason"] == "already_answered"


async def test_suggest_records_dropped_with_reasons() -> None:
    model = FakeToolModel(messages=script(reply(("SK-300 の保管場所は？", "棚 B"), ("仕入先は？", "S-07"))))
    out = await suggest(model, "SK-300 は？", "SK-300 です。", [], ["| P-1042 | S-07 |"])
    assert out.questions == ("仕入先は？",)
    assert out.dropped == (
        {"question": "SK-300 の保管場所は？", "reason": "no_evidence", "evidence": "棚 B"},
    )


async def test_suggest_passes_recent_turns() -> None:
    model = FakeToolModel(messages=script(reply()))
    history = [("前の質問です", "x" * 1000)]
    await suggest(model, "SK-300 は？", "SK-300 です。", [], [], history=history)
    human = model.calls[0][1].text
    assert "前の質問です" in human and "x" * 600 in human and "x" * 601 not in human
