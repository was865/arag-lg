"""回答の流れを明示のグラフにする（specs/029 R1〜R4）。

外側の `StateGraph` に節点と辺を書き、調査（モデル ⇄ ツールの輪）は create_agent の部分グラフとして
`investigate` の 1 節点に入れる。要約・モデルの切り替え・ツールのステップの記録・回数の上限は、今の
middleware のまま部分グラフに残す。外に出したのは流れの制御（雑談は検索を飛ばす・空の生成をやり直す・
下書きへ退避する・確認で差し戻す）だけ。

辺の関数は状態だけを見る純関数（`route_after_*`）。判断は節点が状態に書き、辺はそれを読むだけにする。
節点の並びと表示名・説明は `NODES`（図と画面の流れの表示が同じ源から出る。`arag.agent.diagram`）。
"""

from dataclasses import dataclass
from typing import Annotated, Any, Literal, NotRequired, TypedDict, cast

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, RemoveMessage, ToolMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.runtime import Runtime

from arag.agent.citations import cited_numbers, finalize_citations
from arag.agent.context import Completion, RunContext
from arag.agent.middleware import (
    ANNOUNCE_NOTE,
    AgentPolicyMiddleware,
    RecordedSummarization,
    StepMiddleware,
    checks_numbers,
    clean_answer,
    discard_reason,
    empty_detail,
    final_answer,
    finish_send_back,
    is_announce_only,
    open_send_back,
    pick_review,
    reason_caveat,
    reason_review,
    record_discarded,
    record_empty,
    record_number_check,
    record_review_pass,
    review_skip,
    searches,
    turn_start,
)
from arag.agent.model_switch import ModelSwitchMiddleware
from arag.agent.primer import primer_search_node, understand_node
from arag.agent.query_image import with_image_description
from arag.agent.steps import Step, StepClock, record_system, tag_node
from arag.agent.tools import ASK_USER, TOOLS
from arag.logging import get_logger

log = get_logger("arag.agent.flow")

NO_ANSWER_TEXT = {
    "no_sources": "社内の資料から、この質問に答えられる情報は見つかりませんでした。"
    "言い方を変えるか、検索範囲（ナレッジベース）を広げてもう一度お試しください。",
    "step_budget_exhausted": "調べる回数の上限に達したため、回答をまとめられませんでした。"
    "質問を絞るか、エージェント設定の「最大ステップ数」を増やしてください。",
    "tool_failed": "検索の実行に失敗したため回答できませんでした。しばらくしてからもう一度お試しください。",
    "generation_failed": "回答の生成に失敗しました。しばらくしてからもう一度お試しください。",
    "empty_generation": "回答を生成できませんでした。もう一度お試しください。",
}


@dataclass(frozen=True, slots=True)
class NodeInfo:
    id: str
    label: str  # 画面と図の表示名
    description: str  # 図の説明（1 行）


# 節点の並び（左から右）。図・画面の流れの表示・推定の規則はこの順に従う
NODES: tuple[NodeInfo, ...] = (
    NodeInfo("read_image", "画像", "添付画像を文章にして質問に添える（画像が無ければ素通り）"),
    NodeInfo(
        "understand", "理解", "質問の種類・検索語・表の集計の要否を整理する（初回は質問文での検索と並行）"
    ),
    NodeInfo("primer_search", "最初の検索", "整理した検索語で検索し、結果を質問に添える用意をする"),
    NodeInfo(
        "investigate", "調査", "モデルとツールの輪（create_agent。要約・モデルの切り替え・回数の上限を含む）"
    ),
    NodeInfo("guard", "見張り", "空の生成のやり直し・差し戻しへの返事や引用の消えた書き直しの取り消し"),
    NodeInfo("review", "確認", "調べ残し・表の集計・数字を確かめ、当てはまれば差し戻す（種類ごとに 1 度）"),
    NodeInfo("finalize", "確定", "数字の照合・引用の整形と刈り込み・回答の分類をして、完了を送る"),
    NodeInfo("followups", "続けて聞く", "完了の後に、続けて聞く質問の候補を作って届ける"),
)

# 条件つきの辺の札（辺の関数が返す値 → 表示名）
EDGE_LABELS: dict[str, str] = {
    "chat": "雑談",
    "docs": "資料",
    "retry": "やり直し",
    # 下書きへの退避と聞き返しは、どちらも確認を通さずに確定へ進む（図では 1 本の辺）
    "use_draft": "下書き・聞き返し",
    "investigate": "調査へ",
    "clarify": "聞き返し",
    "ok": "通過",
    "send_back": "差し戻し",
    "pass": "通過",
    "followups": "候補あり",
    "end": "なし",
}


class FlowState(TypedDict):
    """回答の流れの状態。`messages` は調査の部分グラフと共有する。

    流れの制御の鍵はターンの始め（read_image）で初期値に戻す（前のターンから持ち越さない）。
    """

    messages: Annotated[list[AnyMessage], add_messages]
    # 質問の理解（kind・queries・table と、primer_search で検索する残りの語）
    understanding: NotRequired[dict[str, Any] | None]
    # 調査と共有（middleware.InvestigateState と同じ鍵）
    send_back: NotRequired[dict[str, Any] | None]
    draft: NotRequired[AIMessage | None]
    empty_pending: NotRequired[dict[str, Any] | None]
    announce_pending: NotRequired[dict[str, Any] | None]
    rewrite_of: NotRequired[str | None]
    chain: NotRequired[int]
    # 差し戻した下書きの確認の種類
    draft_kind: NotRequired[str | None]
    # 済んだ確認の種類（gap・table・numbers）
    reviews_done: NotRequired[list[str]]
    # 空の生成のやり直しの回数（ターンに 1 度まで）
    empty_retries: NotRequired[int]
    # 予告だけの回答のやり直しの回数（ターンに 1 度まで）
    announce_retries: NotRequired[int]
    # 見張りの判断（retry・use_draft・ok）
    guard: NotRequired[str | None]
    # 確定の理由（answered・used_draft・empty_failed）
    outcome: NotRequired[str | None]
    no_answer_reason: NotRequired[str | None]
    # 続けて聞く候補を作るか・作った候補
    followups: NotRequired[bool]
    suggestions: NotRequired[list[str]]
    # 回答の末尾に添える注記（理由の裏付けが無いまま書き直された回答。specs/031 R13）
    caveat: NotRequired[str | None]
    # 最初の検索の後にシステムが決めた聞き返し（question・options・reason。specs/031 R14）
    clarify: NotRequired[dict[str, Any] | None]


# ターンの始めに戻す値
FRESH: dict[str, Any] = {
    "understanding": None,
    "send_back": None,
    "draft": None,
    "draft_kind": None,
    "empty_pending": None,
    "announce_pending": None,
    "rewrite_of": None,
    "chain": 0,
    "reviews_done": [],
    "empty_retries": 0,
    "announce_retries": 0,
    "guard": None,
    "outcome": None,
    "no_answer_reason": None,
    "followups": False,
    "suggestions": [],
    "caveat": None,
    "clarify": None,
}


# ── 節点 ──


async def read_image(state: FlowState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    """添付画像を文章にして質問に添える（specs/017 R4・R5）。画像が無ければ流れの状態を戻すだけ。"""
    ctx = runtime.context
    ctx.tool_seen.clear()  # 同じ呼び出しの繰り返しはターンの中だけで見る
    hook = ctx.hooks.read_image
    if hook is None:
        return dict(FRESH)
    emit = tag_node(runtime.stream_writer, "read_image")
    question = state["messages"][-1]
    clock = StepClock(
        emit,
        Step(id=f"img-{ctx.hooks.image_id}", name="read_image", label="画像の読み取り", status="running"),
    )
    description: str | None = None
    try:
        description = await hook(question.text)
        clock.done("読み取りました", {"description": description})
    except Exception as e:
        log.warning("read_image_failed", error=f"{type(e).__name__}: {e}")
        clock.done("画像を読み取れませんでした", {"error": str(e)[:200]}, error=True)
    query = with_image_description(question.text, description)
    ctx.question = query  # 検索語の書き換えでも画像の内容を踏まえる（R5）
    return {**FRESH, "messages": [HumanMessage(content=query, id=question.id)]}


async def guard(state: FlowState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    """調査の最後の応答を見張る（specs/026 R25・T29）。

    - 空の生成（本文もツール呼び出しも無い）: ターンに 1 度だけやり直す。だめなら差し戻した下書きを
      回答にする。下書きも無ければ空のまま確定へ（empty_generation）。
    - 差し戻しの直後にツールを呼ばずに書いた書き直しが、差し戻しへの返事・引用の消えたものなら、
      取り消して下書きへ。
    どの場合も記録に残す。
    """
    ctx, emit = runtime.context, tag_node(runtime.stream_writer, "guard")
    last = state["messages"][-1] if state["messages"] else None
    if isinstance(last, ToolMessage) and last.name == ASK_USER:
        # 聞き返しでターンを終える（specs/031 R7）。確認は通さない（問いには資料の事実が無い）
        # 見張りが確定へ回したことも記録に残す（経路で見張りの停留所にする。specs/029 T42）
        record_system(
            emit,
            "system-guard-clarify",
            "guard_clarify",
            "聞き返しで終える",
            "モデルが聞き返したので、確認を通さずに確定へ進めた",
            input={"tool": ASK_USER},
            output={"result": "clarify"},
        )
        return {"guard": "clarify", "outcome": "clarify"}
    answer = final_answer(last)
    pending = state.get("empty_pending")
    draft = state.get("draft")
    if answer is not None and not answer.strip():
        assert last is not None and last.id is not None
        detail = empty_detail(last)
        if not state.get("empty_retries"):
            ctx.stats.empty_retries += 1
            return {
                "messages": [RemoveMessage(id=last.id)],
                "empty_retries": 1,
                "empty_pending": detail,
                "guard": "retry",
            }
        retried = pending is not None
        if draft is not None:
            out = {"result": "used_draft", "pending_review": state.get("draft_kind")}
            record_empty(ctx, emit, {**detail, "retried": retried}, out)
            if send_back := state.get("send_back"):
                finish_send_back(emit, send_back, draft)
            return {
                "messages": [RemoveMessage(id=last.id), draft],
                "empty_pending": None,
                "send_back": None,
                "rewrite_of": None,
                "guard": "use_draft",
                "outcome": "used_draft",
            }
        ctx.stats.empty_failed = True
        record_empty(ctx, emit, {**detail, "retried": retried}, {"result": "failed"})
        return {"empty_pending": None, "guard": "ok", "outcome": "empty_failed"}
    chat = ctx.primer is not None and ctx.primer.kind == "chat"
    if (
        answer is not None
        and not chat
        and not state.get("announce_retries")
        and not state.get("send_back")
        and is_announce_only(answer)
    ):
        assert last is not None and last.id is not None
        record_system(
            emit,
            "system-announce-retry",
            "announce_only",
            "予告だけの回答のやり直し",
            "ツールを呼ばずに「これから〜する」と書いただけの回答だったので、ツールを呼ぶよう求めてやり直した",
            input={"answer": answer[:300]},
            output={"note": ANNOUNCE_NOTE},
        )
        return {
            "messages": [RemoveMessage(id=last.id)],
            "announce_retries": 1,
            "announce_pending": {"answer": answer},
            "guard": "retry",
        }
    rewrite_of = state.get("rewrite_of")
    if answer is not None and rewrite_of is not None and draft is not None:
        assert last is not None and last.id is not None
        if reason := discard_reason(rewrite_of, answer):
            record_discarded(ctx, emit, reason, state.get("draft_kind") or "", answer)
            return {
                "messages": [RemoveMessage(id=last.id), draft],
                "rewrite_of": None,
                "guard": "use_draft",
                "outcome": "used_draft",
            }
    # 何もせずに通したことも記録に残す（確認の通過と同じく、見張りが動いたことを追えるように。specs/029 T41）
    ctx.stats.guard_passes += 1
    checks = ["empty", "announce_only"] + (["rewrite_reply"] if rewrite_of is not None else [])
    record_system(
        emit,
        f"system-guard-pass-{ctx.stats.guard_passes}",
        "guard_passed",
        "見張りの通過",
        "空の応答・予告だけの回答"
        + ("・差し戻しへの返事の書き直し" if rewrite_of is not None else "")
        + "のどれでもないので通した",
        input={"checks": checks},
        output={"result": "ok"},
    )
    return {"rewrite_of": None, "guard": "ok", "outcome": "answered"}


async def review(state: FlowState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    """最終回答の下書きを確かめる（specs/026 ④）。

    調べ残し → 表の集計 → 数字の順に、当てはまるものを 1 つ差し戻す。

    差し戻すときは下書きを会話の状態から外して `draft` に置き、依頼の文を `send_back` に置く（調査の次の
    モデル呼び出しにだけ添える）。差し戻したことは「見直し」のステップとして記録に残す。
    """
    ctx, emit = runtime.context, tag_node(runtime.stream_writer, "review")
    msgs = state["messages"]
    last = msgs[-1] if msgs else None
    answer = final_answer(last)
    if answer is None:
        return {"send_back": None}
    turn = msgs[turn_start(msgs) :]
    # 同じモデル呼び出しの続きとして数える（ツールを呼ばずに書き直した差し戻しの回数を足す）
    calls = sum(1 for m in turn if isinstance(m, AIMessage))
    has_tools = calls < ctx.cfg.max_steps
    done = list(state.get("reviews_done") or [])
    used = calls + state.get("chain", 0)
    found = pick_review(ctx, turn, answer, used, has_tools, done)
    if found is None and review_skip(ctx, used, has_tools) is None:
        found = await reason_review(ctx, emit, turn, answer, done)
    if found is None:
        # 理由の差し戻しの後も裏付けが無ければ、回答に注記を添える（確定で足す）
        caveat = await reason_caveat(ctx, emit, turn, answer, done)
        record_review_pass(emit, len(done) + 1, review_skip(ctx, used, has_tools), done)
        return {"send_back": None, "caveat": caveat}
    assert last is not None and last.id is not None
    send_back = open_send_back(ctx, emit, found, answer, searches(ctx, turn))
    return {
        "messages": [RemoveMessage(id=last.id)],
        "draft": last,
        "draft_kind": found.kind,
        "reviews_done": [*done, found.kind],
        "chain": state.get("chain", 0) + 1,
        "send_back": send_back,
    }


def classify(answer: str, ctx: RunContext) -> str | None:
    """回答の無い理由（no_answer_reason）。回答があれば、資料なし・引用なしの分析用の理由か None。"""
    if answer.strip():
        # 調べたのに資料が 1 件も無く、引用も無い回答は「資料なし」として数える（知識ギャップの分析用）
        chat = ctx.primer is not None and ctx.primer.kind == "chat"
        searched = ctx.stats.tool_calls or (ctx.stats.primer_searches and not chat)
        if searched and not cited_numbers(answer):
            if len(ctx.registry) == 0:
                return "no_sources"
            # 資料はあったが引用の無い回答（多くは「見つからなかった」）。引用必須のときだけ数える
            if ctx.cfg.require_citations:
                return "no_relevant_sources"
        return None
    if ctx.stats.tool_errors and len(ctx.registry) == 0:
        return "tool_failed"
    if len(ctx.registry) == 0:
        return "no_sources"
    if ctx.stats.empty_failed:
        # 資料はあったが、モデルが本文の無い応答を返し、やり直しても下書きも無かった（R25。上限ではない）
        return "empty_generation"
    return "step_budget_exhausted"


async def finalize(state: FlowState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    """回答を確定する: 数字の照合の記録・引用の整形と刈り込み・引用の振り直し・回答の分類。

    確定したら runner に渡して保存させ、完了（run.completed）を送らせる。続けて聞く候補はこの後に作る。
    """
    ctx = runtime.context
    # この節点で記録したステップ。完了（保存）は同じ節点の中で行い、ストリームの処理より先に走るので、
    # runner に直接渡して保存に含める（渡さないと再読み込みで数字の照合などが消える）
    recorded: list[dict[str, Any]] = []

    def capture(ev: dict[str, Any]) -> None:
        if ev.get("type") == "step":
            recorded.append(ev["step"])
        runtime.stream_writer(ev)

    emit = tag_node(capture, "finalize")
    msgs = state["messages"]
    last = msgs[-1] if msgs else None
    if state.get("outcome") == "clarify" and isinstance(last, ToolMessage):
        question, options = _ask_user_args(msgs, last)
        return await _finish_clarify(ctx, question, options, "ask_user", capture, recorded)
    if (pre := state.get("clarify")) is not None:
        # 最初の検索の後に、システムが決めた聞き返し（specs/031 R14）
        return await _finish_clarify(ctx, pre["question"], pre["options"], pre["reason"], capture, recorded)
    update: dict[str, Any] = {}
    text = ""
    if isinstance(last, AIMessage) and not last.tool_calls:
        answer = final_answer(last) or ""
        if checks_numbers(ctx):
            record_number_check(ctx, emit, msgs[turn_start(msgs) :], answer)
        fixed = clean_answer(ctx, emit, last)
        if caveat := state.get("caveat"):
            base = fixed or last
            fixed = AIMessage(
                content=f"{base.text.rstrip()}\n\n{caveat}", id=last.id, usage_metadata=last.usage_metadata
            )
            record_system(
                emit,
                "system-reason-caveat",
                "reason_caveat",
                "推測の注記",
                "書き直しても理由の裏付けが無かったので、回答の末尾に推測だと注記した",
                output={"caveat": caveat},
            )
        if fixed is not None:
            update["messages"] = [fixed]
        text = (fixed or last).text
    fin = finalize_citations(text, ctx.registry)
    # 引用した文書名を回答のメッセージに残す。出典番号は保存のときに振り直され、最初の検索の結果は
    # 会話の履歴に残らないので、次のターンで「さっきの資料」を文書名に直せるようにする
    docs = {str(c.document_id): c.document_name for c in fin.items.values() if c.document_name}
    target = update["messages"][0] if update.get("messages") else last
    if docs and isinstance(target, AIMessage) and not target.tool_calls:
        kwargs = {**target.additional_kwargs, "cited_documents": list(dict.fromkeys(docs.values()))}
        kwargs["cited_document_ids"] = list(docs)
        update["messages"] = [target.model_copy(update={"additional_kwargs": kwargs})]
    reason = classify(fin.answer, ctx)
    shown = NO_ANSWER_TEXT[reason] if reason and not fin.answer.strip() else fin.answer
    chat = ctx.primer is not None and ctx.primer.kind == "chat"
    eligible = reason is None and not chat and ctx.hooks.followups is not None
    want = eligible and ctx.cfg.followups
    if eligible and not want:
        # 利用者が設定で切った。作らなかったことも記録に残す（後端の動きは黙って行わない）
        record_system(
            tag_node(capture, "followups"),
            "system-followups",
            "followups",
            "続けて聞く質問の作成",
            "利用者の設定でオフのため作らなかった",
            output={"skipped": "user_setting"},
        )
    if ctx.hooks.completed is not None:
        await ctx.hooks.completed(
            Completion(answer=shown, reason=reason, citations=fin, followups=want, steps=recorded)
        )
    return {**update, "no_answer_reason": reason, "followups": want}


CLARIFY_OPTIONS_MAX = 3


def _ask_user_args(msgs: list[AnyMessage], tool: ToolMessage) -> tuple[str, list[str]]:
    """ask_user の呼び出しの問いと選択肢。"""
    call = next(
        (
            c
            for m in reversed(msgs)
            if isinstance(m, AIMessage)
            for c in m.tool_calls
            if c["id"] == tool.tool_call_id
        ),
        None,
    )
    args = call["args"] if call else {}
    question = str(args.get("question") or tool.text).strip()
    raw = args.get("options") or []
    options = list(dict.fromkeys(str(o).strip() for o in raw if str(o).strip()))[:CLARIFY_OPTIONS_MAX]
    return question, options


CLARIFY_REASONS = {
    "ask_user": "質問の意味を決められないため、モデルが利用者に聞き返した",
    "document_unspecified": "「この資料」がどの文書か決まらないため、検索で見つかった文書から選んでもらう",
    "reference_unknown": "初めのターンの「この件」「それ」は指す先が無いため、対象を添えて聞き直してもらう",
}


async def _finish_clarify(
    ctx: RunContext,
    question: str,
    options: list[str],
    reason: str,
    capture: Any,
    recorded: list[dict[str, Any]],
) -> dict[str, Any]:
    """聞き返しを回答として確定する。問いを回答に、選択肢を候補にする（続けて聞く候補は作らない）。

    会話の状態には問いを AIMessage（clarify の印付き）として足す。次のターンの質問の理解が問いと
    選択肢を履歴として読み、続けての聞き返しを止めるのに使う。
    """
    record_system(
        tag_node(capture, "finalize"),
        "system-clarify",
        "clarify",
        "聞き返しで終える",
        f"{CLARIFY_REASONS.get(reason, reason)}（選択肢 {len(options)} 個）",
        input={"question": question, "reason": reason},
        output={"options": options},
    )
    answer = AIMessage(content=question, additional_kwargs={"clarify": True, "options": options})
    if ctx.hooks.completed is not None:
        await ctx.hooks.completed(
            Completion(
                answer=question,
                reason=None,
                citations=finalize_citations("", ctx.registry),
                followups=False,
                steps=recorded,
                suggestions=options,
            )
        )
    return {"messages": [answer], "no_answer_reason": None, "followups": False}


async def followups(state: FlowState, runtime: Runtime[RunContext]) -> dict[str, Any] | None:
    """完了の後に、続けて聞く質問の候補を作って届ける（specs/028 R7・T24）。"""
    hook = runtime.context.hooks.followups
    if hook is None:
        return None
    return {"suggestions": await hook()}


# ── 辺（状態だけを見る純関数） ──


def route_after_understand(state: FlowState) -> Literal["chat", "docs"]:
    """雑談は最初の検索を飛ばして調査へ。"""
    u = state.get("understanding")
    return "chat" if u and u.get("kind") == "chat" else "docs"


def route_after_primer(state: FlowState) -> Literal["investigate", "clarify"]:
    """どの文書か決まらない「この資料」は、調べずに聞き返す（確定へ）。"""
    return "clarify" if state.get("clarify") else "investigate"


def route_after_guard(state: FlowState) -> Literal["retry", "use_draft", "ok"]:
    """やり直し（調査へ戻る）・下書きへの退避か聞き返し（確認を通さず確定へ）・通過（確認へ）。"""
    g = state.get("guard")
    if g == "retry":
        return "retry"
    return "use_draft" if g in ("use_draft", "clarify") else "ok"


def route_after_review(state: FlowState) -> Literal["send_back", "pass"]:
    """差し戻し（調査へ戻る）か、通過（確定へ）。"""
    return "send_back" if state.get("send_back") else "pass"


def route_after_finalize(state: FlowState) -> Literal["followups", "end"]:
    return "followups" if state.get("followups") else "end"


# ── 組み立て ──


def build_investigate(
    model: BaseChatModel,
    *,
    utility: BaseChatModel | None = None,
    fallback: BaseChatModel | None = None,
    model_label: str = "会話モデル",
    fallback_label: str = "代替モデル",
    summarize_at_tokens: int = 12_000,
) -> Any:
    """調査の部分グラフ（create_agent。checkpointer は外側のものを使う）。"""
    middleware: list[Any] = [
        RecordedSummarization(
            utility or model, trigger=("tokens", summarize_at_tokens), keep=("messages", 12)
        ),
        AgentPolicyMiddleware(),
    ]
    # 代替が無くても入れる（失敗の理由と、いまのモデル名を「考えた過程」に出すため）
    fallbacks = [] if fallback is None else [(fallback_label, fallback)]
    middleware += [ModelSwitchMiddleware(model_label, fallbacks), StepMiddleware()]
    return create_agent(
        model, tools=TOOLS, middleware=middleware, context_schema=RunContext, name="investigate"
    )


def build_graph(investigate: Any, *, checkpointer: BaseCheckpointSaver[Any] | None = None) -> Any:
    g = StateGraph(FlowState, context_schema=RunContext)
    g.add_node("read_image", read_image)
    g.add_node("understand", cast(Any, understand_node))
    g.add_node("primer_search", cast(Any, primer_search_node))
    g.add_node("investigate", investigate)
    g.add_node("guard", guard)
    g.add_node("review", review)
    g.add_node("finalize", finalize)
    g.add_node("followups", followups)
    g.add_edge(START, "read_image")
    g.add_edge("read_image", "understand")
    g.add_conditional_edges(
        "understand", route_after_understand, {"chat": "investigate", "docs": "primer_search"}
    )
    g.add_conditional_edges(
        "primer_search", route_after_primer, {"investigate": "investigate", "clarify": "finalize"}
    )
    g.add_edge("investigate", "guard")
    g.add_conditional_edges(
        "guard",
        route_after_guard,
        {"retry": "investigate", "use_draft": "finalize", "ok": "review"},
    )
    g.add_conditional_edges("review", route_after_review, {"send_back": "investigate", "pass": "finalize"})
    g.add_conditional_edges("finalize", route_after_finalize, {"followups": "followups", "end": END})
    g.add_edge("followups", END)
    return g.compile(checkpointer=checkpointer)
