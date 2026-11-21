"""確認（差し戻し）の規則の登録（specs/037 R8〜R10）。LangChain のメッセージを使わずに確かめる。"""

from arag.agent.context import Primer, RunStats
from arag.agent.domain.citations import CitationRegistry
from arag.agent.domain.review_rules import REVIEW_LABELS, RULES, Draft, ToolResult, pick
from arag.agent.domain.tool_output import ToolOutput

TABLE = "| 部品 | 在庫 |\n|---|---|\n| A | 4 |"


def draft(answer: str, *results: ToolResult, **kw: object) -> Draft:
    return Draft(answer=answer, question="質問", results=list(results), registry=CitationRegistry(), **kw)  # type: ignore[arg-type]


def test_rules_have_unique_kinds_and_labels() -> None:
    kinds = [r.kind for r in RULES]
    assert len(kinds) == len(set(kinds))
    assert set(kinds) | {"reason"} == set(REVIEW_LABELS)
    # 今の順（specs/037 R8: 順を変えない）
    assert kinds == [
        "omitted",
        "current",
        "system_missed",
        "system_gap",
        "gap",
        "table",
        "structure",
        "numbers",
    ]


def test_omitted_reads_structure_not_text() -> None:
    outline = ToolResult("get_outline", "章立て（中略の語なし）", out=ToolOutput("", omitted=True))
    found = pick(draft("最後の章は分かりません。", outline))
    assert found is not None and found.kind == "omitted" and found.label == "省略の読み残し"
    # 文に「中略」と書いてあっても、構造が省略なしなら差し戻さない（gap に回る）
    plain = ToolResult("get_outline", "…（中略: 第 2〜9 節は未表示", out=ToolOutput(""))
    other = pick(draft("最後の章は分かりません。", plain, primer_searches=1))
    assert other is not None and other.kind == "gap"


def test_done_kinds_are_skipped_in_order() -> None:
    primer = Primer(table=True, text=TABLE)
    d = draft("A は不明です。", primer=primer, primer_searches=1)
    assert (first := pick(d)) is not None and first.kind == "gap"
    assert (second := pick(d, ["gap"])) is not None and second.kind == "table"
    assert pick(d, ["gap", "table"]) is None


def test_weak_primer_does_not_send_back_gap() -> None:
    d = draft("資料には記載がありません。", primer=Primer(weak=True), primer_searches=1)
    assert pick(d) is None


def test_structure_is_counted_as_its_own_kind() -> None:
    """章の見出しの確認は数字の確認と別に数える（以前は数字の確認に数えていた）。"""
    d = draft("第2章: 架空の見出し です", primer=Primer(text="第1章 はじめに"))
    found = pick(d)
    assert found is not None and found.kind == "structure"
    stats = RunStats()
    stats.count_review(found.kind)
    assert stats.reviewed("structure") == 1 and stats.reviewed("numbers") == 0 and stats.reviews == 1
