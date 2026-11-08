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

from arag.agent.citations import normalize_markers, strip_unknown
from arag.agent.context import RunContext
from arag.agent.steps import Step, StepClock
from arag.agent.tools import LABELS
from arag.prompts import load_prompt

TZ = ZoneInfo("Asia/Tokyo")
FINAL_NOTE = (
    "\n\n## 最終回答\n検索の回数が上限に達しました。これ以上ツールは使えません。"
    "ここまでに得た資料だけで回答をまとめてください。足りない点は足りないと書いてください。"
)
PRIOR_TOOL_PLACEHOLDER = "（前のターンの資料。出典番号はこのターンでは使えないので、必要なら検索し直す）"


def system_prompt(ctx: RunContext, now: datetime | None = None) -> str:
    cfg = ctx.cfg
    citation = (
        "重要な事実には、根拠の資料の出典番号 [n] を文の末尾に必ず付ける。"
        if cfg.require_citations
        else "できれば、根拠の資料の出典番号 [n] を付ける。"
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
        return await handler(request.override(system_message=SystemMessage(prompt), **overrides))


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
        clock.done(f"資料 {n} 件" if n else "完了", {"result": text[:2000]})
        return result


class CitationMiddleware(AgentMiddleware[Any, RunContext]):
    """回答の引用記号を正規化し、登録されていない番号を除く（R18）。"""

    async def aafter_agent(self, state: Any, runtime: Runtime[RunContext]) -> dict[str, Any] | None:
        msgs = state["messages"]
        if not msgs or not isinstance(msgs[-1], AIMessage) or msgs[-1].tool_calls:
            return None
        last: AIMessage = msgs[-1]
        text = last.text
        fixed = strip_unknown(normalize_markers(text), set(runtime.context.registry.numbers()))
        if fixed == text:
            return None
        return {"messages": [AIMessage(content=fixed, id=last.id, usage_metadata=last.usage_metadata)]}
