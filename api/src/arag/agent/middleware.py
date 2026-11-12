"""エージェントの middleware（specs/005-agent design §3）。"""

import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse, ToolCallRequest
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
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
        prompt = system_prompt(ctx)
        overrides: dict[str, Any] = {"messages": compact}
        if calls >= ctx.cfg.max_steps:
            prompt += FINAL_NOTE
            overrides["tools"] = []
        elif calls == 1 and ctx.cfg.require_citations and request.tools:
            # 小さいモデルは追質問で前の回答だけを頼りに引用なしで答えがちなので、最初は必ずツールを使わせる
            overrides["tool_choice"] = "any"
        response = await handler(request.override(system_message=SystemMessage(prompt), **overrides))
        if not _needs_gap_review(ctx, msgs[start:], response, calls, bool(request.tools)):
            return response
        # 複数の資料を照合する質問で、小さいモデルは 1 回の検索だけで「資料に無い」と答えがち。
        # 下書きを添えて 1 度だけ差し戻す（下書きと依頼は状態に残さず、この呼び出しの中だけで使う）
        ctx.stats.gap_reviews += 1
        draft = cast(AIMessage, response.result[-1])
        retry: list[AnyMessage] = [*compact, draft, HumanMessage(GAP_NOTE)]
        return await handler(request.override(system_message=SystemMessage(prompt), messages=retry))


def _needs_gap_review(
    ctx: RunContext, turn: list[AnyMessage], response: ModelResponse[Any], calls: int, has_tools: bool
) -> bool:
    """下書きを差し戻すか。最終回答で、調べ残しを認めていて、検索が少なく、回数にまだ余裕があるとき。"""
    if not has_tools or ctx.stats.gap_reviews or calls + 2 > ctx.cfg.max_steps:
        return False
    last = response.result[-1] if response.result else None
    if not isinstance(last, AIMessage) or last.tool_calls:
        return False
    searches = sum(1 for m in turn if isinstance(m, ToolMessage) and m.name in SEARCH_TOOLS)
    if searches == 0 or searches > GAP_REVIEW_MAX_SEARCHES:
        return False
    _, answer = split_thinking(last.text)
    return bool(GAP.search(answer))


_MATERIAL = re.compile(r"<資料 n=")


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
        _, answer = split_thinking(text)  # 考えた過程は「考えた過程」のステップで見せる
        fixed = drop_repeated_tail(
            strip_unknown(normalize_markers(answer), set(runtime.context.registry.numbers()))
        )
        if fixed == text:
            return None
        return {"messages": [AIMessage(content=fixed, id=last.id, usage_metadata=last.usage_metadata)]}
