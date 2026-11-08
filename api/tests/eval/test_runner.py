from dataclasses import dataclass

from arag.eval.dataset import Case, GoldenSuite
from arag.eval.runner import ranked_documents, run_suite


@dataclass
class FakeHit:
    document_name: str
    text: str = ""
    section_text: str | None = None


def _suite() -> GoldenSuite:
    return GoldenSuite.model_validate(
        {
            "suite": "t",
            "documents": ["a.pdf", "b.pdf"],
            "cases": [
                {
                    "id": "c1",
                    "query": "q",
                    "top_k": 5,
                    "relevant_documents": ["a.pdf"],
                    "key_facts": [{"any": ["AlphaGate X2"]}],
                }
            ],
        }
    )


async def test_run_suite_uses_section_text_for_facts() -> None:
    async def fake(case: Case) -> list[FakeHit]:
        assert case.top_k == 5
        return [FakeHit("a.pdf", "本文", section_text="採用候補は AlphaGate X2。"), FakeHit("b.pdf")]

    result = await run_suite(_suite(), fake)
    case = result["cases"][0]
    assert case["recall_at_5"] == 1.0 and case["fact_coverage"] == 1.0 and case["n_retrieved"] == 2
    assert result["aggregate"]["recall_at_5"] == 1.0
    assert result["aggregate"]["p50_ms"] >= 0


async def test_run_suite_miss_lowers_metrics() -> None:
    async def fake(case: Case) -> list[FakeHit]:
        return [FakeHit("b.pdf", "無関係")]

    case = (await run_suite(_suite(), fake))["cases"][0]
    assert case["recall_at_5"] == 0.0 and case["fact_coverage"] == 0.0 and case["mrr"] == 0.0


def test_ranked_documents_keeps_first_rank() -> None:
    hits = [FakeHit("b"), FakeHit("a"), FakeHit("b"), FakeHit("c")]
    assert ranked_documents(hits) == ["b", "a", "c"]


async def test_negative_cases_excluded_and_tag_aggregate() -> None:
    suite = GoldenSuite.model_validate(
        {
            "suite": "t",
            "documents": ["a.pdf", "b.pdf"],
            "cases": [
                {"id": "c1", "query": "q", "tags": ["ja"], "relevant_documents": ["a.pdf"]},
                {"id": "c2", "query": "what", "tags": ["en"], "relevant_documents": ["a.pdf"]},
                {"id": "neg", "query": "無い", "tags": ["ja", "negative"]},
            ],
        }
    )

    async def fake(case: Case) -> list[FakeHit]:
        return [FakeHit("a.pdf")] if case.id == "c1" else [FakeHit("b.pdf")]

    result = await run_suite(suite, fake)
    neg = result["cases"][2]
    # 正解文書の無い題（答えが無いことを問う題）は検索指標を持たず、集計から除く
    assert neg["recall_at_5"] is None and neg["mrr"] is None
    assert result["aggregate"]["recall_at_5"] == 0.5
    assert result["by_tag"]["ja"]["recall_at_5"] == 1.0
    assert result["by_tag"]["en"]["recall_at_5"] == 0.0 and result["by_tag"]["en"]["n"] == 1
