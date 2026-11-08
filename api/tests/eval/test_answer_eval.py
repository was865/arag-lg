"""回答評価の純関数とケース実行（specs/005-agent E1・R33）。"""

from typing import Any

import pytest

from arag.eval.answer import (
    CaseResult,
    citation_precision,
    citation_recall,
    cited_documents,
    cited_sources,
    faithfulness_from_claims,
    iter_sse,
    run_case,
    summarize,
    to_markdown,
    trajectory,
)
from arag.eval.dataset import Case, KeyFact

COMPLETED: dict[str, Any] = {
    "type": "run.completed",
    "message_id": "m1",
    "answer": "停止します[1]。部品は翌営業日PM[2]。",
    "tokens_in": 1000,
    "tokens_out": 200,
    "duration_ms": 4000,
    "no_answer_reason": None,
    "citation_map": {
        "1": {"source_id": "d1", "section_id": "s1"},
        "2": {"source_id": "d2", "section_id": "s2"},
        "3": {"source_id": "d1", "section_id": "s3"},
    },
    "sources": [
        {
            "id": "d1",
            "title": "a.pdf",
            "score": 0.9,
            "sections": [
                {"id": "s1", "n": 1, "heading": "1 章", "body": "即時停止", "block_type": "text", "page": 1},
                {"id": "s3", "n": 3, "heading": "3 章", "body": "補足", "block_type": "text", "page": 2},
            ],
        },
        {
            "id": "d2",
            "title": "b.pdf",
            "score": 0.7,
            "sections": [
                {
                    "id": "s2",
                    "n": 2,
                    "heading": "2 章",
                    "body": "翌営業日PM",
                    "block_type": "text",
                    "page": 1,
                },
            ],
        },
    ],
}


def test_cited_documents_and_sources() -> None:
    assert cited_documents(COMPLETED) == ["a.pdf", "b.pdf"]
    srcs = cited_sources(COMPLETED)
    # [3] は回答に書かれていないので引用に数えない
    assert [s["n"] for s in srcs] == [1, 2]
    assert cited_documents(COMPLETED | {"answer": "引用なし"}) == []
    assert srcs[1] == {"n": 2, "title": "b.pdf", "heading": "2 章", "body": "翌営業日PM"}


def test_citation_recall_precision() -> None:
    assert citation_recall({"a.pdf"}, ["a.pdf", "b.pdf"]) == 0.5
    assert citation_recall(set(), []) == 1.0
    assert citation_precision({"a.pdf", "c.pdf"}, ["a.pdf"]) == 0.5
    assert citation_precision(set(), ["a.pdf"]) == 0.0
    # 根拠の無い題（relevant 空）で何も引用しなければ精度は満点
    assert citation_precision(set(), []) == 1.0


def test_trajectory_counts_model_tools_and_search_attempts() -> None:
    steps = [
        {"id": "c1", "name": "search", "parent_id": None, "input": {}},
        {"id": "c1:r1", "name": "retrieve", "parent_id": "c1", "input": {}},
        {"id": "c1:rw", "name": "rewrite_query", "parent_id": "c1", "input": {}},
        {"id": "c1:r2", "name": "retrieve", "parent_id": "c1", "input": {}},
        {"id": "c2", "name": "read_section", "parent_id": None, "input": {}},
    ]
    assert trajectory(steps) == {"tool_calls": 2, "search_calls": 1, "retrieve_attempts": 2, "rewrites": 1}


def test_faithfulness_from_claims() -> None:
    claims = [
        {"text": "a", "verdict": "supported"},
        {"text": "b", "verdict": "unsupported"},
        {"text": "c", "verdict": "not_a_claim"},
    ]
    assert faithfulness_from_claims(claims) == (0.5, ["b"])
    assert faithfulness_from_claims([{"text": "x", "verdict": "not_a_claim"}]) == (None, [])


async def test_iter_sse_parses_named_events() -> None:
    async def lines() -> Any:
        for ln in [
            "id: 1-0",
            "event: step",
            'data: {"a": 1}',
            "",
            ": ping",
            "event: run.completed",
            "data: {}",
            "",
        ]:
            yield ln

    assert [e async for e in iter_sse(lines())] == [("step", {"a": 1}), ("run.completed", {})]


class FakeApi:
    """POST /v1/runs と GET stream だけを真似る。"""

    def __init__(self, events: list[tuple[str, dict[str, Any]]]) -> None:
        self.events = events
        self.bodies: list[dict[str, Any]] = []

    async def start(self, body: dict[str, Any]) -> str:
        self.bodies.append(body)
        return "r1"

    async def stream(self, run_id: str) -> Any:
        for e in self.events:
            yield e


async def test_run_case_collects_metrics() -> None:
    api = FakeApi(
        [
            (
                "step",
                {
                    "type": "step",
                    "step": {"id": "c1", "name": "search", "parent_id": None, "status": "running"},
                },
            ),
            (
                "step",
                {"type": "step", "step": {"id": "c1", "name": "search", "parent_id": None, "status": "done"}},
            ),
            ("run.completed", COMPLETED),
        ]
    )
    case = Case(
        id="q1",
        query="MX-17 は？",
        relevant_documents=["a.pdf"],
        key_facts=[KeyFact(any=["即時停止", "停止"]), KeyFact(any=["0.91"])],
    )

    async def judge(query: str, answer: str, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        assert sources and answer
        return [{"text": "停止", "verdict": "supported"}]

    r = await run_case(api, case, kb_id="kb1", model_id="qwen", judge=judge)
    assert api.bodies == [
        {"query": "MX-17 は？", "kb_ids": ["kb1"], "model_id": "qwen", "include_archived": False}
    ]
    assert r.status == "completed"
    assert r.citation_recall == 1.0 and r.citation_precision == 0.5
    assert r.fact_coverage == 0.5
    assert r.faithfulness == 1.0
    assert r.tool_calls == 1 and r.tokens == 1200 and r.duration_ms == 4000
    assert r.no_answer is False


async def test_run_case_failed_run_counts_as_zero() -> None:
    api = FakeApi([("run.failed", {"type": "run.failed", "code": "generation_failed", "message": "失敗"})])
    r = await run_case(api, Case(id="q", query="x", relevant_documents=["a.pdf"]), kb_id="k", model_id=None)
    assert r.status == "failed" and r.error == "失敗"
    assert r.citation_recall == 0.0 and r.faithfulness is None


def _result(**kw: Any) -> CaseResult:
    base: dict[str, Any] = {
        "id": "q",
        "query": "x",
        "tags": ["ja"],
        "status": "completed",
        "answer": "a",
        "cited_documents": [],
        "relevant_documents": [],
        "citation_recall": 1.0,
        "citation_precision": 1.0,
        "fact_coverage": 1.0,
        "faithfulness": None,
        "unsupported_claims": [],
        "tool_calls": 2,
        "search_calls": 1,
        "retrieve_attempts": 1,
        "rewrites": 0,
        "tokens": 100,
        "duration_ms": 1000,
        "no_answer": False,
        "no_answer_reason": None,
    }
    return CaseResult(**(base | kw))


def test_summarize_and_markdown() -> None:
    rs = [
        _result(id="a", faithfulness=1.0, duration_ms=1000),
        _result(id="b", faithfulness=0.5, duration_ms=3000, citation_recall=0.0, tags=["en"]),
        _result(id="c", faithfulness=None, duration_ms=2000, no_answer=True, status="failed"),
    ]
    s = summarize(rs)
    assert s["n"] == 3
    assert s["citation_recall"] == pytest.approx(2 / 3)
    assert s["faithfulness"] == 0.75  # 判定できなかった題は除く
    assert s["p50_ms"] == 2000 and s["p95_ms"] == 3000
    assert s["no_answer_rate"] == pytest.approx(1 / 3) and s["failed"] == 1
    assert s["by_tag"]["en"]["citation_recall"] == 0.0
    md = to_markdown({"suite": "demo", "model_id": "qwen", "summary": s, "cases": [r.__dict__ for r in rs]})
    assert "| 引用再現率 |" in md and "| b |" in md
