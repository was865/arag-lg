"""エージェントの middleware（specs/005-agent design §3）。"""

import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    SummarizationMiddleware,
    ToolCallRequest,
)
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.runtime import Runtime
from langgraph.types import Command

from arag.agent.answer_text import drop_repeated_tail
from arag.agent.citations import normalize_markers, strip_unknown
from arag.agent.context import RunContext
from arag.agent.ops import KEYWORD_FALLBACK_NOTE, KEYWORD_RELAX_NOTE
from arag.agent.steps import Step, StepClock
from arag.agent.thinking import split_thinking
from arag.agent.tools import LABELS
from arag.prompts import load_prompt

TZ = ZoneInfo("Asia/Tokyo")
FINAL_NOTE = (
    "\n\n## 最終回答\n検索の回数が上限に達しました。これ以上ツールは使えません。"
    "ここまでに得た資料だけで回答をまとめてください。足りない点は足りないと書いてください。"
)
PRIOR_TOOL_PLACEHOLDER = "（前のターンの資料。出典番号はこのターンでは使えないので、必要なら検索し直す）"
# 下書きが「資料に無い」「確認が必要」などと調べ残しを認めているか（日本語・英語）
GAP = re.compile(
    r"記載(されていない|されていません|がない|がありません|はありません)|見つかりません|見つからな|不明|"
    r"分かりません|わかりません|確認(する|が)必要|情報(が)?不足|計算(することは|は)?でき(ません|ない)|"
    r"not (mentioned|found|available|specified)|no information|could not find|unknown",
    re.IGNORECASE,
)
GAP_NOTE = (
    "この下書きには、資料で確かめられていない点があります。回答する前に、まだ調べていない資料"
    "（台帳・一覧・記録・議事録・規程など、その点が書かれていそうな種類）を、"
    "その点に絞った語で search してください。"
    "数の計算が要るなら、値をそろえてから calculate で計算してください。"
    "調べても見つからない点だけを、見つからないと書いてください。"
)
GAP_REVIEW_MAX_SEARCHES = 2  # この回数を超えて検索していれば、調べ尽くしたとみなす
SEARCH_TOOLS = {"search", "keyword_search"}
# 資料の本文を返すツール（一覧・目次は含めない）
READ_TOOLS = SEARCH_TOOLS | {"read_section"}
# 資料を読むまでツールを必須にする上限（検索してもなお 0 件なら「見つからない」と答えてよい）
FORCE_READ_MAX_ATTEMPTS = 3


def system_prompt(ctx: RunContext, now: datetime | None = None) -> str:
    cfg = ctx.cfg
    citation = (
        # 「[n]」と書くと小さいモデルがそのまま [n] と写すので、実際の数字の例で示す
        '重要な事実には、根拠にした資料の番号を文の末尾に必ず付ける（<資料 n="3"> を根拠にしたら [3]）。'
        if cfg.require_citations
        else 'できれば、根拠にした資料の番号を付ける（<資料 n="3"> を根拠にしたら [3]）。'
    )
    unknown = (
        "資料で答えられないときは、分からないと正直に答え、何が見つからなかったか・どう調べればよいかを書く。"
        if cfg.admit_unknown
        else "資料で答えきれない部分は、一般的な知識で補ってよいが、資料に基づかない部分だと明記する。"
    )
    today = (now or datetime.now(TZ)).strftime("%Y年%m月%d日（%a）")
    return load_prompt("agent_system").format(today=today, citation_rule=citation, unknown_rule=unknown)


def record_system(emit: Any, step_id: str, kind: str, label: str, summary: str, **detail: Any) -> None:
    """後ろで行った処理を「システムの処理」のステップとして記録に残す（後端の動きは原則すべて記録に出す）。

    detail の input は入力に、output は出力にそのまま入れる。画面では 1 つの畳んだ組にまとめて見せる。
    """
    step = Step(
        id=step_id,
        name="system",
        label=label,
        status="done",
        input={"kind": kind, **detail.get("input", {})},
        output=detail.get("output"),
        summary=summary,
    )
    emit({"type": "step", "step": step.model_dump()})


def _turn_start(messages: list[AnyMessage]) -> int:
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return i
    return 0


class AgentPolicyMiddleware(AgentMiddleware[Any, RunContext]):
    """システムプロンプト・前のターンの資料の圧縮・回数上限での最終回答（R20）。"""

    async def awrap_model_call(
        self,
        request: ModelRequest[RunContext],
        handler: Callable[[ModelRequest[RunContext]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        ctx = request.runtime.context
        msgs = list(request.messages)
        start = _turn_start(msgs)
        # 前のターンのツール結果は文脈を圧迫するので置き換える（checkpoint の状態は変えない）
        compact: list[AnyMessage] = [
            m.model_copy(update={"content": PRIOR_TOOL_PLACEHOLDER})
            if i < start and isinstance(m, ToolMessage)
            else m
            for i, m in enumerate(msgs)
        ]
        calls = sum(1 for m in msgs[start:] if isinstance(m, AIMessage)) + 1
        ctx.stats.model_calls = calls
        emit = request.runtime.stream_writer
        replaced = sum(1 for m in msgs[:start] if isinstance(m, ToolMessage))
        if replaced and calls == 1:  # 呼び出しのたびに置き換えるが、記録はターンに 1 回
            record_system(
                emit,
                "system-compact",
                "compact_history",
                "前のターンの資料を省略",
                f"前のターンのツール結果 {replaced} 件を、モデルには省略の案内に置き換えて渡した",
                input={"replaced": replaced},
                output={"placeholder": PRIOR_TOOL_PLACEHOLDER},
            )
        prompt = system_prompt(ctx)
        overrides: dict[str, Any] = {"messages": compact}
        if calls >= ctx.cfg.max_steps:
            prompt += FINAL_NOTE
            overrides["tools"] = []
            record_system(
                emit,
                f"system-budget-{calls}",
                "step_budget",
                "呼び出しの上限",
                f"{calls} 回目で上限（{ctx.cfg.max_steps} 回）に達したため、ツールを外して最終回答を求めた",
                input={"calls": calls, "max_steps": ctx.cfg.max_steps},
                output={"note": FINAL_NOTE.strip()},
            )
        elif calls == 1 and ctx.cfg.require_citations and request.tools:
            # RAG の最初の一歩は検索。小さいモデルは文書一覧だけ見て「こう調べてください」と答えたり、
            # 追質問で前の回答だけを頼りに答えたりするので、最初は検索のツールだけを渡して必ず使わせる
            first = [t for t in request.tools if _tool_name(t) in SEARCH_TOOLS] or list(request.tools)
            overrides["tool_choice"] = "any"
            overrides["tools"] = first
            names = [_tool_name(t) for t in first]
            record_system(
                emit,
                "system-force-tool",
                "force_tool",
                "最初は検索を必須に",
                f"ターンの最初の呼び出しで、検索（{'・'.join(names)}）を必ず使わせた",
                input={"tool_choice": "any", "tools": names},
            )
        elif ctx.cfg.require_citations and request.tools and _must_read(msgs[start:]):
            # 検索が 0 件だった・一覧や目次しか見ていないなど、資料の本文をまだ読んでいないうちは答えさせない
            overrides["tool_choice"] = "any"
            record_system(
                emit,
                f"system-force-tool-{calls}",
                "force_tool",
                "資料を読むまでツールを必須に",
                f"{calls} 回目の呼び出し: まだ資料の本文を読んでいないので、ツールを必ず使わせた",
                input={"tool_choice": "any", "calls": calls},
            )
        response = await handler(request.override(system_message=SystemMessage(prompt), **overrides))
        gap = _gap_review(ctx, msgs[start:], response, calls, bool(request.tools))
        if gap is None:
            return response
        # 複数の資料を照合する質問で、小さいモデルは 1 回の検索だけで「資料に無い」と答えがち。
        # 下書きを添えて 1 度だけ差し戻す。下書きと依頼は会話の状態には入れないが、
        # 差し戻したこと（下書き・きっかけの語・依頼・その結果）は「見直し」のステップとして記録に残す
        trigger, searches, answer = gap
        ctx.stats.gap_reviews += 1
        clock = StepClock(
            request.runtime.stream_writer,
            Step(
                id=f"review-{ctx.stats.gap_reviews}",
                name="review",
                label="調べ残しの見直し",
                status="running",
                input={"draft": answer, "trigger": trigger, "searches": searches},
                summary="下書きを差し戻して書き直し中",
            ),
        )
        draft = cast(AIMessage, response.result[-1])
        retry: list[AnyMessage] = [*compact, draft, HumanMessage(GAP_NOTE)]
        try:
            redo = await handler(request.override(system_message=SystemMessage(prompt), messages=retry))
        except Exception as e:
            clock.done("差し戻しに失敗しました", {"note": GAP_NOTE, "error": str(e)[:300]}, error=True)
            raise
        last = redo.result[-1] if redo.result else None
        tools = [c["name"] for c in last.tool_calls] if isinstance(last, AIMessage) else []
        clock.done(
            f"「{trigger}」のため差し戻し → " + (f"{'・'.join(tools)} を実行" if tools else "回答を書き直し"),
            {"note": GAP_NOTE, "next_tools": tools},
        )
        return redo


def _tool_name(tool: Any) -> str:
    return str(tool.get("name", "")) if isinstance(tool, dict) else str(getattr(tool, "name", ""))


def _must_read(turn: list[AnyMessage]) -> bool:
    """資料の本文（検索の結果・章）をまだ 1 件も受け取っておらず、探す余地も残っているか。"""
    reads = [m for m in turn if isinstance(m, ToolMessage) and m.name in READ_TOOLS]
    got = any(m.status != "error" and "<資料" in m.text for m in reads)
    return not got and len(reads) < FORCE_READ_MAX_ATTEMPTS


def _gap_review(
    ctx: RunContext, turn: list[AnyMessage], response: ModelResponse[Any], calls: int, has_tools: bool
) -> tuple[str, int, str] | None:
    """下書きを差し戻すなら（きっかけの語, 検索の回数, 下書き）を返す。

    最終回答で、調べ残しを認めていて、検索が少なく、回数にまだ余裕があるとき。
    """
    if not has_tools or ctx.stats.gap_reviews or calls + 2 > ctx.cfg.max_steps:
        return None
    last = response.result[-1] if response.result else None
    if not isinstance(last, AIMessage) or last.tool_calls:
        return None
    searches = sum(1 for m in turn if isinstance(m, ToolMessage) and m.name in SEARCH_TOOLS)
    if searches == 0 or searches > GAP_REVIEW_MAX_SEARCHES:
        return None
    _, answer = split_thinking(last.text)
    m = GAP.search(answer)
    return (m.group(0), searches, answer) if m else None


_MATERIAL = re.compile(r"<資料 n=")
_MARK = re.compile(r"\[(\d+)\](?!\()")


class StepMiddleware(AgentMiddleware[Any, RunContext]):
    """ツールの開始・終了を step イベントにし、失敗をモデルへの結果に変える（R10・R23）。"""

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        call = request.tool_call
        cid, name = call["id"] or "", call["name"]
        ctx = cast(RunContext, request.runtime.context)
        emit = request.runtime.stream_writer
        label, running = LABELS.get(name, (name, "実行しています"))
        clock = StepClock(
            emit,
            Step(id=cid, name=name, label=label, status="running", input=dict(call["args"]), summary=running),
        )
        ctx.stats.tool_calls += 1
        try:
            result = await handler(request)
        except Exception as e:
            ctx.stats.tool_errors += 1
            clock.done("失敗しました", {"error": str(e)[:300]}, error=True)
            return ToolMessage(
                content=f"ツールの実行に失敗しました（{type(e).__name__}）。別の方法を試してください。",
                tool_call_id=cid,
                name=name,
                status="error",
            )
        text = result.text if isinstance(result, ToolMessage) else ""
        n = len(_MATERIAL.findall(text))
        summary = f"資料 {n} 件" if n else (text[:120] if name == "calculate" else "完了")
        if n and text.startswith(KEYWORD_FALLBACK_NOTE):
            summary = f"完全一致 0 件 → セマンティック検索で資料 {n} 件"
        elif n and text.startswith(KEYWORD_RELAX_NOTE):
            summary = f"完全一致 0 件 → 型番のみで資料 {n} 件"
        clock.done(summary, {"result": text[:2000]})
        return result


class CitationMiddleware(AgentMiddleware[Any, RunContext]):
    """回答の引用記号を正規化し、登録されていない番号を除く（R18）。考えた過程と末尾の言い直しも落とす。"""

    async def aafter_agent(self, state: Any, runtime: Runtime[RunContext]) -> dict[str, Any] | None:
        msgs = state["messages"]
        if not msgs or not isinstance(msgs[-1], AIMessage) or msgs[-1].tool_calls:
            return None
        last: AIMessage = msgs[-1]
        text = last.text
        thought, answer = split_thinking(text)  # 考えた過程は「考えた過程」のステップで見せる
        known = set(runtime.context.registry.numbers())
        normalized = normalize_markers(answer)
        stripped = strip_unknown(normalized, known)
        fixed = drop_repeated_tail(stripped)
        if fixed == text:
            return None
        removed = sorted({int(n) for n in _MARK.findall(normalized)} - known)
        notes = []
        if thought:
            notes.append(f"考えた過程 {len(thought)} 文字を回答から分けた")
        if normalized != answer:
            notes.append("引用の書き方をそろえた")
        if removed:
            notes.append("資料に無い番号 " + "".join(f"[{n}]" for n in removed) + " を消した")
        if len(stripped) > len(fixed):
            notes.append(f"末尾の言い直し {len(stripped) - len(fixed)} 文字を消した")
        record_system(
            runtime.stream_writer,
            "system-citation-cleanup",
            "citation_cleanup",
            "回答の整形",
            "・".join(notes) or "回答を整えた",
            input={"before": text[:4000]},
            output={
                "after": fixed[:4000],
                "removed_numbers": removed,
                "tail_dropped_chars": len(stripped) - len(fixed),
                "thinking_chars": len(thought or ""),
            },
        )
        return {"messages": [AIMessage(content=fixed, id=last.id, usage_metadata=last.usage_metadata)]}


class RecordedSummarization(SummarizationMiddleware):
    """会話が長くなったときの要約。要約したこと（何件を置き換え、どんな要約にしたか）を記録に残す。"""

    async def abefore_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        before = list(state["messages"])
        result = await super().abefore_model(state, runtime)
        if not result:
            return None
        ids = {m.id for m in before}
        after = [m for m in result["messages"] if getattr(m, "id", None) != REMOVE_ALL_MESSAGES]
        kept = sum(1 for m in after if m.id in ids)
        summary = "\n".join(m.text for m in after if m.id not in ids)
        record_system(
            runtime.stream_writer,
            f"system-summarize-{len(before)}",
            "summarize_history",
            "会話の要約",
            f"会話が長くなったため、前の {len(before) - kept} 件のメッセージを要約に置き換えた"
            f"（{kept} 件はそのまま）",
            input={"messages_before": len(before), "kept": kept},
            output={"summary": summary[:4000]},
        )
        return result
