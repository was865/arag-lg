"""回答評価（specs/005-agent R33・E1）。旧版 tools/answer-eval を移植し、API 経由で実際の run を解かせる。

題ごとに POST /v1/runs → SSE を最後まで読み、run.completed から指標を出す。runner・検索・モデルは
本番と同じ経路を通るので、評価の数字がそのまま画面の振る舞いになる。

指標:
- 回答の中身（LLM 不要）: 引用再現率・引用精度（文書名で比較）・事実網羅（key_facts の部分一致）
- 忠実度（評価者 LLM）: 回答の事実主張のうち、引用した資料で裏付けられる割合
- 軌跡・コスト: モデルが呼んだツール数・実際に走った検索の回数・書き直し回数・トークン・所要時間・回答不能
"""

import asyncio
import json
import re
import statistics
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Protocol, TypedDict

import httpx
from pydantic import BaseModel, Field

from arag.eval.dataset import Case
from arag.eval.metrics import normalize_text

TERMINAL = {"run.completed", "run.failed", "run.cancelled"}
SEARCH_TOOLS = {"search", "keyword_search"}
NON_TOOL_STEPS = {"system", "reasoning", "review", "switch_model", "understand", "read_image"}

Judge = Callable[[str, str, list[dict[str, Any]]], Awaitable[list[dict[str, Any]]]]


class RunApi(Protocol):
    async def start(self, body: dict[str, Any], thread_id: str | None = None) -> tuple[str, str]:
        """run を始めて (run_id, thread_id) を返す。thread_id を渡すとそのスレッドの続きとして尋ねる。"""
        ...

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
    # 誤りの値（wrong_facts）を見た題か、と答えに出た誤りの値
    wrong_checked: bool = False
    wrong_facts_found: list[str] = field(default_factory=list)
    # 評価者の判定（主張ごと）と、評価者に見せた資料。人手ラベルとの一致確認（E2）に使う
    claims: list[dict[str, Any]] = field(default_factory=list)
    judge_sources: list[dict[str, Any]] = field(default_factory=list)
    # 聞き返しで終えたか（モデルの ask_user かシステムの聞き返し）と、題の期待（specs/031 T12）
    clarified: bool = False
    expect_clarify: bool | None = None


# ── 純関数 ──────────────────────────────────────────────────────────────


def _cited_refs(completed: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """回答に実際に書かれた番号の引用（API は引用した箇所だけを返すが、古い記録にも備えて番号で絞る）。"""
    used = {m for m in re.findall(r"\[(\d+)\]", completed.get("answer", ""))}
    cmap = completed.get("citation_map", {})
    return sorted(((n, r) for n, r in cmap.items() if n in used), key=lambda kv: int(kv[0]))


def cited_documents(completed: dict[str, Any]) -> list[str]:
    """引用した文書の名前（出現順・重複なし）。"""
    titles = {s["id"]: s["title"] for s in completed.get("sources", [])}
    out: list[str] = []
    for _, ref in _cited_refs(completed):
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
    for n, ref in _cited_refs(completed):
        if (sec := secs.get(ref["section_id"])) is not None:
            out.append({"n": int(n)} | sec)
    return out


def citation_recall(cited: set[str], relevant: list[str]) -> float:
    rel = set(relevant)
    return 1.0 if not rel else len(cited & rel) / len(rel)


def citation_precision(cited: set[str], relevant: list[str], acceptable: list[str] | None = None) -> float:
    """引用した文書のうち、根拠の文書か、同じ事実を載せた別の文書（acceptable）の割合。"""
    if not cited:
        # 根拠の無い題で何も引用しないのは正しい振る舞い
        return 1.0 if not relevant else 0.0
    return len(cited & (set(relevant) | set(acceptable or []))) / len(cited)


class Trajectory(TypedDict):
    tool_calls: int
    search_calls: int
    retrieve_attempts: int
    rewrites: int


def trajectory(steps: list[dict[str, Any]]) -> Trajectory:
    # モデルが呼んだツールだけを数える（システムの処理・考えた過程・見直し・モデルの切り替えは除く）
    top = [s for s in steps if not s.get("parent_id") and s["name"] not in NON_TOOL_STEPS]
    return {
        "tool_calls": len(top),
        "search_calls": sum(1 for s in top if s["name"] in SEARCH_TOOLS),
        "retrieve_attempts": sum(1 for s in steps if s.get("parent_id") and s["name"] == "retrieve"),
        "rewrites": sum(1 for s in steps if s["name"] == "rewrite_query"),
    }


def clarified(steps: list[dict[str, Any]]) -> bool:
    """聞き返しで終えたターンか（モデルの ask_user か、システムの聞き返し。specs/031）。"""
    return any(
        s["name"] == "ask_user" or (s["name"] == "system" and (s.get("input") or {}).get("kind") == "clarify")
        for s in steps
    )


_DATE = re.compile(r"(\d{4})\s*(?:年|/|-|\.)\s*(\d{1,2})\s*(?:月|/|-|\.)\s*(\d{1,2})\s*日?")


def canon(s: str) -> str:
    """事実照合用の正規化。normalize_text に加え、Markdown の太字記号（**・__）を外し、
    日付（2026年6月5日・2026/6/5）を 2026-06-05 にそろえる。"""
    s = s.replace("**", "").replace("__", "")
    return _DATE.sub(lambda m: f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}", normalize_text(s))


def facts_matched(answer: str, facts: list[list[str]]) -> list[bool]:
    a = canon(answer)
    return [any(canon(x) in a for x in f) for f in facts]


def wrong_facts_found(answer: str, facts: list[list[str]]) -> list[str]:
    """答えに出た誤りの値（各項目の最初に当たった表記）。"""
    a = canon(answer)
    return [next(x for x in f if canon(x) in a) for f in facts if any(canon(x) in a for x in f)]


# 「資料に無い」と答えたことを示す言い回し（日英）。canon 後の小文字で照合する
_DECLINE = re.compile(
    r"(記載|明記|言及|明示|記述)(が|は)?(され)?(てい)?(ありません|ない|ません|無い|なし)"
    r"|示されていな|示されていません|見つかりませんでした|見当たりません|資料に(は)?(ありません|ない|無い)"
    # 「データが含まれていません」「データは資料内に含まれていません」「資料からは確認できません」
    # 「お答えすることができません」（Gemma 4）。
    # 「送料は含まれていません」のような補足に当たらないよう、情報を指す語や資料に続くときだけ見る
    r"|(情報|データ|数値|記述|記載|値)(は|が|も)?(一切)?((資料|文書|検索結果)(内|の中)?に(は)?)?含まれてい(な|ません)"
    r"|(資料|検索結果|文書)(の中)?(から|で|に)(は)?確認でき(な|ません)"
    r"|お答え(する)?(こと)?(が|は)?できません"
    r"|not (explicitly |directly )?(mention|state|specif|provide|include|contain|found|cover)"
    r"|(does|do|is|are) not (mention|state|specify|provide|include|contain)"
    r"|no (information|mention|details?) (about|on|regarding)"
    # 「I could not find …」（Gemma 4 の hm60、026d）
    r"|(could not|couldn't|was unable to|am unable to|cannot|can't) (find|locate)"
)


def declines(answer: str) -> bool:
    """回答が「資料に記載が無い」と述べているか。"""
    return bool(_DECLINE.search(canon(answer)))


def score_citation_precision(case: Case, cited: set[str], *, declined: bool, wrong_found: list[str]) -> float:
    """引用精度。答えの無い題（expect_no_answer かつ relevant_documents が空）で、資料に無いと述べ
    （回答不能を含む）、誤りの値も書いていなければ、近い資料を引用していても 1.0 とする（2026-11-13）。
    値を言い切った答えと、答えのある題は今までどおり引用の当たりで測る（acceptable_documents も当たり）。"""
    if case.expect_no_answer and not case.relevant_documents and declined and not wrong_found:
        return 1.0
    return citation_precision(cited, case.relevant_documents, case.acceptable_documents)


def _coverage(matched: list[bool]) -> float:
    return 1.0 if not matched else sum(matched) / len(matched)


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
        "wrong_fact_rate": _mean([float(bool(r.wrong_facts_found)) for r in rs if r.wrong_checked]),
        # 聞き返し（specs/031 T12）: 全体の率と、聞き返すべき題で聞き返した率・必要の無い題で聞き返した率
        "clarify_rate": _mean([float(r.clarified) for r in rs]),
        "clarify_recall": _mean([float(r.clarified) for r in rs if r.expect_clarify is True]),
        "over_clarify_rate": _mean([float(r.clarified) for r in rs if r.expect_clarify is False]),
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
    ("誤りの記述", "wrong_fact_rate"),
    ("聞き返し率", "clarify_rate"),
    ("聞き返すべき題で聞き返した", "clarify_recall"),
    ("聞き返す必要の無い題で聞き返した", "over_clarify_rate"),
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
        if c.get("clarified"):
            state += "/聞き返し"
        lines.append(
            f"| {c['id']} | {state} | {_fmt(c['citation_recall'])} | {_fmt(c['citation_precision'])} | "
            f"{_fmt(c['fact_coverage'])} | {_fmt(c['faithfulness'])} | "
            f"{c['tool_calls']} | {c['duration_ms']} | "
            f"{', '.join(c['cited_documents'])} | {excerpt} |"
        )
    wrong = [(c["id"], w) for c in result["cases"] for w in c.get("wrong_facts_found", [])]
    if wrong:
        lines += ["", "## 誤りの記述", ""] + [f"- {i}: {w}" for i, w in wrong]
    unsupported = [(c["id"], u) for c in result["cases"] for u in c.get("unsupported_claims", [])]
    if unsupported:
        lines += ["", "## 裏付けの無い主張", ""] + [f"- {i}: {u}" for i, u in unsupported]
    return "\n".join(lines) + "\n"


# ── 実行 ───────────────────────────────────────────────────────────────


async def run_case(
    api: RunApi, case: Case, *, kb_id: str, model_id: str | None, judge: Judge | None = None
) -> CaseResult:
    def body(query: str) -> dict[str, Any]:
        return {"query": query, "kb_ids": [kb_id], "model_id": model_id, "include_archived": False}

    async def ask(query: str, thread_id: str | None) -> tuple[str, dict[str, Any], dict[str, Any], str]:
        run_id, tid = await api.start(body(query), thread_id)
        steps: dict[str, dict[str, Any]] = {}
        end: tuple[str, dict[str, Any]] = ("run.failed", {"message": "ストリームが途中で終わりました"})
        async for ev, d in api.stream(run_id):
            if ev == "step":
                steps[d["step"]["id"]] = d["step"]
            elif ev in TERMINAL:
                end = (ev, d)
                break
        return end[0], end[1], steps, tid

    # 続けて尋ねる題: 前の質問を同じスレッドで順に尋ねてから最後の質問を採点する
    thread_id: str | None = None
    event: str
    data: dict[str, Any]
    steps: dict[str, dict[str, Any]]
    for i, turn in enumerate(case.turns, start=1):
        ev, d, _, thread_id = await ask(turn, thread_id)
        if ev != "run.completed":
            event, data, steps = ev, {"message": f"前の質問 {i} が終わりませんでした: {d.get('message')}"}, {}
            break
    else:
        event, data, steps, _ = await ask(case.query, thread_id)
    traj = trajectory(list(steps.values()))
    asked = clarified(list(steps.values()))
    facts = [f.any for f in case.key_facts]
    if event != "run.completed":
        return CaseResult(
            id=case.id, query=case.query, tags=case.tags,
            status="failed" if event == "run.failed" else "cancelled",
            answer="", cited_documents=[], relevant_documents=case.relevant_documents,
            citation_recall=0.0 if case.relevant_documents else 1.0,
            citation_precision=0.0 if case.relevant_documents else 1.0,
            fact_coverage=_coverage(facts_matched("", facts)), faithfulness=None, unsupported_claims=[],
            tokens=0, duration_ms=0, no_answer=True, no_answer_reason=None,
            error=data.get("message"), expect_clarify=case.expect_clarify, **traj,
        )  # fmt: skip
    answer = data["answer"]
    cited = cited_documents(data)
    matched = facts_matched(answer, facts)
    no_answer = data.get("no_answer_reason") is not None
    declined = no_answer or declines(answer)
    if case.expect_no_answer:
        # 答えの無い題は、資料に無いと答えたか（回答不能を含む）だけを見る
        matched = [declined]
    if case.expect_clarify:
        # 聞き返すべき題は、聞き返したかだけを見る（specs/031 T12）
        matched = [asked]
    wrong_found = wrong_facts_found(answer, [f.any for f in case.wrong_facts])
    faith: float | None = None
    unsupported: list[str] = []
    claims: list[dict[str, Any]] = []
    judge_error = None
    sources = cited_sources(data)
    if judge is not None and answer.strip():
        try:
            claims = await judge(case.query, answer, sources)
            faith, unsupported = faithfulness_from_claims(claims)
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
        citation_precision=score_citation_precision(
            case, set(cited), declined=declined, wrong_found=wrong_found
        ),
        fact_coverage=_coverage(matched),
        faithfulness=faith,
        unsupported_claims=unsupported,
        tokens=data["tokens_in"] + data["tokens_out"],
        duration_ms=data["duration_ms"],
        no_answer=no_answer,
        no_answer_reason=data.get("no_answer_reason"),
        judge_error=judge_error,
        facts_matched=matched,
        wrong_checked=bool(case.wrong_facts),
        wrong_facts_found=wrong_found,
        claims=claims,
        judge_sources=sources if judge is not None else [],
        clarified=asked,
        expect_clarify=case.expect_clarify,
        **traj,
    )


class HttpRunApi:
    """対話 API（開発用ヘッダで認証）。"""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def start(self, body: dict[str, Any], thread_id: str | None = None) -> tuple[str, str]:
        url = f"/v1/threads/{thread_id}/runs" if thread_id else "/v1/runs"
        for _ in range(20):
            res = await self.client.post(url, json=body)
            if res.status_code != 429:
                break
            # 回数制限（ARAG_RATE_LIMIT_RUNS_PER_MIN）にかかったら待って出し直す
            await asyncio.sleep(float(res.headers.get("retry-after") or 10))
        if res.status_code >= 400:
            raise RuntimeError(f"run を開始できません: {res.status_code} {res.text[:200]}")
        out = res.json()
        return str(out["run_id"]), str(out["thread_id"])

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
