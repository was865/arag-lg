"""ターンの最初にシステムが行う整理と検索（specs/026 ①②）。

モデルが検索するかどうかに任せず、質問（と整理したクエリ）で必ず検索し、結果を RunContext に置く。
回答の流れの節点 `understand`・`primer_search`（specs/029）。
結果を質問に添えるのは AgentPolicyMiddleware（会話の状態は変えない）。
"""

import asyncio
import difflib
import re
import unicodedata
from typing import Any

from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.runtime import Runtime

from arag.agent.context import Emit, Primer, RunContext
from arag.agent.ops import find_named_documents, op_search, read_document, weak_result
from arag.agent.prior import last_cited_scope
from arag.agent.steps import Step, StepClock, record_system, tag_node
from arag.agent.understand import MAX_QUERIES, Understanding, understand
from arag.logging import get_logger

_BLOCK = re.compile(r'<資料 n="(\d+)".*?</資料>', re.DOTALL)
PRIMER_OPEN = "<検索結果>"
PRIMER_CLOSE = "</検索結果>"
# 検索結果の後ろに付ける締めの 1 行（R22）。資料が日本語ばかりだと英語の質問にも日本語で答えがち（hm60）
PRIMER_LANGUAGE = "資料の言語にかかわらず、上の質問と同じ言語で答える。"
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
    return f"{question}\n\n{PRIMER_OPEN}\n{PRIMER_HEAD}\n\n{primer.text}\n{PRIMER_CLOSE}\n{PRIMER_LANGUAGE}"


# なぜこの検索をするのか（質問文での検索と、整理したクエリでの検索は、狙いが違う）
log = get_logger("arag.agent.primer")

ROLES = {
    "question": ("質問文で検索", "質問の言葉そのままで探す（整理を待たずに始める）"),
    "named": ("指定の文書を読む", "質問に書かれた文書名の文書を、検索せずに読む"),
    "understood": (
        "整理したクエリで検索",
        "補助モデルが言い換え・分けたクエリで探す（言葉の違いによる取りこぼしを減らす）",
    ),
}


async def _read_scoped(
    ctx: RunContext, emit: Emit, sid: str, scope: tuple[list[str], list[str]]
) -> str | None:
    """絞った文書が 1 つで、上限に収まるなら、検索せずに文書を読む。長いときは None（検索に任せる）。"""
    clock = StepClock(
        emit,
        Step(
            id=f"{sid}:read",
            name="read_document",
            parent_id=sid,
            label="文書を読む",
            status="running",
            input={"document": scope[1][0], "document_id": scope[0][0]},
            summary="文書を読んでいます",
        ),
    )
    try:
        got = await read_document(ctx, scope[0][0])
    except Exception as e:  # 読めなくても、検索で続ける
        clock.done(f"読めなかった（{type(e).__name__}）。検索で絞る", {"error": str(e)[:200]}, error=True)
        return None
    if isinstance(got, str):
        clock.done(got[:120], error=True)
        return None
    if got.truncated:
        clock.done(f"長いため全部は読めない（先頭 {got.sections} 節）。検索で絞る", {"truncated": True})
        return None
    clock.done(f"{got.sections} 節を読んだ", {"result": got.text[:2000], "sections": got.sections})
    return got.text


async def _read_named(ctx: RunContext, emit: Emit, index: int, doc: tuple[str, str], question: str) -> str:
    """質問に名前が書かれた文書を、検索せずに読む。長くて読み切れないときは、その文書の中を質問で探す。"""
    sid = f"primer-{index}"
    label, purpose = ROLES["named"]
    clock = StepClock(
        emit,
        Step(
            id=sid,
            name="search",
            label=label,
            status="running",
            input={
                "query": question[:300],
                "by": "system",
                "role": "named",
                "purpose": f"{purpose}: 「{doc[1]}」",
                "scope_documents": [doc[1]],
            },
            summary="読んでいます",
        ),
    )
    ctx.stats.primer_searches += 1
    try:
        text = await _read_scoped(ctx, emit, sid, ([doc[0]], [doc[1]]))
        how = "直接読んだ"
        if text is None:
            text = await op_search(ctx, emit, sid, question, document_ids=[doc[0]])
            how = "長いため文書の中を検索した"
    except Exception as e:
        ctx.stats.tool_errors += 1
        clock.done("失敗しました", {"error": str(e)[:300]}, error=True)
        return f"文書「{doc[1]}」を読めませんでした（{type(e).__name__}）。"
    n = len(_BLOCK.findall(text))
    clock.done(f"「{doc[1]}」を{how}・資料 {n} 件", {"result": text[:2000]})
    return text


async def _search(
    ctx: RunContext,
    emit: Emit,
    index: int,
    query: str,
    role: str,
    scope: tuple[list[str], list[str]] | None = None,
) -> str:
    """scope は（文書 ID, 文書名）。「さっきの資料」のとき、前のターンで引用した文書に絞る。"""
    sid = f"primer-{index}"
    label, purpose = ROLES[role]
    if scope and scope[0]:
        purpose += "。前のターンで引用した文書に絞る: " + "・".join(f"「{n}」" for n in scope[1])
    clock = StepClock(
        emit,
        Step(
            id=sid,
            name="search",
            label=label,
            status="running",
            input={"query": query, "by": "system", "role": role, "purpose": purpose}
            | ({"scope_documents": scope[1]} if scope and scope[0] else {}),
            summary="検索中",
        ),
    )
    ctx.stats.primer_searches += 1
    how = "search"
    try:
        if scope and scope[0]:
            read = await _read_scoped(ctx, emit, sid, scope) if len(scope[0]) == 1 else None
            if read is not None:
                text, how = read, "read"
            else:
                text = await op_search(ctx, emit, sid, query, document_ids=scope[0])
            if how != "read" and weak_result(text):
                # 絞った範囲に答えが無いときは、範囲を外して探し直す（記録に残る）
                text = await op_search(
                    ctx, emit, sid, query, step_tag="all", label="範囲を外して再検索", running="再検索中"
                )
        else:
            text = await op_search(ctx, emit, sid, query)
    except Exception as e:
        ctx.stats.tool_errors += 1
        clock.done("失敗しました", {"error": str(e)[:300]}, error=True)
        return f"検索「{query}」は失敗しました（{type(e).__name__}）。"
    n = len(_BLOCK.findall(text))
    base = distinct_part(query, ctx.question) if role == "understood" else query
    shown = base if len(base) <= 28 else base[:27] + "…"
    if how == "read":
        # 検索ではなく読んだので、行の名前と狙いもそれに合わせる
        doc = scope[1][0] if scope else ""
        clock.step = clock.step.model_copy(
            update={
                "label": "指定の文書を読む",
                "input": {
                    **clock.step.input,
                    "purpose": f"前のターンで引用した文書「{doc}」を、検索せずに読む",
                },
            }
        )
    found = f"資料 {n} 件" if n else "資料なし"
    summary = f"文書を直接読んだ・{found}" if how == "read" else f"「{shown}」・{found}"
    clock.done(summary, {"result": text[:2000]})
    return text


# 整理したクエリが質問文とほぼ同じなら、同じ資料が返るだけなので検索しない（記録には残す）
SIMILAR_RATIO = 0.85
_PUNCT = re.compile(r"[\s\W_]+")


def similarity(a: str, b: str) -> float:
    def norm(x: str) -> str:
        return _PUNCT.sub("", unicodedata.normalize("NFKC", x)).casefold()

    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def distinct_part(query: str, question: str) -> str:
    """質問文と先頭が同じなら、違い始める所から見せる（行の要約で 2 つの検索の差が見えるように）。"""
    n = 0
    while n < min(len(query), len(question)) and query[n] == question[n]:
        n += 1
    return query if n < 8 else "…" + query[max(0, n - 2) :]


def _describe(u: Understanding) -> str:
    if u.error:
        return f"整理できなかったため、質問文のまま検索する（{u.error}）"
    if u.kind == "chat":
        return "文書を調べる質問ではないと判断"
    head = "・".join(f"「{q}」" for q in u.queries)
    return f"{head} で検索" + ("（表の集計あり）" if u.table else "")


def _drop_similar(emit: Emit, question: str, queries: list[str]) -> list[str]:
    kept: list[str] = []
    dropped: list[tuple[str, float]] = []
    for q in queries:
        r = similarity(q, question)
        if r >= SIMILAR_RATIO:
            dropped.append((q, r))
        else:
            kept.append(q)
    if dropped:
        record_system(
            emit,
            "system-query-skipped",
            "query_skipped",
            "近いクエリの省略",
            f"質問文とほぼ同じ（{max(r for _, r in dropped):.2f}）なので、{len(dropped)} 件は検索しない",
            input={"question": question[:300], "threshold": SIMILAR_RATIO},
            output={
                "skipped_queries": [q for q, _ in dropped],
                "similarity": [round(r, 2) for _, r in dropped],
            },
        )
    return kept


def strip_documents(query: str, names: list[str]) -> str:
    """絞った文書の名前（拡張子つき・なし）をクエリから外す。絞ってあるので、文書名は検索語として余る。"""
    out = query
    for n in names:
        for form in (n, n.rsplit(".", 1)[0]):
            out = out.replace(form, " ")
    out = " ".join(out.split())
    # 助詞しか残らないとき（「A.docx と B.docx の違い」→「と の違い」）は、元のクエリのままにする
    left = re.sub(r"[\sとのをはがにでも・、,]+", "", out)
    return out if len(left) >= 3 else query


def _last_question(msgs: list[AnyMessage]) -> int | None:
    return next((i for i in range(len(msgs) - 1, -1, -1) if isinstance(msgs[i], HumanMessage)), None)


async def understand_node(state: dict[str, Any], runtime: Runtime[RunContext]) -> dict[str, Any]:
    """質問の理解。補助モデルで種類・検索クエリ・表の集計の要否を得る。

    初回のターンは、質問文そのものでの検索を理解と並行に行う（待ち時間を増やさない）。
    """
    ctx, emit = runtime.context, tag_node(runtime.stream_writer, "understand")
    ctx.primer, ctx.primer_texts = None, []
    msgs: list[AnyMessage] = list(state["messages"])
    last = _last_question(msgs)
    if last is None:
        return {"understanding": None}
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
            {
                "kind": u.kind,
                "queries": list(u.queries),
                "table": u.table,
                "refers_prior": u.refers_prior,
                "raw": u.raw[:1000],
            }
            | ({"error": u.error} if u.error else {})
            | ({"table_overridden": True} if u.table_overridden else {})
            | ({"refers_overridden": True} if u.refers_overridden else {}),
        )

    if first_turn:
        # 質問文での検索は整理を待たずに始める（待ち時間を増やさない）
        u, text = await asyncio.gather(
            understand(ctx.utility_model, history, question), _search(ctx, emit, 1, question, "question")
        )
        finish(u)
        ctx.primer_texts = [text]
        extra = [q for q in u.queries if q != question]
        extra = _drop_similar(emit, question, extra)[: MAX_QUERIES - 1]
        start = 2
    else:
        # 追質問は指示語を含むので、整理したクエリで検索する
        u = await understand(ctx.utility_model, history, question)
        finish(u)
        extra = list(u.queries)
        start = 1
    if u.kind == "chat":
        ctx.primer = Primer(kind="chat")
    scope: tuple[list[str], list[str]] = ([], [])
    plain: list[
        str
    ] = []  # 絞ったとき、絞らずに探す元のクエリ（「新版と比べて」のように他の文書も要るとき用）
    if u.refers_prior and not first_turn and u.kind == "docs":
        scope = last_cited_scope(history)
        if scope[0]:
            record_system(
                emit,
                "system-scope-prior",
                "scope_prior",
                "前の文書に絞る",
                f"「さっきの資料」とみなし、前のターンで引用した文書 {len(scope[0])} 件に絞って検索する",
                input={"question": question[:300]},
                output={"documents": scope[1]},
            )
            plain = list(extra)
            extra = [strip_documents(q, scope[1]) for q in extra]
    understanding = {
        "kind": u.kind,
        "queries": list(u.queries),
        "table": u.table,
        "extra": extra,
        "start": start,
        "scope": {"ids": scope[0], "names": scope[1]},
        "plain": plain,
        "question": question[:2000],
    }
    return {"understanding": understanding}


async def primer_search_node(state: dict[str, Any], runtime: Runtime[RunContext]) -> dict[str, Any] | None:
    """最初の検索。整理したクエリ（初回は質問文での検索に足りない分）で検索し、結果を質問に添える用意をする。"""
    ctx, emit = runtime.context, tag_node(runtime.stream_writer, "primer_search")
    u = state.get("understanding")
    if not u:
        return None
    texts = list(ctx.primer_texts)
    if extra := u["extra"]:
        start = u["start"]
        scope = (u["scope"]["ids"], u["scope"]["names"])
        jobs = [_search(ctx, emit, start + i, q, "understood", scope) for i, q in enumerate(extra)]
        # 絞ったときも、絞らない普通の検索を足す。「この資料と新版の違い」のように、前の文書だけでは足りない
        jobs += [
            _search(ctx, emit, start + len(extra) + i, q, "understood")
            for i, q in enumerate(u.get("plain") or [])
        ]
        texts += await asyncio.gather(*jobs)
    # 質問に文書名が書かれているときは、検索に頼らず、その文書を確実に読む
    named: list[tuple[str, str]] = []
    if u["kind"] == "docs":
        try:
            named = await find_named_documents(ctx, u.get("question", ""))
        except Exception as e:  # 文書名で決められなくても、検索で続ける
            log.warning("named_documents_failed", error=str(e)[:200])
    if named:
        base = u["start"] + len(u["extra"]) * 2 + 1
        texts = [
            await _read_named(ctx, emit, base + i, d, u["question"]) for i, d in enumerate(named)
        ] + texts
    ctx.primer_texts = texts
    ctx.primer = Primer(
        kind=u["kind"],
        table=u["table"],
        queries=tuple(u["queries"]),
        text=merge_results(texts),
        weak=bool(texts) and all(weak_result(t) for t in texts),
    )
    return None
