"""調査（create_agent の部分グラフ）の middleware と、回答の流れの節点が使う判断・記録（specs/005・029）。"""

import json
import re
import time
from collections.abc import Awaitable, Callable, Collection
from datetime import datetime
from typing import Any, NotRequired, cast
from zoneinfo import ZoneInfo

from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    ExtendedModelResponse,
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
from arag.agent.mcp_tools import record_removed
from arag.agent.numbers import numbers_in
from arag.agent.primer import with_primer
from arag.agent.prior import cited_documents
from arag.agent.prune import prune_citations
from arag.agent.reason_check import ReasonCheck, asks_reason, check_reason
from arag.agent.review_rules import (
    KEEP_CITATIONS,
    REASON,
    REASON_LABEL,
    REVIEW_LABELS,
    Draft,
    Review,
    ToolResult,
    pick,
)
from arag.agent.steps import Step, StepClock, elapsed_ms, record_system
from arag.agent.thinking import split_thinking
from arag.agent.tool_output import ToolOutput
from arag.agent.tools import ASK_USER, LABELS
from arag.mcp.registry import is_mcp_tool
from arag.prompts import load_prompt

TZ = ZoneInfo("Asia/Tokyo")
FINAL_NOTE = (
    "\n\n## 最終回答\n検索の回数が上限に達しました。これ以上ツールは使えません。"
    "ここまでに得た資料だけで回答をまとめてください。足りない点は足りないと書いてください。"
)
PRIOR_TOOL_PLACEHOLDER = "（前のターンの資料。本文は省略）"
# 置き換えた最初の 1 件にだけ添える説明（全部に付けると同じ文が何度も並ぶ）
PRIOR_NOTE = "出典番号はこのターンでは使えないので、必要なら文書名を手がかりに検索し直す"
PRIOR_DOCS_MAX = 8


def prior_placeholder(names: list[str] | None = None) -> str:
    """前のターンのツール結果の代わりに渡す文。本文は省くが、どの文書を調べたかは最初の 1 件に残す。

    names を渡した 1 件にだけ、文書名と説明が付く（全部に付けると同じ文書名や説明が何度も並ぶ）。
    """
    if names is None:
        return PRIOR_TOOL_PLACEHOLDER
    if not names:
        return f"（前のターンの資料。本文は省略。{PRIOR_NOTE}）"
    docs = "・".join(f"「{n}」" for n in names[:PRIOR_DOCS_MAX])
    more = f"ほか {len(names) - PRIOR_DOCS_MAX} 件" if len(names) > PRIOR_DOCS_MAX else ""
    return f"（前のターンの資料: {docs}{more}。本文は省略。{PRIOR_NOTE}）"


# ツールを呼ばずに「これから〜します」と予告しただけで終わった回答（小さいモデルが、実行せずに止まる）
ANNOUNCE_MAX_CHARS = 160
_CITE = re.compile(r"\[\d+\]")
_ANNOUNCE = re.compile(
    r"(?:(?:まず|これから|次に|それでは)[^。！？\n]*(?:します|いたします|てみます)"
    r"|(?:確認|取得|調査|検索|参照|読み取|読み込|探)(?:し|いた)(?:ます|てみます))[。.！!]?\s*$"
)
ANNOUNCE_NOTE = (
    "あなたの直前の応答は、これから行うことの予告だけで、ツールを呼んでいません。"
    "予告は書かず、実際にツール（search・get_outline・read_section・read_document など）を呼んで資料を調べ、"
    "その結果に基づいて、根拠にした資料の出典番号を付けて答えてください。"
)


def is_announce_only(answer: str) -> bool:
    """出典番号が無く、短く、「まず〜を取得します」のような予告で終わる回答か。"""
    text = answer.strip()
    return (
        bool(text)
        and len(text) <= ANNOUNCE_MAX_CHARS
        and not _CITE.search(text)
        and bool(_ANNOUNCE.search(text))
    )


# すべての差し戻しの依頼の末尾に付ける（R22）。依頼を利用者の発言と取り違えて返事・お詫びを書き、
# それが回答になるのを防ぐ（Gemma 4 12B の hm52: 英語の質問に、日本語の依頼への返事で答えた）
SEND_BACK_TAIL = (
    "\n\nこの依頼は利用者の発言ではありません（システムの確認です）。"
    "上でツールを使うよう求めているときは、本文を書く前に、まずそのツールを呼んでください"
    "（暗算で数字だけ書き換えない）。"
    "本文を書くときは、返事・お詫び・経緯の説明は書かず、"
    "利用者の元の質問への回答そのものを、元の質問と同じ言語で書いてください。"
)


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
    systems = ctx.mcp.systems if ctx.mcp is not None else []
    down = ctx.mcp.down if ctx.mcp is not None else []
    prompt = load_prompt("agent_system").format(
        today=today,
        citation_rule=citation,
        unknown_rule=unknown,
        grounds="社内の文書と社内システムの結果" if systems else "社内の文書",
    )
    if systems or down:
        # 社内システムを登録していて、使えるか応答しないものがあるターンだけ（specs/032 R15〜R18）
        catalog = ctx.mcp.catalog if ctx.mcp is not None else ""
        prompt += "\n\n" + load_prompt("agent_systems").format(
            systems="・".join(systems) or "なし", catalog=catalog or "（なし）"
        )
    if down:
        prompt += "\n" + load_prompt("agent_systems_down").format(down="・".join(down))
    return prompt


def asked_last_turn(prior: list[AnyMessage]) -> bool:
    """直前のターンが聞き返し（ask_user）で終わったか。"""
    last = next((m for m in reversed(prior) if isinstance(m, AIMessage) and not m.tool_calls), None)
    return bool(last is not None and last.additional_kwargs.get("clarify"))


def no_ask_reason(ctx: RunContext, prior: list[AnyMessage], again: bool) -> str | None:
    """聞き返し（ask_user）を外す理由。雑談・差し戻しの書き直し・続けての聞き返しでは使わせない。"""
    if ctx.primer is not None and ctx.primer.kind == "chat":
        return "chat"
    if again:
        return "rewrite"
    if asked_last_turn(prior):
        return "asked_last_turn"
    return None


def turn_start(messages: list[AnyMessage]) -> int:
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return i
    return 0


class InvestigateState(AgentState[Any]):
    """調査（create_agent の部分グラフ）と外側の流れで共有する状態の鍵（specs/029）。"""

    # 差し戻し中: 記録のステップの ID・表示名・入力・依頼の文・始めた時刻
    # （review が置き、書き直しの応答で消す）
    send_back: NotRequired[dict[str, Any] | None]
    # 差し戻した下書き（書き直しが空・返事なら、これを回答にする）
    draft: NotRequired[AIMessage | None]
    # 空の生成をやり直し中（やり直す前の応答の様子。guard が置き、やり直しの応答で消す）
    empty_pending: NotRequired[dict[str, Any] | None]
    # 予告だけの回答のやり直し（直前の回答を渡して、ツールを呼ぶよう依頼する）
    announce_pending: NotRequired[dict[str, Any] | None]
    # 差し戻しの直後に、ツールを呼ばずに書いた書き直しの元の下書き（guard が取り消しを判断する）
    rewrite_of: NotRequired[str | None]
    # 同じ呼び出しの続きとして数える差し戻しの回数（ツールを呼んだら 0 に戻す。回数の上限の判断に使う）
    chain: NotRequired[int]


class AgentPolicyMiddleware(AgentMiddleware[InvestigateState, RunContext]):
    """調査の中のモデル呼び出し: システムプロンプト・最初の検索結果の添付・前のターンの資料の圧縮・回数上限、
    差し戻し中なら下書きと依頼を添える。応答の後に、空のやり直しと差し戻しの結果を記録に残す。

    差し戻す・やり直す・下書きへ退避するという判断は外側の節点（guard・review）が行う。
    """

    state_schema = InvestigateState

    async def awrap_model_call(
        self,
        request: ModelRequest[RunContext],
        handler: Callable[[ModelRequest[RunContext]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any] | ExtendedModelResponse[Any]:
        ctx = request.runtime.context
        state = cast(dict[str, Any], request.state)
        send_back: dict[str, Any] | None = state.get("send_back")
        # 差し戻し・空のやり直しで同じ呼び出しをし直すときは、ターンに 1 度の記録を繰り返さない
        again = bool(send_back or state.get("empty_pending") or state.get("announce_pending"))
        msgs = list(request.messages)
        start = turn_start(msgs)
        # 前のターンのツール結果は文脈を圧迫するので置き換える（checkpoint の状態は変えない）
        first_prior = next((i for i, m in enumerate(msgs[:start]) if isinstance(m, ToolMessage)), None)
        names = cited_documents(msgs[:start], limit=50)
        compact: list[AnyMessage] = [
            m.model_copy(update={"content": prior_placeholder(names if i == first_prior else None)})
            if i < start and isinstance(m, ToolMessage)
            else m
            for i, m in enumerate(msgs)
        ]
        # システムが最初に検索した結果を、このターンの質問に添える（状態には保存しない）
        if (
            ctx.primer
            and ctx.primer.text
            and start < len(compact)
            and isinstance(compact[start], HumanMessage)
        ):
            q = compact[start]
            compact[start] = q.model_copy(update={"content": with_primer(q.text, ctx.primer)})
        calls = sum(1 for m in msgs[start:] if isinstance(m, AIMessage)) + 1
        ctx.stats.model_calls = calls
        emit = request.runtime.stream_writer
        replaced = sum(1 for m in msgs[:start] if isinstance(m, ToolMessage))
        if replaced and calls == 1 and not again:  # 呼び出しのたびに置き換えるが、記録はターンに 1 回
            record_system(
                emit,
                "system-compact",
                "compact_history",
                "前のターンの資料を省略",
                f"前のターンのツール結果 {replaced} 件を、モデルには省略の案内に置き換えて渡した",
                input={"replaced": replaced},
                output={
                    "placeholders": list(
                        dict.fromkeys(m.text for m in compact[:start] if isinstance(m, ToolMessage))
                    ),
                },
            )
        prompt = system_prompt(ctx)
        overrides: dict[str, Any] = {"messages": compact}
        if why := no_ask_reason(ctx, msgs[:start], again):
            # 聞き返しを使わせない場面（specs/031 R8）。ツールの一覧から外す
            overrides["tools"] = [t for t in request.tools if getattr(t, "name", None) != ASK_USER]
            if calls == 1 and not again and why == "asked_last_turn":
                record_system(
                    emit,
                    "system-no-ask",
                    "ask_user_blocked",
                    "聞き返しの制限",
                    "前のターンで聞き返したので、このターンは聞き返さずに答えさせる",
                    input={"reason": why},
                    output={"removed_tool": ASK_USER},
                )
        if ctx.mcp is not None:
            # 社内システムのツールは、このターンで使えるものだけを渡す（specs/032 R10・R14・R17）
            base = overrides.get("tools", request.tools)
            overrides["tools"] = [
                t
                for t in base
                if not is_mcp_tool(getattr(t, "name", "")) or getattr(t, "name", "") in ctx.mcp.usable
            ]
            if calls == 1 and not again:
                record_removed(ctx, emit)
        elif any(is_mcp_tool(getattr(t, "name", "")) for t in request.tools):
            overrides["tools"] = [
                t for t in overrides.get("tools", request.tools) if not is_mcp_tool(getattr(t, "name", ""))
            ]
        if calls >= ctx.cfg.max_steps:
            prompt += FINAL_NOTE
            overrides["tools"] = []
            if not again:
                record_system(
                    emit,
                    f"system-budget-{calls}",
                    "step_budget",
                    "呼び出しの上限",
                    f"{calls} 回目で上限（{ctx.cfg.max_steps} 回）に達したため、"
                    "ツールを外して最終回答を求めた",
                    input={"calls": calls, "max_steps": ctx.cfg.max_steps},
                    output={"note": FINAL_NOTE.strip()},
                )
        if announce := state.get("announce_pending"):
            # 予告だけで止まった回答: その回答と依頼を、この呼び出しの中だけに添える
            overrides["messages"] = [
                *compact,
                AIMessage(content=announce["answer"]),
                HumanMessage(ANNOUNCE_NOTE),
            ]
        if send_back:
            # 差し戻し: 下書きと依頼はこの呼び出しの中だけに添える（会話の状態には入れない）
            overrides["messages"] = [*compact, state["draft"], HumanMessage(send_back["note"])]
        t0 = time.perf_counter()
        try:
            response = await handler(request.override(system_message=SystemMessage(prompt), **overrides))
        except Exception as e:
            if send_back:
                finish_send_back(emit, send_back, None, error=str(e)[:300], ctx=ctx)
            raise
        record_model_call(ctx, emit, t0, response.result[-1] if response.result else None)
        update = self._after_response(ctx, emit, state, response)
        return ExtendedModelResponse(response, Command(update=update)) if update else response

    def _after_response(
        self, ctx: RunContext, emit: Any, state: Any, response: ModelResponse[Any]
    ) -> dict[str, Any]:
        """応答の直後の記録（空のやり直しの結果・差し戻しの結果）。空の応答は見張り（guard）に任せる。"""
        last = response.result[-1] if response.result else None
        if not isinstance(last, AIMessage) or is_empty(last):
            return {}
        update: dict[str, Any] = {}
        if state.get("announce_pending"):
            update["announce_pending"] = None
        if (pending := state.get("empty_pending")) is not None:
            record_empty(ctx, emit, {**pending, "retried": True}, {"result": "retried_ok"})
            update["empty_pending"] = None
        if send_back := state.get("send_back"):
            finish_send_back(emit, send_back, last, ctx=ctx)
            update["send_back"] = None
            # ツールを呼ばずに書き直したなら、取り消すかを見張りが判断する
            update["rewrite_of"] = None if last.tool_calls else send_back["input"]["draft"]
        if last.tool_calls and state.get("chain"):
            update["chain"] = 0
        return update


def tool_target(name: str, args: dict[str, Any]) -> str:
    """ツールが何を対象にしたか（検索のクエリ・読んだ文書や節）。記録の要約に使う。"""
    key = {
        "search": "query",
        "list_documents": "query",
        "keyword_search": "terms",
        "get_outline": "document",
        "read_document": "document",
        "read_section": "section",
    }.get(name)
    v = args.get(key) if key else None
    if isinstance(v, list):
        v = "・".join(str(x) for x in v)
    return str(v)[:60] if v else ""


def tool_title(name: str, ctx: RunContext | None) -> str:
    """記録の要約に書くツールの名前。社内システムのツールは「ERP（資材・購買）の get_stock」。"""
    if ctx is not None and ctx.mcp is not None and is_mcp_tool(name):
        spec = ctx.mcp.usable.get(name)
        if spec is not None:
            return f"{spec.server.label}の {spec.name}"
    return LABELS.get(name, (name,))[0]


def record_model_call(ctx: RunContext, emit: Any, t0: float, last: Any) -> None:
    """モデルの応答（ツールを選ぶ・回答を書く）を、測った時間とともに記録する（specs/029 T35）。

    検索などのツールは別のステップで時間を測る。これが無いと、モデルが考えて書く時間（多くは run の大半）が
    どの段階にも入らず、経路の段階の時間を足しても回答までの時間に合わない。失敗した呼び出しは、モデルの
    切り替え（switch_model）か run の失敗として記録されるので、ここでは記録しない。
    """
    ctx.stats.model_records += 1
    n = ctx.stats.model_records
    calls = list(last.tool_calls) if isinstance(last, AIMessage) else []
    tools = [c["name"] for c in calls]
    usage = getattr(last, "usage_metadata", None) or {}
    if tools:
        picked = [
            tool_title(c["name"], ctx) + (f"「{w}」" if (w := tool_target(c["name"], c["args"])) else "")
            for c in calls
        ]
        summary = f"ツールを選んだ: {'・'.join(picked)}"
    elif isinstance(last, AIMessage) and last.text.strip():
        summary = "回答を書いた"
    else:
        summary = "空の応答を返した"
    record_system(
        emit,
        f"system-model-{n}",
        "model_call",
        "モデルの応答",
        summary,
        duration_ms=elapsed_ms(t0),
        input={"call": n},
        output={
            "chose": tools,
            "answer_chars": len(last.text) if isinstance(last, AIMessage) else 0,
            **({"tokens_out": usage.get("output_tokens")} if usage.get("output_tokens") else {}),
        },
    )


def finish_send_back(
    emit: Any,
    send_back: dict[str, Any],
    redo: AnyMessage | None,
    *,
    error: str | None = None,
    ctx: RunContext | None = None,
) -> None:
    """差し戻しのステップを閉じる（書き直しで呼んだツール、または書き直したこと）。"""
    started = float(send_back["started"])
    if error is not None:
        summary, output, status = (
            "差し戻しに失敗しました",
            {"note": send_back["note"], "error": error},
            "error",
        )
    else:
        tools = [c["name"] for c in redo.tool_calls] if isinstance(redo, AIMessage) else []
        summary = f"「{send_back['input']['trigger']}」のため差し戻し → " + (
            f"{'・'.join(tool_title(n, ctx) for n in tools)} を実行" if tools else "回答を書き直し"
        )
        output, status = {"note": send_back["note"], "next_tools": tools}, "done"
    step = Step(
        id=send_back["id"],
        name="review",
        label=send_back["label"],
        status=status,  # type: ignore[arg-type]
        duration_ms=round((time.perf_counter() - started) * 1000),
        input=send_back["input"],
        output=output,
        summary=summary,
        node="review",
    )
    emit({"type": "step", "step": step.model_dump()})


def open_send_back(ctx: RunContext, emit: Any, review: Review, answer: str, searches: int) -> dict[str, Any]:
    """差し戻しを始める（記録に「見直し」のステップを出す）。返す値は状態の send_back に置く。"""
    ctx.stats.count_review(review.kind)
    send_back: dict[str, Any] = {
        "id": f"review-{ctx.stats.reviews}",
        "label": review.label,
        "input": {"kind": review.kind, "draft": answer, "trigger": review.trigger, "searches": searches},
        "note": review.note + SEND_BACK_TAIL,
        "started": time.perf_counter(),
    }
    step = Step(
        id=send_back["id"],
        name="review",
        label=review.label,
        status="running",
        input=send_back["input"],
        summary="下書きを差し戻して書き直し中",
        node="review",
    )
    emit({"type": "step", "step": step.model_dump()})
    return send_back


# 差し戻しへの返事の言い方（書き直しの冒頭にあれば、回答ではなく依頼への返事。specs/026 T29）
_REPLY = re.compile(
    r"了解|承知|かしこまりました|指示に従い|ご指摘|申し訳|失礼いたしました|"
    r"I understand|Understood|I will|I apologi[sz]e|Sorry",
    re.IGNORECASE,
)
REPLY_HEAD_CHARS = 40
_DISCARD_SUMMARY = {
    "no_citations": "書き直しで引用がすべて消えたため、差し戻す前の下書きを回答にした（確認は未了）",
    "reply_to_request": "書き直しが差し戻しへの返事だったため、差し戻す前の下書きを回答にした（確認は未了）",
}


def discard_reason(draft: str, rewrite: str) -> str | None:
    """差し戻しの後、ツールを呼ばずに書いた書き直しを捨てる理由。捨てないなら None。

    呼び出し側は、書き直しがツール呼び出しの無い応答（差し戻しの直後の最終回答）のときだけ使う。
    """
    if not rewrite.strip():
        return None
    if _MARK.search(normalize_markers(draft)) and not _MARK.search(normalize_markers(rewrite)):
        return "no_citations"
    if _REPLY.search(rewrite.strip()[:REPLY_HEAD_CHARS]):
        return "reply_to_request"
    return None


def record_discarded(ctx: RunContext, emit: Any, reason: str, kind: str, rewrite: str) -> None:
    ctx.stats.rewrites_discarded += 1
    record_system(
        emit,
        f"system-rewrite-discarded-{ctx.stats.rewrites_discarded}",
        "rewrite_discarded",
        "書き直しの取り消し",
        _DISCARD_SUMMARY[reason],
        input={"reason": reason, "review": kind},
        output={"discarded": rewrite[:200], "used": "draft", "pending_review": kind},
    )


def final_answer(msg: AnyMessage | None) -> str | None:
    """最終回答（ツール呼び出しの無い応答）の本文。そうでなければ None。"""
    if not isinstance(msg, AIMessage) or msg.tool_calls:
        return None
    return split_thinking(msg.text)[1]


def is_empty(msg: AnyMessage | None) -> bool:
    """ツール呼び出しも本文も無い応答（思考だけで切れた場合を含む）。"""
    answer = final_answer(msg)
    return answer is not None and not answer.strip()


def empty_detail(msg: AnyMessage | None) -> dict[str, Any]:
    """空の応答の様子（終わった理由・思考の文字数・出力のトークン数）。記録に残す。"""
    if not isinstance(msg, AIMessage):
        return {"finish_reason": None, "reasoning_chars": 0, "tokens_out": None}
    separate = msg.additional_kwargs.get("reasoning_content")
    thought = split_thinking(msg.text)[0]
    return {
        "finish_reason": msg.response_metadata.get("finish_reason"),
        "reasoning_chars": len(thought) + (len(separate) if isinstance(separate, str) else 0),
        "tokens_out": msg.usage_metadata["output_tokens"] if msg.usage_metadata else None,
    }


_EMPTY_SUMMARY = {
    "retried_ok": "回答が空だったため、同じ要求でやり直して回答できた",
    "used_draft": "書き直しが空だったため、差し戻す前の下書きを回答にした（確認は未了）",
    "failed": "回答が空のままで、使える下書きも無かった",
}


def record_empty(ctx: RunContext, emit: Any, inp: dict[str, Any], out: dict[str, Any]) -> None:
    ctx.stats.empty_events += 1
    record_system(
        emit,
        f"system-empty-{ctx.stats.empty_events}",
        "empty_generation",
        "回答の生成のやり直し",
        _EMPTY_SUMMARY[out["result"]],
        input=inp,
        output=out,
    )


def draft_of(ctx: RunContext, turn: list[AnyMessage], answer: str) -> Draft:
    """このターンのメッセージと実行文脈を、確認の規則に渡す値に写す（specs/037 R9）。"""
    results = [
        ToolResult(
            name=m.name or "",
            text=str(m.text),
            ok=m.status != "error",
            out=ToolOutput.from_artifact(str(m.text), m.artifact),
            mcp=is_mcp_tool(m.name or ""),
        )
        for m in turn
        if isinstance(m, ToolMessage)
    ]
    # 履歴の要約で結果のメッセージが消えても数えられるよう、呼び出しの記録（tool_seen）からも拾う
    called = {k.split(":", 1)[0] for k in ctx.tool_seen} | {r.name for r in results}
    return Draft(
        answer=answer,
        question=ctx.user_question or _asked(turn) or ctx.question,
        results=results,
        registry=ctx.registry,
        primer=ctx.primer,
        primer_searches=ctx.stats.primer_searches,
        mcp=ctx.mcp,
        mcp_called={n for n in called if is_mcp_tool(n)},
        check_numbers=checks_numbers(ctx),
        number_sources=[ctx.question, datetime.now(TZ).strftime("%Y年%m月%d日")],
    )


def searches(ctx: RunContext, turn: list[AnyMessage]) -> int:
    """このターンの検索の回数（システムが最初に行った分を含む）。"""
    return draft_of(ctx, turn, "").searches


def checks_numbers(ctx: RunContext) -> bool:
    # 雑談と、一般知識で補ってよい設定では照合しない
    return ctx.cfg.admit_unknown and (ctx.primer is None or ctx.primer.kind != "chat")


def review_skip(ctx: RunContext, calls: int, has_tools: bool) -> str | None:
    """見直しをしない理由（回数に余裕が無い・雑談）。見直す場合は None。"""
    if not has_tools or calls + 2 > ctx.cfg.max_steps:
        return "limit"
    if ctx.primer is not None and ctx.primer.kind == "chat":
        return "chat"
    return None


def record_review_pass(emit: Any, n: int, skip: str | None, done: Collection[str]) -> None:
    """確認を差し戻さずに通したことを記録に残す（specs/029。通過も確認の節点の動き）。"""
    if skip == "limit":
        summary = "回数に余裕が無いので、見直さずに通した"
    elif skip == "chat":
        summary = "雑談なので、見直さずに通した"
    else:
        summary = "当てはまる見直しが無いので通した"
        if done:
            summary += "（" + "・".join(REVIEW_LABELS.get(k, k) for k in done) + " は済み）"
    record_system(
        emit,
        f"system-review-pass-{n}",
        "review_passed",
        "確認の通過",
        summary,
        input={"skip": skip, "done": list(done)},
        output={"result": "pass"},
    )


def _asked(turn: list[AnyMessage]) -> str:
    return next((m.text for m in turn if isinstance(m, HumanMessage)), "")


def pick_review(
    ctx: RunContext,
    turn: list[AnyMessage],
    answer: str,
    calls: int,
    has_tools: bool,
    done: Collection[str] = (),
) -> Review | None:
    """最終回答の下書きを差し戻すなら、その理由を返す。回数に余裕が無い・雑談のときは差し戻さない。

    規則は review_rules.RULES の順に確かめる。done はこのターンで済んだ確認の種類（種類ごとに 1 度まで）。
    """
    if review_skip(ctx, calls, has_tools):
        return None
    return pick(draft_of(ctx, turn, answer), done)


REASON_NOTE = (
    "この下書きが挙げた理由は、引用した資料には、質問の事柄の理由としては書かれていません"
    "（判定: {why}）。その事柄の理由が書かれた資料を、その事柄に絞った語で search してください。"
    "見つからなければ、結論に「理由は資料に書かれていない」と書き、関連する事実を添えるときは、"
    "それぞれの資料に書いてあることを分けて書き、つないだ部分は推測と明記してください。" + KEEP_CITATIONS
)


REASON_CAVEAT = (
    "※ 資料には、この理由はそのまま書かれていません。上の理由は、別々の資料の記述をつないだ推測です。"
)


async def _check_reason(
    ctx: RunContext, emit: Any, turn: list[AnyMessage], answer: str, *, again: bool
) -> ReasonCheck | None:
    """回答の理由が引用した資料に書かれているかを確かめ、記録に残す。確かめない場面では None。"""
    asked = turn[0].text if turn and isinstance(turn[0], HumanMessage) else ""
    question = ctx.user_question or asked or ctx.question
    model = ctx.utility_model
    if model is None or not asks_reason(question):
        return None
    nums = sorted({int(n) for n in _MARK.findall(answer)})
    materials = {n: c.text for n in nums if (c := ctx.registry.get(n)) is not None}
    if not materials:
        return None  # 引用の無い回答は「理由は書かれていない」側。調べ残しの見直しに任せる
    got = await check_reason(model, question, answer, materials)
    verdict = {True: "裏付けあり", False: "裏付けなし", None: "判定できず"}[got.supported]
    record_system(
        emit,
        "system-reason-recheck" if again else "system-reason-check",
        "reason_check",
        "理由の裏付けの再確認" if again else "理由の裏付けの確認",
        f"{'書き直した' if again else ''}回答の理由が、引用した資料 {len(materials)} 件に"
        f"書かれているかを確かめた（{verdict}）",
        duration_ms=got.ms,
        input={"question": question[:300], "cited": nums, "again": again},
        output={"supported": got.supported, "why": got.why}
        | ({"error": got.error} if got.error else {})
        | ({"raw": got.raw} if got.supported is None and got.raw else {}),
    )
    return got


async def reason_review(
    ctx: RunContext, emit: Any, turn: list[AnyMessage], answer: str, done: Collection[str]
) -> Review | None:
    """理由を尋ねる質問で、回答の理由が引用した資料に書かれているかを補助モデルで確かめる（specs/031 R12）。

    確かめたことは結果にかかわらず記録に残す。裏付けが無ければ差し戻す（ターンに 1 度）。
    """
    if REASON in done:
        return None
    got = await _check_reason(ctx, emit, turn, answer, again=False)
    if got is None or got.supported is not False:
        return None
    return Review(REASON, got.why or "理由の裏付けなし", REASON_NOTE.format(why=got.why), REASON_LABEL)


async def reason_caveat(
    ctx: RunContext, emit: Any, turn: list[AnyMessage], answer: str, done: Collection[str]
) -> str | None:
    """差し戻した後の書き直しをもう一度確かめ、まだ裏付けが無ければ回答に添える注記を返す（specs/031 R13）。

    小さいモデルは差し戻されても同じ理由を書き直すことがある。そのときは回答を止めず、推測だと明記する。
    """
    if REASON not in done:
        return None
    got = await _check_reason(ctx, emit, turn, answer, again=True)
    return REASON_CAVEAT if got is not None and got.supported is False else None


def record_number_check(ctx: RunContext, emit: Any, turn: list[AnyMessage], answer: str) -> None:
    """数字の照合の結果を記録に残す（見当たらない数字は画面で注意として示す）。"""
    found = numbers_in(_MARK.sub("", answer))
    if not found:
        return
    t0 = time.perf_counter()
    res = draft_of(ctx, turn, answer).numbers
    took = elapsed_ms(t0)
    missing = res.missing
    # 回答の内訳から和・差で確かめた数字も、黙って通さず記録に残す（R24）
    derived = "・".join(d["value"] for d in res.derived[:8])
    record_system(
        emit,
        "system-number-check",
        "number_check",
        "数字の照合",
        (
            "回答の数字のうち " + "・".join(missing[:8]) + " が資料・計算結果に見当たらない"
            if missing
            else f"回答の数字 {len(found)} 個を資料・計算結果と照合した（すべて確認"
            + (f"。{derived} は回答の内訳から確かめた）" if derived else "）")
        ),
        duration_ms=took,
        input={"checked": len(found)},
        output={"unverified": missing[:20], "derived": res.derived[:20]},
    )


_MARK = re.compile(r"\[(\d+)\](?!\()")


DUPLICATE_NOTE = (
    "同じツールを同じ引数でこのターンに既に呼んでいます（結果は同じなので実行しませんでした）。"
    "その結果を使ってください。章立ての続きは get_outline に start を、本文は read_section を使います。"
    "前の結果に求める値が無かったなら、別のツールか別の語で探すか、見つからなかったと答えてください。"
)


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
        spec = ctx.mcp.usable.get(name) if ctx.mcp is not None else None
        if spec is not None:  # 社内システム（specs/032 R23）
            # 何をどの条件で聞いているかを出す（specs/033 R18。経過の秒は画面が数える）
            asked = " ".join(f"{k}={v}" for k, v in call["args"].items() if v not in (None, "", [], {}))
            label = f"社内システム: {spec.server.label}"
            running = f"{spec.server.label} に問い合わせ中: {spec.name} {asked}".strip()
        clock = StepClock(
            emit,
            Step(id=cid, name=name, label=label, status="running", input=dict(call["args"]), summary=running),
        )
        key = f"{name}:{json.dumps(call['args'], ensure_ascii=False, sort_keys=True)}"
        if name != ASK_USER and key in ctx.tool_seen:
            # 同じ引数の呼び出しは結果も同じなので実行しない（specs/031 R4）。黙って省かず記録に残す
            clock.done("同じ呼び出しの繰り返しのため実行しなかった", {"skipped": "duplicate"})
            return ToolMessage(content=DUPLICATE_NOTE, tool_call_id=cid, name=name)
        ctx.tool_seen.add(key)
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
        out = ToolOutput.from_artifact(text, result.artifact if isinstance(result, ToolMessage) else None)
        n = out.materials
        summary = f"資料 {n} 件" if n else (text[:120] if name == "calculate" else "完了")
        # 何を探した・読んだかを要約の頭に（システムが行った検索と同じ形「…」・資料 n 件）
        if (what := tool_target(name, call["args"])) and name not in {"calculate", "table_query"}:
            summary = f"「{what}」・{summary}"
        output: dict[str, Any] = {"result": text[:2000]}
        if name == "table_query":
            summary = f"{out.rows[0]} 行中 {out.rows[1]} 行" if out.rows else text[:120]
            # 画面で行・件数・集計を見せるための構造（モデルに渡す文は変えない。specs/028 T8）
            output.update(ctx.table_outputs.pop(cid, {}))
        if is_mcp_tool(name):
            rec = ctx.table_outputs.pop(cid, None)
            output.update(rec or {})
            # モデルに渡した文をそのまま（specs/036 R8。社内システムの結果は max_chars までなので切らない）
            output["result"] = text
            secs = (time.perf_counter() - clock.t0) or 0.0
            summary = (
                f"{rec['system']}・{rec['total']} 行・{secs:.1f} 秒"
                if rec and "columns" in rec
                else text[:120]
            )
        if n and out.fallback == "semantic":
            summary = f"完全一致 0 件 → セマンティック検索で資料 {n} 件"
        elif n and out.fallback == "codes":
            summary = f"完全一致 0 件 → 型番のみで資料 {n} 件"
        clock.done(summary, output)
        return result


def clean_answer(ctx: RunContext, emit: Any, last: AIMessage) -> AIMessage | None:
    """回答の引用記号を正規化し、登録されていない番号を除く（R18）。考えた過程と末尾の言い直しも落とす。

    変えたら記録に残し、置き換える AIMessage（同じ ID）を返す。変えなければ None。
    """
    text = last.text
    thought, answer = split_thinking(text)  # 考えた過程は「考えた過程」のステップで見せる
    known = set(ctx.registry.numbers())
    normalized = normalize_markers(answer)
    stripped = strip_unknown(normalized, known)
    tailed = drop_repeated_tail(stripped)
    tail_dropped = len(stripped) - len(tailed)
    fixed = _prune(ctx, emit, tailed) if ctx.citation_prune else tailed
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
    if tail_dropped:
        notes.append(f"末尾の言い直し {tail_dropped} 文字を消した")
    if tailed != fixed:
        notes.append("値を書いていない資料の番号を外した（引用の刈り込み）")
    record_system(
        emit,
        "system-citation-cleanup",
        "citation_cleanup",
        "回答の整形",
        "・".join(notes) or "回答を整えた",
        input={"before": text[:4000]},
        output={
            "after": fixed[:4000],
            "removed_numbers": removed,
            "tail_dropped_chars": tail_dropped,
            "thinking_chars": len(thought or ""),
        },
    )
    return AIMessage(content=fixed, id=last.id, usage_metadata=last.usage_metadata)


def _prune(ctx: RunContext, emit: Any, answer: str) -> str:
    """値を書いていない資料の番号を、その文から外す（specs/026 T31）。外したら記録に残す。"""
    reg = ctx.registry
    materials = {
        c.n: "\n".join(x for x in (c.document_name, c.heading_path, c.context, c.text) if x)
        for c in reg.items()
    }
    # 質問に出た値は判断に使わない（T34）。画像の説明は含めない
    question = ctx.user_question or ctx.question
    t0 = time.perf_counter()
    pruned_text, pruned = prune_citations(answer, materials, question=question)
    took = elapsed_ms(t0)
    names = {c.n: c.document_name for c in reg.items()}
    for p in pruned:
        # 番号は保存のときに振り直されるので、どの資料を外し・残したかを名前でも残す
        p["documents"] = {str(n): names.get(n, "") for n in sorted([*p["removed"], *p["kept"]])}
    if pruned:
        removed = sorted({n for p in pruned for n in p["removed"]})
        record_system(
            emit,
            "system-citation-pruned",
            "citation_pruned",
            "引用の刈り込み",
            f"{len(pruned)} つの文から、値を書いていない資料の番号 "
            + "".join(f"[{n}]" for n in removed)
            + " を外した",
            duration_ms=took,
            input={"sentences": len(pruned)},
            output={"pruned": pruned},
        )
    return pruned_text


class RecordedSummarization(SummarizationMiddleware):
    """会話が長くなったときの要約。要約したこと（何件を置き換え、どんな要約にしたか）を記録に残す。"""

    async def abefore_model(self, state: Any, runtime: Runtime[Any]) -> dict[str, Any] | None:
        before = list(state["messages"])
        t0 = time.perf_counter()
        result = await super().abefore_model(state, runtime)
        took = elapsed_ms(t0)
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
            duration_ms=took,
            input={"messages_before": len(before), "kept": kept},
            output={"summary": summary[:4000]},
        )
        return result
