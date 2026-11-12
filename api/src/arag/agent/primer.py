"""ターンの最初にシステムが行う整理と検索（specs/026 ①②）。

モデルが検索するかどうかに任せず、質問（と整理したクエリ）で必ず検索し、結果を RunContext に置く。
結果を質問に添えるのは AgentPolicyMiddleware（会話の状態は変えない）。
"""

import asyncio
import re
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.runtime import Runtime

from arag.agent.context import Emit, Primer, RunContext
from arag.agent.ops import op_search, weak_result
from arag.agent.steps import Step, StepClock
from arag.agent.understand import MAX_QUERIES, Understanding, understand

_BLOCK = re.compile(r'<資料 n="(\d+)".*?</資料>', re.DOTALL)
PRIMER_OPEN = "<検索結果>"
PRIMER_CLOSE = "</検索結果>"
PRIMER_HEAD = (
    "次は、システムがこの質問をもとに先に検索した結果です（[n] が出典番号）。"
    "足りるならこのまま答え、足りない点だけツールで調べてください。"
)


def merge_results(texts: list[str]) -> str:
    """複数の検索結果をつなぐ。前の結果に出た資料（同じ出典番号）は省く。"""
    seen: set[str] = set()
    parts: list[str] = []
    for text in texts:

        def keep(m: re.Match[str]) -> str:
            if m.group(1) in seen:
                return f"（資料 [{m.group(1)}] は上と同じ）"
            seen.add(m.group(1))
            return m.group(0)

        parts.append(_BLOCK.sub(keep, text))
    return "\n\n".join(parts)


def with_primer(question: str, primer: Primer | None) -> str:
    if primer is None or not primer.text:
        return question
    return f"{question}\n\n{PRIMER_OPEN}\n{PRIMER_HEAD}\n\n{primer.text}\n{PRIMER_CLOSE}"


async def _search(ctx: RunContext, emit: Emit, index: int, query: str) -> str:
    sid = f"primer-{index}"
    clock = StepClock(
        emit,
        Step(
            id=sid,
            name="search",
            label="検索",
            status="running",
            input={"query": query, "by": "system"},
            summary="検索中",
        ),
    )
    ctx.stats.primer_searches += 1
    try:
        text = await op_search(ctx, emit, sid, query)
    except Exception as e:
        ctx.stats.tool_errors += 1
        clock.done("失敗しました", {"error": str(e)[:300]}, error=True)
        return f"検索「{query}」は失敗しました（{type(e).__name__}）。"
    n = len(_BLOCK.findall(text))
    clock.done(f"資料 {n} 件" if n else "資料なし", {"result": text[:2000]})
    return text


def _describe(u: Understanding) -> str:
    if u.error:
        return f"整理できなかったため、質問文のまま検索する（{u.error}）"
    if u.kind == "chat":
        return "文書を調べる質問ではないと判断"
    head = "・".join(f"「{q}」" for q in u.queries)
    return f"{head} で検索" + ("（表の集計あり）" if u.table else "")


class PrimerMiddleware(AgentMiddleware[Any, RunContext]):
    async def abefore_agent(self, state: Any, runtime: Runtime[RunContext]) -> dict[str, Any] | None:
        ctx, emit = runtime.context, runtime.stream_writer
        msgs: list[AnyMessage] = list(state["messages"])
        last = next((i for i in range(len(msgs) - 1, -1, -1) if isinstance(msgs[i], HumanMessage)), None)
        if last is None:
            return None
        question = msgs[last].text.strip()
        history = msgs[:last]
        first_turn = not any(isinstance(m, HumanMessage) for m in history)
        clock = StepClock(
            emit,
            Step(
                id="understand",
                name="understand",
                label="質問の理解",
                status="running",
                input={"question": question[:2000], "history": not first_turn},
                summary="質問を整理しています",
            ),
        )

        def finish(u: Understanding) -> None:
            clock.done(
                _describe(u),
                {"kind": u.kind, "queries": list(u.queries), "table": u.table, "raw": u.raw[:1000]}
                | ({"error": u.error} if u.error else {}),
            )

        texts: list[str] = []
        if first_turn:
            # 質問文での検索は整理を待たずに始める（待ち時間を増やさない）
            u, text = await asyncio.gather(
                understand(ctx.utility_model, history, question), _search(ctx, emit, 1, question)
            )
            finish(u)
            texts.append(text)
            extra = [q for q in u.queries if q != question][: MAX_QUERIES - 1]
            start = 2
        else:
            # 追質問は指示語を含むので、整理したクエリで検索する
            u = await understand(ctx.utility_model, history, question)
            finish(u)
            extra = list(u.queries)
            start = 1
        if u.kind == "chat":
            ctx.primer = Primer(kind="chat")
            return None
        if extra:
            texts += await asyncio.gather(*(_search(ctx, emit, start + i, q) for i, q in enumerate(extra)))
        ctx.primer = Primer(
            kind=u.kind,
            table=u.table,
            queries=u.queries,
            text=merge_results(texts),
            weak=bool(texts) and all(weak_result(t) for t in texts),
        )
        return None
