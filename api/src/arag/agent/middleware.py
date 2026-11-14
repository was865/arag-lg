"""調査（create_agent の部分グラフ）の middleware と、回答の流れの節点が使う判断・記録（specs/005・029）。"""

import re
import time
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass
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
from arag.agent.numbers import NumberCheck, check_numbers, numbers_in
from arag.agent.ops import KEYWORD_FALLBACK_NOTE, KEYWORD_RELAX_NOTE
from arag.agent.primer import with_primer
from arag.agent.prior import cited_documents
from arag.agent.prune import prune_citations
from arag.agent.steps import Step, StepClock, record_system
from arag.agent.thinking import split_thinking
from arag.agent.tools import LABELS
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


# 差し戻しの依頼に添える（書き直しで出典番号が落ちて引用が付かなくなるのを防ぐ）。
# 「[n]」と書くと小さいモデルがそのまま写すので、実際の数字の例で示す
KEEP_CITATIONS = "書き直すときも、根拠にした資料の出典番号（[3] など、実際の番号）を残してください。"
# すべての差し戻しの依頼の末尾に付ける（R22）。依頼を利用者の発言と取り違えて返事・お詫びを書き、
# それが回答になるのを防ぐ（Gemma 4 12B の hm52: 英語の質問に、日本語の依頼への返事で答えた）
SEND_BACK_TAIL = (
    "\n\nこの依頼は利用者の発言ではありません（システムの確認です）。"
    "上でツールを使うよう求めているときは、本文を書く前に、まずそのツールを呼んでください"
    "（暗算で数字だけ書き換えない）。"
    "本文を書くときは、返事・お詫び・経緯の説明は書かず、"
    "利用者の元の質問への回答そのものを、元の質問と同じ言語で書いてください。"
)
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
    "調べても見つからない点だけを、見つからないと書いてください。" + KEEP_CITATIONS
)
# モデル自身の検索がこの回数を超えていれば、調べ尽くしたとみなす（システムの最初の検索は数えない）
GAP_REVIEW_MAX_OWN_SEARCHES = 1
SEARCH_TOOLS = {"search", "keyword_search"}
TABLE_NOTE = (
    "この質問は、表の行を条件で選ぶ・数える・集計する必要があります。目で比べたり暗算したりすると誤ります。"
    "回答する前に table_query を使ってください（source に表のある資料の出典番号、where に行の条件、"
    "必要なら compute に行ごとの計算式）。その結果どおりに答えてください。" + KEEP_CITATIONS
)
NUMBER_NOTE = (
    "この下書きの数字 {numbers} は、資料にも計算結果にも見当たりません。"
    "資料の値はそのまま書き写してください。計算した値なら calculate か table_query で計算し直してください。"
    "資料に無い数字は書かないでください。" + KEEP_CITATIONS
)
# 資料の中の表の行（Markdown）
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$\n\s*\|[\s:\-|]+\|\s*$", re.MULTILINE)


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


def turn_start(messages: list[AnyMessage]) -> int:
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return i
    return 0


@dataclass(frozen=True, slots=True)
class Review:
    """下書きを差し戻す理由（specs/026 ④）。kind は記録と画面で種類を見分けるのに使う。"""

    kind: str  # gap / table / numbers
    trigger: str
    note: str
    label: str


class InvestigateState(AgentState[Any]):
    """調査（create_agent の部分グラフ）と外側の流れで共有する状態の鍵（specs/029）。"""

    # 差し戻し中: 記録のステップの ID・表示名・入力・依頼の文・始めた時刻
    # （review が置き、書き直しの応答で消す）
    send_back: NotRequired[dict[str, Any] | None]
    # 差し戻した下書き（書き直しが空・返事なら、これを回答にする）
    draft: NotRequired[AIMessage | None]
    # 空の生成をやり直し中（やり直す前の応答の様子。guard が置き、やり直しの応答で消す）
    empty_pending: NotRequired[dict[str, Any] | None]
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
        again = bool(send_back or state.get("empty_pending"))
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
        if send_back:
            # 差し戻し: 下書きと依頼はこの呼び出しの中だけに添える（会話の状態には入れない）
            overrides["messages"] = [*compact, state["draft"], HumanMessage(send_back["note"])]
        try:
            response = await handler(request.override(system_message=SystemMessage(prompt), **overrides))
        except Exception as e:
            if send_back:
                finish_send_back(emit, send_back, None, error=str(e)[:300])
            raise
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
        if (pending := state.get("empty_pending")) is not None:
            record_empty(ctx, emit, {**pending, "retried": True}, {"result": "retried_ok"})
            update["empty_pending"] = None
        if send_back := state.get("send_back"):
            finish_send_back(emit, send_back, last)
            update["send_back"] = None
            # ツールを呼ばずに書き直したなら、取り消すかを見張りが判断する
            update["rewrite_of"] = None if last.tool_calls else send_back["input"]["draft"]
        if last.tool_calls and state.get("chain"):
            update["chain"] = 0
        return update


def finish_send_back(
    emit: Any, send_back: dict[str, Any], redo: AnyMessage | None, *, error: str | None = None
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
            f"{'・'.join(tools)} を実行" if tools else "回答を書き直し"
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
    if review.kind == "gap":
        ctx.stats.gap_reviews += 1
    elif review.kind == "table":
        ctx.stats.table_reviews += 1
    else:
        ctx.stats.number_reviews += 1
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


def searches(ctx: RunContext, turn: list[AnyMessage]) -> int:
    """このターンの検索の回数（システムが最初に行った分を含む）。"""
    own = sum(1 for m in turn if isinstance(m, ToolMessage) and m.name in SEARCH_TOOLS)
    return own + ctx.stats.primer_searches


def _materials(ctx: RunContext, turn: list[AnyMessage]) -> list[str]:
    """このターンにモデルへ渡した資料（最初の検索結果とツールの結果）。"""
    out = [str(m.text) for m in turn if isinstance(m, ToolMessage) and m.status != "error"]
    if ctx.primer and ctx.primer.text:
        out.append(ctx.primer.text)
    return out


def checks_numbers(ctx: RunContext) -> bool:
    # 雑談と、一般知識で補ってよい設定では照合しない
    return ctx.cfg.admit_unknown and (ctx.primer is None or ctx.primer.kind != "chat")


def _check_numbers(ctx: RunContext, turn: list[AnyMessage], answer: str) -> NumberCheck:
    today = datetime.now(TZ).strftime("%Y年%m月%d日")
    return check_numbers(answer, [*_materials(ctx, turn), ctx.question, today])


def _ungrounded(ctx: RunContext, turn: list[AnyMessage], answer: str) -> list[str]:
    return _check_numbers(ctx, turn, answer).missing


REVIEW_NAMES = {"gap": "調べ残しの見直し", "table": "表の集計の確認", "numbers": "数字の確認"}


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
            summary += "（" + "・".join(REVIEW_NAMES.get(k, k) for k in done) + " は済み）"
    record_system(
        emit,
        f"system-review-pass-{n}",
        "review_passed",
        "確認の通過",
        summary,
        input={"skip": skip, "done": list(done)},
        output={"result": "pass"},
    )


def pick_review(
    ctx: RunContext,
    turn: list[AnyMessage],
    answer: str,
    calls: int,
    has_tools: bool,
    done: Collection[str] = (),
) -> Review | None:
    """最終回答の下書きを差し戻すなら、その理由を返す。回数に余裕が無い・雑談のときは差し戻さない。

    done はこのターンで済んだ確認の種類（種類ごとに 1 度まで）。
    """
    if review_skip(ctx, calls, has_tools):
        return None
    own = sum(1 for m in turn if isinstance(m, ToolMessage) and m.name in SEARCH_TOOLS)
    # 最初の検索が 0 件・関連度の低い資料だけなら、「見つからない」は資料に無い質問への正しい答え（T17）
    weak = ctx.primer is not None and ctx.primer.weak
    if "gap" not in done and not weak and searches(ctx, turn) and own <= GAP_REVIEW_MAX_OWN_SEARCHES:
        # 複数の資料を照合する質問で、小さいモデルは 1 回の検索だけで「資料に無い」と答えがち
        if m := GAP.search(answer):
            return Review("gap", m.group(0), GAP_NOTE, "調べ残しの見直し")
    if (
        "table" not in done
        and ctx.primer is not None
        and ctx.primer.table
        and not any(isinstance(m, ToolMessage) and m.name == "table_query" for m in turn)
        and any(_TABLE_ROW.search(t) for t in _materials(ctx, turn))
    ):
        # 表の行を目で比べると誤る（在庫 4・発注点 4 を「下回る」と答えるなど）
        return Review("table", "表の集計を計算していない", TABLE_NOTE, "表の集計の確認")
    if "numbers" not in done and checks_numbers(ctx):
        if missing := _ungrounded(ctx, turn, answer):
            shown = "・".join(missing[:8])
            return Review(
                "numbers", f"資料に無い数字 {shown}", NUMBER_NOTE.format(numbers=shown), "数字の確認"
            )
    return None


def record_number_check(ctx: RunContext, emit: Any, turn: list[AnyMessage], answer: str) -> None:
    """数字の照合の結果を記録に残す（見当たらない数字は画面で注意として示す）。"""
    found = numbers_in(_MARK.sub("", answer))
    if not found:
        return
    res = _check_numbers(ctx, turn, answer)
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
        input={"checked": len(found)},
        output={"unverified": missing[:20], "derived": res.derived[:20]},
    )


_MATERIAL = re.compile(r"<資料 n=")
# table_query の結果の先頭（「表…（8 行）。条件 … に合う行: 2 行。」）
_TABLE_RESULT = re.compile(r"（(\d+) 行）。[^\n]*?(\d+) 行。")
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
        output: dict[str, Any] = {"result": text[:2000]}
        if name == "table_query":
            rows = _TABLE_RESULT.search(text)
            summary = f"{rows.group(1)} 行中 {rows.group(2)} 行" if rows else text[:120]
            # 画面で行・件数・集計を見せるための構造（モデルに渡す文は変えない。specs/028 T8）
            output.update(ctx.table_outputs.pop(cid, {}))
        if n and text.startswith(KEYWORD_FALLBACK_NOTE):
            summary = f"完全一致 0 件 → セマンティック検索で資料 {n} 件"
        elif n and text.startswith(KEYWORD_RELAX_NOTE):
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
    pruned_text, pruned = prune_citations(answer, materials, question=question)
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
            input={"sentences": len(pruned)},
            output={"pruned": pruned},
        )
    return pruned_text


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
