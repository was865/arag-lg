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
