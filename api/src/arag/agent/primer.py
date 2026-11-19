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

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.runtime import Runtime

from arag.agent.context import Emit, Primer, RunContext
from arag.agent.mcp_tools import asks_current, current_note
from arag.agent.ops import (
    TOC_SECTION_ID,
    find_named_documents,
    op_get_outline,
    op_read_section,
    op_search,
    read_document,
    recent_documents,
    weak_result,
)
from arag.agent.prior import cited_documents, last_cited_scope
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
    tail = f"\n{primer.note}" if primer.note else ""
    body = f"{PRIMER_OPEN}\n{PRIMER_HEAD}\n\n{primer.text}\n{PRIMER_CLOSE}"
    return f"{question}\n\n{body}\n{PRIMER_LANGUAGE}{tail}"


# なぜこの検索をするのか（質問文での検索と、整理したクエリでの検索は、狙いが違う）
log = get_logger("arag.agent.primer")

ROLES = {
    "question": ("質問文で検索", "質問の言葉そのままで探す（整理を待たずに始める）"),
    "named": ("指定の文書を読む", "質問に書かれた文書名の文書を、検索せずに読む"),
    "structure": (
        "文書の構成を読む",
        "構成（目次・最後の章など）を問う質問なので、前のターンの文書の章立てと目次の節を添える",
    ),
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
            found = await op_search(ctx, emit, sid, question, document_ids=[doc[0]])
            # 検索では「最後の章」「目次」のような位置・構成の問いに答えられないので、章立ての先頭と末尾も
            # 添える（specs/031 R11）
            outline = await _outline_for(ctx, emit, sid, doc, question)
            text = f"{outline}\n\n{found}" if outline else found
            how = "長いため章立てを添えて文書の中を検索した" if outline else "長いため文書の中を検索した"
    except Exception as e:
        ctx.stats.tool_errors += 1
        clock.done("失敗しました", {"error": str(e)[:300]}, error=True)
        return f"文書「{doc[1]}」を読めませんでした（{type(e).__name__}）。"
    n = len(_BLOCK.findall(text))
    clock.done(f"「{doc[1]}」を{how}・資料 {n} 件", {"result": text[:2000]})
    return text


# 長い文書に添える章立ての節の数（先頭・末尾）。全部は文脈を圧迫するので、続きは get_outline の start で
PRIMER_OUTLINE_HEAD = 20
PRIMER_OUTLINE_TAIL = 20


_CHAPTER_NO = re.compile(r"第\s*(\d{1,2})\s*章")


async def _outline_for(
    ctx: RunContext, emit: Emit, sid: str, doc: tuple[str, str], question: str = ""
) -> str:
    """名前を書かれた長い文書の章立て（先頭と末尾）。取れなければ空。記録には子のステップで残す。"""
    # 質問が章を指すなら（「第2章の最後の節」）、その章の節も全部添える（T20）
    m = _CHAPTER_NO.search(question)
    chapter = int(m.group(1)) if m else None
    clock = StepClock(
        emit,
        Step(
            id=f"{sid}:outline",
            name="get_outline",
            parent_id=sid,
            label="目次を取得",
            status="running",
            input={"document": doc[1], "head": PRIMER_OUTLINE_HEAD, "tail": PRIMER_OUTLINE_TAIL}
            | ({"chapter": chapter} if chapter is not None else {}),
            summary="章立てを取得しています",
        ),
    )
    try:
        text = await op_get_outline(
            ctx, doc[0], head=PRIMER_OUTLINE_HEAD, tail=PRIMER_OUTLINE_TAIL, chapter=chapter
        )
    except Exception as e:  # 章立てが無くても検索の結果で続ける
        clock.done(f"取得できなかった（{type(e).__name__}）", {"error": str(e)[:200]}, error=True)
        return ""
    toc = ""
    if m := TOC_SECTION_ID.search(text):
        # 文書の中の目次の節は短く、章の全体（最後の章・付録まで）が分かるので、本文も添える（引用できる）
        try:
            toc = await op_read_section(ctx, m.group(1))
        except Exception as e:
            log.warning("toc_read_failed", error=str(e)[:200])
    clock.done(
        "章立ての先頭と末尾" + ("と目次の節" if toc else "") + "を添えた",
        {"result": text[:4000]} | ({"toc": toc[:2000]} if toc else {}),
    )
    out = f"<章立て>\n{text}\n</章立て>"
    return f"{out}\n\n{toc}" if toc else out


# 構成を問う質問への注意（specs/031 T16）。検索結果（資料）の中でなく、その外に指示として添える
STRUCTURE_NOTE = (
    "章の見出しは、資料の目次の節・章立てに書かれたとおりに書き、資料に無い見出しを作らない。"
    "足りなければ get_outline や read_section で確かめる。"
)
# 「最後の章」「最初の章」は 2 通りに取れ、両方を短く答えられる（R6）
EDGE_CHAPTER_NOTE = (
    "「最後の章」「最初の章」は 2 通りに取れる。番号の付いた最後（最初）の章（第N章）と、文書の末尾（先頭）に"
    "ある付録・補遺・入門などを分けて、両方を答える。"
)
_EDGE_CHAPTER = re.compile(
    r"(最後|最初|最終|末尾|はじめ|初め)の?章|最終章|\b(last|first|final)\s+chapter", re.I
)


def structure_note(question: str) -> str:
    """構成を問う質問に添える注意。構成を問わなければ空（T16）。"""
    if not structure_question(question):
        return ""
    return STRUCTURE_NOTE + (EDGE_CHAPTER_NOTE if _EDGE_CHAPTER.search(question) else "")


# 文書の構成を問う質問（目次・最後の章・付録・第N章など。specs/031 T15）
_STRUCTURE = re.compile(
    r"目\s*次|最後の章|最初の章|最終章|章立て|構成|付録|補遺|第\s*\d+\s*章|何章|章の(?:一覧|内容|数)|"
    r"table of contents|\bchapters?\b|\bappendix\b",
    re.IGNORECASE,
)


def structure_question(question: str) -> bool:
    """文書の構成（目次・章）を問う質問か。検索では目次の節が上がりにくいので章立てを添える（T15）。"""
    return bool(_STRUCTURE.search(question))


async def _read_structure(
    ctx: RunContext, emit: Emit, index: int, doc: tuple[str, str], question: str = ""
) -> str:
    """構成を問う続けての質問に、前のターンの文書の章立てと目次の節を添える（specs/031 T15）。"""
    sid = f"primer-{index}"
    label, purpose = ROLES["structure"]
    clock = StepClock(
        emit,
        Step(
            id=sid,
            name="search",
            label=label,
            status="running",
            input={
                "query": doc[1],
                "by": "system",
                "role": "structure",
                "purpose": f"{purpose}: 「{doc[1]}」",
                "scope_documents": [doc[1]],
            },
            summary="章立てを読んでいます",
        ),
    )
    ctx.stats.primer_searches += 1
    text = await _outline_for(ctx, emit, sid, doc, question)
    if not text:
        clock.done("章立てを取得できなかった", {"result": ""})
        return ""
    clock.done(f"「{doc[1]}」の章立てと目次を添えた", {"result": text[:2000]})
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
    question = u.get("question", "")
    history = state["messages"][: _last_question(state["messages"]) or 0]
    if not named and u["kind"] == "docs" and structure_question(question):
        # 構成を問う続けての質問（「目次を教えて」）: 検索では目次の節が上がりにくい。前のターンで
        # 引用した文書が 1 つなら、その章立てと目次の節を添える（specs/031 T15）
        ids, names = (
            (u["scope"]["ids"], u["scope"]["names"]) if u["scope"]["ids"] else last_cited_scope(history)
        )
        if len(ids) == 1:
            base = u["start"] + len(u["extra"]) * 2 + 1
            if text := await _read_structure(ctx, emit, base, (ids[0], names[0]), question):
                texts = [text, *texts]
    ctx.primer_texts = texts
    ctx.primer = Primer(
        kind=u["kind"],
        table=u["table"],
        queries=tuple(u["queries"]),
        text=merge_results(texts),
        weak=bool(texts) and all(weak_result(t) for t in texts),
        note=(note := structure_note(question)) if u["kind"] == "docs" else "",
    )
    if ctx.primer.note:
        record_system(
            emit,
            "system-structure-note",
            "structure_note",
            "構成の質問への注意",
            "文書の構成を問う質問なので、章の見出しを資料のとおりに書くよう添えた"
            + ("（「最後の章」は番号の付いた章と付録の両方を答える）" if EDGE_CHAPTER_NOTE in note else ""),
            input={"asked": question[:300]},
            output={"note": note},
        )
    if u["kind"] == "docs" and ctx.mcp is not None and ctx.mcp.usable and asks_current(question):
        # 今の値を問う質問: 台帳はある時点の値なので、社内システムで確かめるよう添える（specs/032 R15）
        note = current_note(ctx.mcp.down)
        ctx.primer.note = f"{ctx.primer.note}\n{note}".strip()
        record_system(
            emit,
            "system-current-note",
            "current_note",
            "今の値の質問への注意",
            "今の値・進み具合か社内システムにある記録を問う質問なので、社内システムで確かめるよう添えた",
            input={"asked": question[:300], "systems": ctx.mcp.systems, "down": ctx.mcp.down},
            output={"note": note},
        )
    attached = ctx.document_ids is not None or ctx.hooks.read_image is not None
    if u["kind"] == "docs" and not named and not attached and (term := reference_unknown(question, history)):
        # 検索の結果は指す先の手がかりにならないので、選択肢は出さず対象を添えて聞き直してもらう
        return {
            "clarify": {
                "question": CLARIFY_REFERENCE.format(term=term),
                "options": [],
                "reason": "reference_unknown",
            }
        }
    if u["kind"] == "docs" and not named and document_unspecified(ctx, question, history):
        try:
            recent = await recent_documents(ctx)
        except Exception as e:  # 最近の文書が取れなくても、検索で見つかった文書で聞き返す
            log.warning("recent_documents_failed", error=str(e)[:200])
            recent = []
        options = clarify_options(ctx, question, recent)
        if len(options) >= 2:
            return {
                "clarify": {
                    "question": CLARIFY_DOCUMENT,
                    "options": options,
                    "reason": "document_unspecified",
                }
            }
    return None


# 「この資料」「その文書」のように、文書そのものを指す言い方（文書の種類の語「手順書」などは含めない）。
# 添付・本資料・この表・このスライドも、何も添えていなければ指す先が無い（specs/031 T14）
_THIS_DOC = re.compile(
    r"(この|その|あの|上の|上記の|さっきの|先ほどの|先程の)\s*"
    r"(資料|文書|ドキュメント|ファイル|書類|PDF|表(?!計算)|図(?!面)|スライド|シート)|"
    r"添付(?:の|した|された)?\s*(?:資料|文書|ドキュメント|ファイル|書類|PDF)|本資料|当資料|本文書|"
    r"\b(this|that|the\s+attached|attached)\s+(document|file|pdf|spreadsheet|sheet|slides?|deck|table)\b",
    re.IGNORECASE,
)
CLARIFY_DOCUMENT = "どの資料についてですか？候補から選ぶか、文書名を書いてもう一度質問してください。"

# 初めのターンの「この件」「それは」: 会話に前が無いので指す先が無い（specs/031 T14）
_REF = re.compile(r"(?:この|その|あの|例の|本)件|^\s*(?:それ|あれ|これ)(?:は|が|を|って|について|に関して)")
CLARIFY_REFERENCE = (
    "「{term}」が何を指すか分かりませんでした。"
    "対象（文書名・設備名・件名など）を添えて、もう一度質問してください。"
)


def reference_unknown(question: str, history: list[AnyMessage]) -> str | None:
    """会話に前のターンが無いのに「この件」「それは」と指していれば、その語を返す（specs/031 T14）。"""
    if any(isinstance(m, (HumanMessage, AIMessage)) for m in history):
        return None
    m = _REF.search(question)
    return re.sub(r"(は|が|を|って|について|に関して)$", "", m.group(0).strip()) if m else None


CLARIFY_OPTIONS_MAX = 3


def document_unspecified(ctx: RunContext, question: str, history: list[AnyMessage]) -> bool:
    """「この資料」が指す文書が決まらないか（specs/031 R14）。

    添付・範囲で文書が絞られている・画像がある・前のターンで資料を引用した・前のターンが聞き返し、の
    どれかなら、指す先は決まっている（または続けて聞き返さない）とみなす。
    """
    if not _THIS_DOC.search(question):
        return False
    if ctx.document_ids is not None or ctx.hooks.read_image is not None:
        return False
    last = next((m for m in reversed(history) if isinstance(m, AIMessage) and not m.tool_calls), None)
    if last is not None and last.additional_kwargs.get("clarify"):
        return False
    return not cited_documents(history)


# 選択肢に入れる文書の、最も関連の高い文書に対するスコアの比（低いものは偶然に近い一致）
CLARIFY_SCORE_RATIO = 0.5

# 「この資料の〜」で、どの文書にも当てはまる語（要点・まとめなど）。これだけなら内容の語は無い
_GENERIC_TERMS = {
    "資料",
    "文書",
    "要点",
    "要約",
    "概要",
    "内容",
    "結論",
    "目次",
    "説明",
    "一覧",
    "全体",
    "以下",
    "箇条",
    "ポイント",
    "サマリ",
    "サマリー",
    "簡単",
    "詳細",
    "詳しく",
    "summary",
    "summarize",
    "summarise",
    "points",
    "overview",
    "document",
    "file",
    "pdf",
    "this",
    "that",
    "what",
    "about",
    "the",
    "key",
    "main",
    "give",
    "please",
    "explain",
    "list",
    "tell",
    "is",
    "of",
    "in",
    "me",
}
# 漢字・カタカナの 2 文字以上の連なり、英字で始まる語（型番 HP-300 も含む）
_TERM = re.compile(r"[一-龥々ァ-ヶー]{2,}|[A-Za-z][A-Za-z0-9-]+")


def has_content_terms(question: str) -> bool:
    """質問に、文書を絞る内容の語（締付トルク・HP-300 など）があるか。要点・まとめだけなら無い。"""
    body = _THIS_DOC.sub(" ", question)
    return any(t.lower() not in _GENERIC_TERMS for t in _TERM.findall(body))


def clarify_options(ctx: RunContext, question: str, recent: list[str] | None = None) -> list[str]:
    """「この資料」の候補ごとに、その文書名を添えた質問を選択肢にする。

    候補は、利用者が最近登録した文書（2 つまで）、続けて最初の検索で見つかった文書のうち関連の高いもの
    （文書ごとの最高スコアが、いちばん高い文書の半分以上）を高い順に。

    質問に内容の語（締付トルクなど）があるときは、検索の順が当てになるので、最近の文書は検索でも関連の
    高いものだけを先に置く（関係の無い文書を候補にしない。specs/031 T13）。
    """
    best: dict[str, float] = {}
    for c in ctx.registry.items():
        if c.document_name:
            best[c.document_name] = max(best.get(c.document_name, 0.0), c.score or 0.0)
    top = max(best.values(), default=0.0)
    found = [n for n, sc in sorted(best.items(), key=lambda x: -x[1]) if sc >= top * CLARIFY_SCORE_RATIO]
    # 「この資料」は、利用者が登録したばかりの文書を指すことが多い。内容の語が無い質問では検索の順は
    # 当てにならないので、最近の文書を先に置く
    first = (recent or [])[:2]
    if has_content_terms(question):
        first = [n for n in first if n in found]
    names = list(dict.fromkeys([*first, *found]))
    # 関連の高い文書が 1 つだけでも、指す先は決まっていない。次に高い文書で 2 つにする（T14）
    for n, _ in sorted(best.items(), key=lambda x: -x[1]):
        if len(names) >= 2:
            break
        if n not in names:
            names.append(n)
    body = _THIS_DOC.sub("この資料", question).strip()
    return [f"{n} {body}" for n in names[:CLARIFY_OPTIONS_MAX]]
