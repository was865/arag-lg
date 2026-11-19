"""回答評価の純関数とケース実行（specs/005-agent E1・R33）。"""

from typing import Any

import pytest

from arag.eval.answer import (
    CaseResult,
    citation_precision,
    citation_recall,
    cited_documents,
    cited_sources,
    declines,
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
        # モデルのツールではないステップ（システムの処理・考えた過程・見直し・モデルの切り替え）は数えない
        {"id": "s1", "name": "system", "parent_id": None, "input": {"kind": "force_tool"}},
        {"id": "t1", "name": "reasoning", "parent_id": None, "input": {}},
        {"id": "v1", "name": "review", "parent_id": None, "input": {}},
        {"id": "m1", "name": "switch_model", "parent_id": None, "input": {}},
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
        self.threads: list[str | None] = []

    async def start(self, body: dict[str, Any], thread_id: str | None = None) -> tuple[str, str]:
        self.bodies.append(body)
        self.threads.append(thread_id)
        return f"r{len(self.bodies)}", "t1"

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
    # 人手ラベル（E2）と突き合わせるため、評価者の判定と見せた資料を全部残す
    assert r.claims == [{"text": "停止", "verdict": "supported"}]
    assert [x["n"] for x in r.judge_sources] == [1, 2]
    assert r.tool_calls == 1 and r.tokens == 1200 and r.duration_ms == 4000
    assert r.no_answer is False


async def test_run_case_failed_run_counts_as_zero() -> None:
    api = FakeApi([("run.failed", {"type": "run.failed", "code": "generation_failed", "message": "失敗"})])
    r = await run_case(api, Case(id="q", query="x", relevant_documents=["a.pdf"]), kb_id="k", model_id=None)
    assert r.status == "failed" and r.error == "失敗"
    assert r.citation_recall == 0.0 and r.faithfulness is None


async def test_run_case_asks_previous_turns_in_same_thread() -> None:
    # 続けて尋ねる題（specs/018 R4）: 前の質問を同じスレッドで順に尋ね、最後の質問だけを採点する
    api = FakeApi([("run.completed", COMPLETED)])
    case = Case(
        id="m", query="その前の値は？", turns=["MX-17 は？", "単位は？"], key_facts=[KeyFact(any=["0.91"])]
    )
    r = await run_case(api, case, kb_id="kb1", model_id=None)
    assert [b["query"] for b in api.bodies] == ["MX-17 は？", "単位は？", "その前の値は？"]
    assert api.threads == [None, "t1", "t1"]
    assert all(b["kb_ids"] == ["kb1"] for b in api.bodies)
    assert r.status == "completed" and r.query == "その前の値は？"


async def test_run_case_fails_when_previous_turn_fails() -> None:
    api = FakeApi([("run.failed", {"type": "run.failed", "code": "x", "message": "失敗"})])
    case = Case(id="m", query="続き", turns=["最初"], relevant_documents=["a.pdf"])
    r = await run_case(api, case, kb_id="k", model_id=None)
    assert r.status == "failed" and r.error is not None and "前の質問" in r.error
    assert len(api.bodies) == 1


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


def test_facts_matched_normalizes_dates() -> None:
    from arag.eval.answer import facts_matched

    facts = [["2026-06-05"], ["2026/06/07"], ["ＡＢＣ"]]
    assert facts_matched("納期は2026年6月5日です", facts) == [True, False, False]
    assert facts_matched("期限 2026/6/7", [["2026年6月7日"]]) == [True]


@pytest.mark.parametrize(
    "answer",
    [
        "AlphaGate X2 の消費電力は明示されていません。",
        "資料には記載がありません。",
        "具体的なエスカレーション先については明記されていない。",
        "The documents do not mention the power consumption.",
        "This is not specified in the documents.",
    ],
)
def test_declines_detects_absence(answer: str) -> None:
    assert declines(answer)


@pytest.mark.parametrize(
    "answer",
    [
        "温度センサーT2の校正基準は 80.0℃ です [1]。",
        "部長承認を省略できる条件は、低リスク顧客に限られます [1]。",
    ],
)
def test_declines_rejects_made_up_answers(answer: str) -> None:
    assert not declines(answer)


@pytest.mark.parametrize(
    ("answer", "reason", "coverage"),
    [
        ("消費電力は資料に記載されていません。", None, 1.0),
        ("", "no_relevant_sources", 1.0),
        ("校正基準は 80.0℃ です [1]。", None, 0.0),
    ],
)
async def test_run_case_scores_expected_no_answer(answer: str, reason: str | None, coverage: float) -> None:
    api = FakeApi([("run.completed", {**COMPLETED, "answer": answer, "no_answer_reason": reason})])
    case = Case(id="n1", query="消費電力は？", tags=["ja", "negative"], expect_no_answer=True)
    r = await run_case(api, case, kb_id="kb1", model_id=None)
    assert r.fact_coverage == coverage


def test_facts_matched_ignores_markdown_bold() -> None:
    """回答の太字（**6**）で事実の照合が外れないようにする。"""
    from arag.eval.answer import facts_matched

    assert facts_matched("在庫数は **6** です", [["在庫数は6", "在庫数は 6"]]) == [True]


def test_declines_not_directly_provided() -> None:
    from arag.eval.answer import declines

    assert declines("The email address is not directly provided in the search results.")


async def test_run_case_flags_wrong_facts() -> None:
    """答えの中の誤りの値（wrong_facts）を拾う。

    正しい値も書いてあれば key_facts は当たるので、別に見る（specs/021）。
    """
    answer = "合計は **600分** です。30 + 25 + 80 = 135分[1]。"
    api = FakeApi([("run.completed", COMPLETED | {"answer": answer})])
    wrong = [KeyFact(any=["600分", "600 分"])]
    case = Case(id="w", query="合計は？", key_facts=[KeyFact(any=["135"])], wrong_facts=wrong)
    r = await run_case(api, case, kb_id="k", model_id=None)
    assert r.fact_coverage == 1.0
    assert r.wrong_facts_found == ["600分"]


def test_summarize_wrong_fact_rate_counts_only_cases_with_wrong_facts() -> None:
    rs = [
        _result(id="a", wrong_facts_found=["600分"], wrong_checked=True),
        _result(id="b", wrong_facts_found=[], wrong_checked=True),
        _result(id="c"),  # wrong_facts の無い題は数えない
    ]
    s = summarize(rs)
    assert s["wrong_fact_rate"] == 0.5
    assert summarize([_result(id="c")])["wrong_fact_rate"] is None
    md = to_markdown({"suite": "demo", "model_id": None, "summary": s, "cases": [r.__dict__ for r in rs]})
    assert "| 誤りの記述 |" in md and "- a: 600分" in md


@pytest.mark.parametrize(
    "answer",
    [
        # hm57（Gemma 4 12B）: 「含まれていません」「お答えすることができません」
        "提供された検索結果の中には、9月の生産台数を示す表やデータが含まれていません。お答えすることができません。",
        # hm58（Gemma 4 12B）: 「資料からは確認できません」
        "10月の出荷検査の不良率に関する実績は、現在の資料からは確認できません。",
        "生産台数に関する数値は含まれていません。",
        # hm58（026d）: 情報を指す語と「含まれていません」の間に「資料内に」が入る
        "現在、10月の出荷検査の不良率に関する実績データは資料内に含まれていません。",
        # hm60（026d）: 「could not find」
        "I'm sorry, but I could not find the email address for the Aster Seals sales contact "
        "in the provided documents.",
    ],
)
def test_declines_detects_not_included_or_not_confirmable(answer: str) -> None:
    assert declines(answer)


@pytest.mark.parametrize(
    "answer",
    [
        # 値を答えたうえで補足として「含まれていません」と書く回答は、断りとみなさない
        "価格は 12,000 円です [1]。送料は含まれていません。",
        "納期は 5 日です [1]。",
        "送料は資料内に含まれていません。価格は 12,000 円です [1]。",
    ],
)
def test_declines_ignores_incidental_phrases(answer: str) -> None:
    assert not declines(answer)


# 答えの無い題で「資料に無い」と答えつつ、近い資料を引用したときの引用精度（2026-11-13 の規則）
@pytest.mark.parametrize(
    ("answer", "reason", "wrong", "precision"),
    [
        # 資料に無いと述べ、近い資料を引用 → 罰しない
        ("HP-350 の記載はありません。HP-300 は 300 L/min です [1]。", None, [], 1.0),
        # 回答不能（no_answer_reason）も同じ
        ("近い資料: [1]", "no_relevant_sources", [], 1.0),
        # 値を言い切った → 引用した資料は無関係なので 0 のまま
        ("最大吐出量は 350 L/min です [1]。", None, [], 0.0),
        # 資料に無いと述べても、誤りの値を書いたら 0 のまま
        ("HP-350 の記載はありません。ただし 350 L/min と思われます [1]。", None, ["350 L/min"], 0.0),
    ],
)
async def test_run_case_noans_citation_precision(
    answer: str, reason: str | None, wrong: list[str], precision: float
) -> None:
    api = FakeApi([("run.completed", {**COMPLETED, "answer": answer, "no_answer_reason": reason})])
    case = Case(
        id="n2",
        query="HP-350 の最大吐出量は？",
        tags=["ja", "noans"],
        expect_no_answer=True,
        wrong_facts=[KeyFact(any=wrong)] if wrong else [],
    )
    r = await run_case(api, case, kb_id="kb1", model_id=None)
    assert r.cited_documents  # 近い資料を引用している
    assert r.citation_precision == precision


async def test_run_case_normal_case_precision_unchanged_by_decline() -> None:
    """答えのある題は、「資料に無い」と述べても今までどおり引用の当たりで測る。"""
    api = FakeApi([("run.completed", {**COMPLETED, "answer": "記載はありません [1][2]。"})])
    case = Case(id="r", query="停止？", relevant_documents=["a.pdf"])
    r = await run_case(api, case, kb_id="kb1", model_id=None)
    assert r.citation_precision == citation_precision(set(r.cited_documents), ["a.pdf"])
    assert r.citation_precision < 1.0


def test_citation_precision_counts_acceptable_documents() -> None:
    """同じ事実を載せた別の資料（acceptable_documents）の引用は、精度で誤りに数えない（specs/026 T23）。"""
    assert citation_precision({"a.pdf", "b.pdf"}, ["a.pdf"], ["b.pdf"]) == 1.0
    assert citation_precision({"a.pdf", "b.pdf", "c.pdf"}, ["a.pdf"], ["b.pdf"]) == pytest.approx(2 / 3)
    # 許容の資料だけを引用しても、再現率は relevant だけで測る
    assert citation_recall({"b.pdf"}, ["a.pdf"]) == 0.0


async def test_run_case_uses_acceptable_documents_for_precision_only() -> None:
    # 回答は a.pdf（[1]）と b.pdf（[2]）を引用する
    api = FakeApi([("run.completed", COMPLETED)])
    case = Case(id="r", query="停止？", relevant_documents=["a.pdf"], acceptable_documents=["b.pdf"])
    r = await run_case(api, case, kb_id="kb1", model_id=None)
    assert set(r.cited_documents) == {"a.pdf", "b.pdf"}
    assert r.citation_precision == 1.0 and r.citation_recall == 1.0


# ── 聞き返し（specs/031 T12） ──


def test_clarified_detects_model_and_system_clarify() -> None:
    from arag.eval.answer import clarified

    assert not clarified([{"id": "s", "name": "search", "input": {}}])
    assert clarified([{"id": "a", "name": "ask_user", "input": {"question": "どれ？"}}])
    assert clarified(
        [{"id": "c", "name": "system", "input": {"kind": "clarify", "reason": "document_unspecified"}}]
    )
    # 聞き返しを外した記録（ask_user_blocked）は聞き返しではない
    assert not clarified([{"id": "b", "name": "system", "input": {"kind": "ask_user_blocked"}}])


async def test_run_case_scores_expected_clarify() -> None:
    step = {"id": "c", "name": "system", "parent_id": None, "status": "done", "input": {"kind": "clarify"}}
    asked = {**COMPLETED, "answer": "どの資料についてですか？", "citation_map": {}, "sources": []}
    api = FakeApi([("step", {"type": "step", "step": step}), ("run.completed", asked)])
    # 聞き返すべき題: 聞き返せば事実網羅 1.0
    r = await run_case(
        api, Case(id="c", query="この資料の要点は？", expect_clarify=True), kb_id="k", model_id=None
    )
    assert r.clarified is True and r.expect_clarify is True and r.fact_coverage == 1.0
    # 聞き返す必要の無い題で聞き返すと、答えの事実が無いので網羅は 0
    case = Case(
        id="n", query="HP-300 の締付トルクは？", expect_clarify=False, key_facts=[KeyFact(any=["52"])]
    )
    r2 = await run_case(api, case, kb_id="k", model_id=None)
    assert r2.clarified is True and r2.fact_coverage == 0.0
    # 答えた（聞き返さなかった）なら、聞き返すべき題では 0
    api2 = FakeApi([("run.completed", COMPLETED)])
    r3 = await run_case(
        api2, Case(id="c", query="この資料の要点は？", expect_clarify=True), kb_id="k", model_id=None
    )
    assert r3.clarified is False and r3.fact_coverage == 0.0


def test_summarize_clarify_rates() -> None:
    rs = [
        _result(id="a", clarified=True, expect_clarify=True),
        _result(id="b", clarified=False, expect_clarify=True),
        _result(id="c", clarified=True, expect_clarify=False),
        _result(id="d", clarified=False, expect_clarify=False),
        _result(id="e", clarified=False, expect_clarify=False),
        _result(id="f"),  # 聞き返しを見ない題
    ]
    s = summarize(rs)
    assert s["clarify_rate"] == pytest.approx(2 / 6)
    assert s["clarify_recall"] == 0.5
    assert s["over_clarify_rate"] == pytest.approx(1 / 3)
    assert summarize([_result(id="f")])["clarify_recall"] is None
    md = to_markdown({"suite": "demo", "model_id": None, "summary": s, "cases": [r.__dict__ for r in rs]})
    assert "| 聞き返すべき題で聞き返した |" in md and "| a | completed/聞き返し |" in md


# ── 社内システムの題（specs/032 R27・R29） ──


async def test_run_case_checks_systems_leaks_and_caveats() -> None:
    step = {
        "id": "t1",
        "name": "erp__get_stock",
        "parent_id": None,
        "status": "done",
        "input": {"part": "SK-300"},
    }
    answer = {**COMPLETED, "answer": "今（11/18 時点）の在庫は 15 個です[1]。仕入単価は 23,900 円です[2]。"}
    api = FakeApi([("step", {"type": "step", "step": step}), ("run.completed", answer)])
    case = Case(
        id="s1",
        query="SK-300 の今の在庫は？",
        expect_tools=["erp"],
        must_not=[KeyFact(any=["23900", "23,900"])],
        expect_caveat=[KeyFact(any=["時点", "現在"])],
    )
    r = await run_case(api, case, kb_id="k", model_id=None)
    assert r.systems_called == ["erp"] and r.tools_ok is True
    assert r.leaked == ["23,900"] and r.caveat_ok is True
    # 期待したシステムを呼ばなければ tools_ok は False。期待が無ければ None（率に数えない）
    api2 = FakeApi([("run.completed", COMPLETED)])
    r2 = await run_case(api2, case, kb_id="k", model_id=None)
    assert r2.systems_called == [] and r2.tools_ok is False and r2.caveat_ok is False
    r3 = await run_case(
        FakeApi([("run.completed", COMPLETED)]), Case(id="d", query="x"), kb_id="k", model_id=None
    )
    assert r3.tools_ok is None and r3.caveat_ok is None and r3.leaked == []


def test_expected_tools_allow_alternatives() -> None:
    from arag.eval.answer import expected_tools_called

    assert expected_tools_called(["cmms|tickets"], ["cmms"])
    assert expected_tools_called(["erp", "cmms|tickets"], ["tickets", "erp"])
    assert not expected_tools_called(["erp", "cmms|tickets"], ["erp"])


async def test_run_case_sets_and_clears_faults() -> None:
    calls: list[dict[str, str]] = []

    async def faults(spec: dict[str, str]) -> None:
        calls.append(spec)

    api = FakeApi([("run.completed", COMPLETED)])
    await run_case(
        api, Case(id="f", query="x", faults={"cmms": "down"}), kb_id="k", model_id=None, faults=faults
    )
    assert calls == [{"cmms": "down"}, {}]
    # 障害の無い題では触らない
    calls.clear()
    await run_case(api, Case(id="g", query="x"), kb_id="k", model_id=None, faults=faults)
    assert calls == []


def test_summarize_system_rates() -> None:
    rs = [
        _result(id="a", tools_ok=True, leaked=[], leak_checked=True, caveat_ok=True),
        _result(id="b", tools_ok=False, leaked=["23900"], leak_checked=True, caveat_ok=False),
        _result(id="c"),
    ]
    s = summarize(rs)
    assert s["system_recall"] == 0.5 and s["leak_rate"] == 0.5 and s["caveat_rate"] == 0.5
    md = to_markdown({"suite": "s", "model": None, "judge": None, "summary": summarize(rs), "cases": []})
    assert "システムの呼び出し" in md and "漏れ" in md
