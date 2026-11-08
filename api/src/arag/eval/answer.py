"""回答評価（specs/005-agent R33・E1）。旧版 tools/answer-eval を移植し、API 経由で実際の run を解かせる。

題ごとに POST /v1/runs → SSE を最後まで読み、run.completed から指標を出す。runner・検索・モデルは
本番と同じ経路を通るので、評価の数字がそのまま画面の振る舞いになる。

指標:
- 回答の中身（LLM 不要）: 引用再現率・引用精度（文書名で比較）・事実網羅（key_facts の部分一致）
- 忠実度（評価者 LLM）: 回答の事実主張のうち、引用した資料で裏付けられる割合
- 軌跡・コスト: モデルが呼んだツール数・実際に走った検索の回数・書き直し回数・トークン・所要時間・回答不能
"""

import json
import statistics
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Protocol, TypedDict

import httpx
from pydantic import BaseModel, Field

from arag.eval.dataset import Case
from arag.eval.metrics import fact_coverage, normalize_text

TERMINAL = {"run.completed", "run.failed", "run.cancelled"}
SEARCH_TOOLS = {"search", "keyword_search"}

Judge = Callable[[str, str, list[dict[str, Any]]], Awaitable[list[dict[str, Any]]]]


class RunApi(Protocol):
    async def start(self, body: dict[str, Any]) -> str: ...

    def stream(self, run_id: str) -> AsyncIterator[tuple[str, dict[str, Any]]]: ...


@dataclass
class CaseResult:
    id: str
    query: str
    tags: list[str]
    status: str  # completed / failed / cancelled
    answer: str
    cited_documents: list[str]
    relevant_documents: list[str]
    citation_recall: float
    citation_precision: float
    fact_coverage: float
    faithfulness: float | None  # 判定しない・主張が無い・判定失敗は None（平均から除く）
    unsupported_claims: list[str]
    tool_calls: int
    search_calls: int
    retrieve_attempts: int
    rewrites: int
    tokens: int
    duration_ms: int
    no_answer: bool
    no_answer_reason: str | None
    error: str | None = None
    judge_error: str | None = None
    facts_matched: list[bool] = field(default_factory=list)


# ── 純関数 ──────────────────────────────────────────────────────────────


def cited_documents(completed: dict[str, Any]) -> list[str]:
    """引用した文書の名前（出現順・重複なし）。"""
    titles = {s["id"]: s["title"] for s in completed.get("sources", [])}
    out: list[str] = []
    for ref in completed.get("citation_map", {}).values():
        t = titles.get(ref["source_id"], ref["source_id"])
        if t not in out:
            out.append(t)
    return out


def cited_sources(completed: dict[str, Any]) -> list[dict[str, Any]]:
    """引用番号ごとの資料（評価者に渡す）。見つからない番号は除く。"""
    secs = {
        sec["id"]: {"title": s["title"], "heading": sec["heading"], "body": sec["body"]}
        for s in completed.get("sources", [])
        for sec in s["sections"]
    }
    out = []
    for n, ref in sorted(completed.get("citation_map", {}).items(), key=lambda kv: int(kv[0])):
        if (sec := secs.get(ref["section_id"])) is not None:
            out.append({"n": int(n)} | sec)
    return out


def citation_recall(cited: set[str], relevant: list[str]) -> float:
    rel = set(relevant)
    return 1.0 if not rel else len(cited & rel) / len(rel)


def citation_precision(cited: set[str], relevant: list[str]) -> float:
    if not cited:
        # 根拠の無い題で何も引用しないのは正しい振る舞い
        return 1.0 if not relevant else 0.0
    return len(cited & set(relevant)) / len(cited)


class Trajectory(TypedDict):
    tool_calls: int
    search_calls: int
    retrieve_attempts: int
    rewrites: int


def trajectory(steps: list[dict[str, Any]]) -> Trajectory:
    top = [s for s in steps if not s.get("parent_id")]
    return {
        "tool_calls": len(top),
        "search_calls": sum(1 for s in top if s["name"] in SEARCH_TOOLS),
        "retrieve_attempts": sum(1 for s in steps if s.get("parent_id") and s["name"] == "retrieve"),
        "rewrites": sum(1 for s in steps if s["name"] == "rewrite_query"),
    }


def faithfulness_from_claims(claims: list[dict[str, Any]]) -> tuple[float | None, list[str]]:
    checkable = [c for c in claims if c["verdict"] != "not_a_claim"]
    unsupported = [c["text"] for c in checkable if c["verdict"] == "unsupported"]
    if not checkable:
        return None, unsupported
    return 1 - len(unsupported) / len(checkable), unsupported


async def iter_sse(lines: AsyncIterator[str]) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """SSE の行から (event, data) を取り出す。コメント（: ping）は捨てる。"""
    event, data = "message", list[str]()
    async for line in lines:
        if line == "":
            if data:
                yield event, json.loads("\n".join(data))
            event, data = "message", list[str]()
        elif line.startswith(":"):
            continue
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())


def _pct(xs: list[int], q: float) -> int:
    if not xs:
        return 0
    s = sorted(xs)
    # 最近傍順位法（件数が少ないので補間しない）
    return s[min(len(s) - 1, max(0, round(q * len(s) + 0.5) - 1))]


def _mean(xs: list[float]) -> float | None:
    return statistics.fmean(xs) if xs else None


def _block(rs: list[CaseResult]) -> dict[str, Any]:
    durs = [r.duration_ms for r in rs]
    return {
        "n": len(rs),
        "citation_recall": _mean([r.citation_recall for r in rs]),
        "citation_precision": _mean([r.citation_precision for r in rs]),
        "fact_coverage": _mean([r.fact_coverage for r in rs]),
        "faithfulness": _mean([r.faithfulness for r in rs if r.faithfulness is not None]),
        "tool_calls": _mean([float(r.tool_calls) for r in rs]),
        "retrieve_attempts": _mean([float(r.retrieve_attempts) for r in rs]),
        "tokens": _mean([float(r.tokens) for r in rs]),
        "p50_ms": _pct(durs, 0.5),
        "p95_ms": _pct(durs, 0.95),
        "no_answer_rate": _mean([float(r.no_answer) for r in rs]),
        "failed": sum(1 for r in rs if r.status != "completed"),
    }


def summarize(rs: list[CaseResult]) -> dict[str, Any]:
    out = _block(rs)
    tags = sorted({t for r in rs for t in r.tags})
    out["by_tag"] = {t: _block([r for r in rs if t in r.tags]) for t in tags}
    return out


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


ROWS = [
    ("引用再現率", "citation_recall"),
    ("引用精度", "citation_precision"),
    ("事実網羅", "fact_coverage"),
    ("忠実度", "faithfulness"),
    ("ツール呼び出し", "tool_calls"),
    ("検索の実行回数", "retrieve_attempts"),
    ("トークン", "tokens"),
    ("p50 (ms)", "p50_ms"),
    ("p95 (ms)", "p95_ms"),
    ("回答不能率", "no_answer_rate"),
    ("失敗", "failed"),
]


def to_markdown(result: dict[str, Any]) -> str:
    s = result["summary"]
    tags = list(s.get("by_tag", {}))
    lines = [
        f"# 回答評価: {result['suite']}（{result.get('model_id') or '既定'}"
        + (f"、評価者 {result['judge_id']}" if result.get("judge_id") else "")
        + "）",
        "",
        "| 指標 | 全体 | " + " | ".join(tags) + " |",
        "|---|---|" + "---|" * len(tags),
    ]
    for label, key in ROWS:
        cells = [_fmt(s[key])] + [_fmt(s["by_tag"][t][key]) for t in tags]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## 題ごと",
        "",
        "| id | 状態 | 再現 | 精度 | 網羅 | 忠実 | ツール | 時間 (ms) | 引用 | 回答（先頭） |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in result["cases"]:
        excerpt = (c.get("error") or c["answer"]).replace("\n", " ").replace("|", "／")[:60]
        state = c["status"] + (f"/{c['no_answer_reason']}" if c.get("no_answer_reason") else "")
        lines.append(
            f"| {c['id']} | {state} | {_fmt(c['citation_recall'])} | {_fmt(c['citation_precision'])} | "
            f"{_fmt(c['fact_coverage'])} | {_fmt(c['faithfulness'])} | "
            f"{c['tool_calls']} | {c['duration_ms']} | "
            f"{', '.join(c['cited_documents'])} | {excerpt} |"
        )
    unsupported = [(c["id"], u) for c in result["cases"] for u in c.get("unsupported_claims", [])]
    if unsupported:
        lines += ["", "## 裏付けの無い主張", ""] + [f"- {i}: {u}" for i, u in unsupported]
    return "\n".join(lines) + "\n"


# ── 実行 ───────────────────────────────────────────────────────────────


async def run_case(
    api: RunApi, case: Case, *, kb_id: str, model_id: str | None, judge: Judge | None = None
) -> CaseResult:
    run_id = await api.start(
        {"query": case.query, "kb_ids": [kb_id], "model_id": model_id, "include_archived": False}
    )
    steps: dict[str, dict[str, Any]] = {}
    end: tuple[str, dict[str, Any]] = ("run.failed", {"message": "ストリームが途中で終わりました"})
    async for event, data in api.stream(run_id):
        if event == "step":
            steps[data["step"]["id"]] = data["step"]
        elif event in TERMINAL:
            end = (event, data)
            break
    event, data = end
    traj = trajectory(list(steps.values()))
    facts = [f.any for f in case.key_facts]
    if event != "run.completed":
        return CaseResult(
            id=case.id, query=case.query, tags=case.tags,
            status="failed" if event == "run.failed" else "cancelled",
            answer="", cited_documents=[], relevant_documents=case.relevant_documents,
            citation_recall=0.0 if case.relevant_documents else 1.0,
            citation_precision=0.0 if case.relevant_documents else 1.0,
            fact_coverage=fact_coverage("", facts), faithfulness=None, unsupported_claims=[],
            tokens=0, duration_ms=0, no_answer=True, no_answer_reason=None,
            error=data.get("message"), **traj,
        )  # fmt: skip
    answer = data["answer"]
    cited = cited_documents(data)
    norm = normalize_text(answer)
    faith: float | None = None
    unsupported: list[str] = []
    judge_error = None
    sources = cited_sources(data)
    if judge is not None and answer.strip():
        try:
            faith, unsupported = faithfulness_from_claims(await judge(case.query, answer, sources))
        except Exception as e:
            judge_error = f"{type(e).__name__}: {e}"[:300]
    return CaseResult(
        id=case.id,
        query=case.query,
        tags=case.tags,
        status="completed",
        answer=answer,
        cited_documents=cited,
        relevant_documents=case.relevant_documents,
        citation_recall=citation_recall(set(cited), case.relevant_documents),
        citation_precision=citation_precision(set(cited), case.relevant_documents),
        fact_coverage=fact_coverage(norm, facts),
        faithfulness=faith,
        unsupported_claims=unsupported,
        tokens=data["tokens_in"] + data["tokens_out"],
        duration_ms=data["duration_ms"],
        no_answer=data.get("no_answer_reason") is not None,
        no_answer_reason=data.get("no_answer_reason"),
        judge_error=judge_error,
        facts_matched=[any(normalize_text(a) in norm for a in f) for f in facts],
        **traj,
    )


class HttpRunApi:
    """対話 API（開発用ヘッダで認証）。"""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def start(self, body: dict[str, Any]) -> str:
        res = await self.client.post("/v1/runs", json=body)
        if res.status_code >= 400:
            raise RuntimeError(f"run を開始できません: {res.status_code} {res.text[:200]}")
        return str(res.json()["run_id"])

    async def stream(self, run_id: str) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        async with self.client.stream("GET", f"/v1/runs/{run_id}/stream", timeout=None) as res:
            res.raise_for_status()
            async for item in iter_sse(res.aiter_lines()):
                yield item


# ── 評価者（忠実度） ──────────────────────────────────────────────────


class Claim(BaseModel):
    text: str = Field(description="回答から取り出した 1 つの主張（短く）")
    verdict: Literal["supported", "unsupported", "not_a_claim"]
    reason: str | None = Field(default=None, description="unsupported のときの理由（短く）")


class Verdict(BaseModel):
    claims: list[Claim]


JUDGE_PROMPT = """あなたは RAG の回答を検査する評価者です。
回答に含まれる主張が、資料で裏付けられるかを判定します。

手順:
1. 回答を、事実を述べる最小単位の主張に分ける（数値・日付・条件・固有名詞を含む文は 1 つずつ）。
2. 各主張を判定する:
   - supported: 資料のどれかに同じ内容が書かれている（言い換え・要約・単位や表記の違いは可）
   - unsupported: 資料に無い、または資料と食い違う
   - not_a_claim: 事実ではない文
     （「見つかりませんでした」「確認してください」などの案内・前置き・まとめの言い回し）
3. 引用番号 [n] が付いていなくても、資料のどれかで裏付けられれば supported とする。

## 質問
{query}

## 回答
{answer}

## 資料
{sources}
"""


def make_judge(model: Any, *, body_chars: int = 1200) -> Judge:
    structured = model.with_structured_output(Verdict, method="function_calling")

    async def judge(query: str, answer: str, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        src = (
            "\n\n".join(
                f"[{s['n']}] {s['title']} / {s['heading']}\n{s['body'][:body_chars]}" for s in sources
            )
            or "（資料なし）"
        )
        out = await structured.ainvoke(JUDGE_PROMPT.format(query=query, answer=answer, sources=src))
        v = out if isinstance(out, Verdict) else Verdict.model_validate(out)
        return [c.model_dump() for c in v.claims]

    return judge


def result_json(
    suite: str, model_id: str | None, judge_id: str | None, rs: list[CaseResult]
) -> dict[str, Any]:
    return {
        "suite": suite,
        "model_id": model_id,
        "judge_id": judge_id,
        "summary": summarize(rs),
        "cases": [asdict(r) for r in rs],
    }
