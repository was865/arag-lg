"""引用の刈り込み（specs/026 T31）。値を書いていない資料の番号を、その文から外す。"""

from arag.agent.citations import CitationRegistry, finalize_citations
from arag.agent.prune import prune_citations

MATERIALS = {
    1: "第3版: ケーシングボルトの締付トルクは 52 N·m とする。",
    2: "第2版: ケーシングボルトの締付トルクは 45 N·m とする。",
    3: "品質会議: シール部の漏れ対策として締付トルクを見直すことにした。",
}


def test_only_citations_holding_the_value_are_kept() -> None:
    text, pruned = prune_citations("締付トルクは 52 N·m です [1][2][3]。", MATERIALS)
    assert text == "締付トルクは 52 N·m です [1]。"
    assert pruned == [
        {"sentence": "締付トルクは 52 N·m です [1][2][3]。", "removed": [2, 3], "kept": [1], "values": ["52"]}
    ]


def test_untouched_when_no_citation_holds_a_value() -> None:
    text = "締付トルクは 60 N·m です [2][3]。"
    assert prune_citations(text, MATERIALS) == (text, [])


def test_untouched_without_values_or_with_one_citation() -> None:
    no_value = "シール部の漏れ対策として見直しました [1][3]。"
    assert prune_citations(no_value, MATERIALS) == (no_value, [])
    one = "締付トルクは 52 N·m です [3]。"
    assert prune_citations(one, MATERIALS) == (one, [])
    # 1 桁の整数は値に数えない
    small = "手順は 3 つです [1][3]。"
    assert prune_citations(small, MATERIALS) == (small, [])


def test_codes_count_as_values_and_each_sentence_is_separate() -> None:
    materials = {1: "グリスは KG-5 を使う。", 2: "Oリングは毎回交換する。", 3: "KG-2 は廃止予定。"}
    text, pruned = prune_citations("グリスは KG-5 です[1][3]。Oリングは交換します[1][2]。", materials)
    assert text == "グリスは KG-5 です[1]。Oリングは交換します[1][2]。"
    assert [p["removed"] for p in pruned] == [[3]]


def test_table_rows_and_bullets_are_one_sentence_per_line() -> None:
    materials = {1: "HP-300 の最大吐出量 300 L/min", 2: "HP-320 の最大吐出量 320 L/min", 3: "価格表"}
    text = (
        "| 項目 | HP-300 | HP-320 |\n|---|---|---|\n"
        "| 最大吐出量 | 300 L/min | 320 L/min [1][2][3] |\n- 価格は別紙 [3]"
    )
    out, pruned = prune_citations(text, materials)
    assert "| 最大吐出量 | 300 L/min | 320 L/min [1][2] |" in out and out.endswith("- 価格は別紙 [3]")
    assert pruned[0]["removed"] == [3]


def test_markers_after_the_full_stop_belong_to_the_sentence() -> None:
    out, pruned = prune_citations("締付トルクは 52 N·m です。[1][2] 次の文です。", MATERIALS)
    assert out == "締付トルクは 52 N·m です。[1] 次の文です。" and pruned[0]["kept"] == [1]


def test_removed_documents_disappear_and_numbers_are_renumbered() -> None:
    import uuid

    reg = CitationRegistry()
    for n, body in MATERIALS.items():
        reg.add_section(
            document_id=uuid.uuid4(), document_name=f"d{n}.docx", section_id=uuid.uuid4(),
            heading_path="", page=None, text=body,
        )  # fmt: skip
    text, _ = prune_citations("トルクは 45 N·m です [3][2]。", {c.n: c.text for c in reg.items()})
    fin = finalize_citations(text, reg)
    assert fin.answer == "トルクは 45 N·m です [1]。" and [s["title"] for s in fin.sources] == ["d2.docx"]
