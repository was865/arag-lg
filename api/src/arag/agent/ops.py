"""ツールの中身（specs/005-agent R14〜R17）。@tool の包みは tools.py。

どの関数も利用者の閲覧範囲と run の検索範囲（RunContext）の中だけを見る。
"""

import re
import time
import uuid
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arag.agent.citations import format_material
from arag.agent.context import Emit, RunContext
from arag.agent.steps import Step, StepClock
from arag.db.models import Content, Document, Section
from arag.logging import get_logger
from arag.prompts import load_prompt
from arag.search.schemas import SearchHit, SearchRequest, SearchResult
from arag.search.scope import Scope, resolve_scope

log = get_logger("arag.agent.ops")

LIST_MAX = 50
OUTLINE_MAX = 200
SECTION_MAX_CHARS = 6000
_UUID = re.compile(r"[0-9a-fA-F-]{32,36}")


def _uuids(values: list[str] | None) -> list[uuid.UUID]:
    out: list[uuid.UUID] = []
    for v in values or []:
        try:
            out.append(uuid.UUID(str(v).strip()))
        except ValueError:
            continue
    return out


def _ref_number(ref: str) -> int | None:
    m = re.fullmatch(r"\s*\[?\s*(\d{1,4})\s*\]?\s*", ref)
    return int(m.group(1)) if m else None


async def _scope(session: AsyncSession, ctx: RunContext) -> Scope:
    req = SearchRequest(
        query="範囲",
        kb_ids=ctx.kb_ids,
        document_ids=ctx.document_ids,
        include_archived=ctx.include_archived,
        top_k=1,
        candidate_k=1,
    )
    return await resolve_scope(session, ctx.principal, req)


def _doc_ids_for_search(ctx: RunContext, refs: list[str] | None) -> list[uuid.UUID] | None:
    """モデルが指定した文書（ID または出典番号）を run の範囲と重ねる。"""
    if not refs:
        return ctx.document_ids
    ids: list[uuid.UUID] = []
    for r in refs:
        n = _ref_number(r)
        c = ctx.registry.get(n) if n is not None else None
        if c is not None:
            ids.append(c.document_id)
        else:
            ids.extend(_uuids([r]))
    if ctx.document_ids is not None:
        allowed = set(ctx.document_ids)
        ids = [i for i in ids if i in allowed]
    return ids


def _render_hits(ctx: RunContext, query: str, hits: list[SearchHit]) -> str:
    if not hits:
        return (
            f"検索「{query}」に一致する資料は見つかりませんでした。"
            "別の言い方・正式名称・型番や条項番号で検索するか、list_documents で文書を確かめてください。"
        )
    parts = [f"検索「{query}」の結果 {len(hits)} 件（[n] が出典番号）:"]
    for h in hits:
        n = ctx.registry.add_hit(h)
        c = ctx.registry.get(n)
        assert c is not None
        parts.append(format_material(n, c))
    return "\n\n".join(parts)


async def _run_search(ctx: RunContext, req: SearchRequest) -> SearchResult:
    async with ctx.sessionmaker() as s:
        return await ctx.search(s, ctx.principal, req)


def _hits_output(res: SearchResult) -> dict[str, Any]:
    return {
        "hits": [
            {"title": h.document_name, "heading": h.heading_path, "score": round(h.score, 3)}
            for h in res.hits
        ],
        "degraded": res.degraded,
        "stages": [s.model_dump() for s in res.trace.stages],
    }


def _best(res: SearchResult) -> float:
    return max((h.score for h in res.hits), default=0.0)


async def _rewrite(ctx: RunContext, query: str, res: SearchResult) -> str | None:
    if ctx.utility_model is None:
        return None
    heads = "\n".join(f"- {h.document_name} > {h.heading_path}" for h in res.hits[:3]) or "（なし）"
    msg = f"質問: {ctx.question}\n直前の検索クエリ: {query}\n上位の資料:\n{heads}"
    out = await ctx.utility_model.ainvoke([SystemMessage(load_prompt("agent_rewrite")), HumanMessage(msg)])
    text = str(out.content if isinstance(out.content, str) else out.text).strip().strip("「」\"'")
    text = text.splitlines()[0].strip() if text else ""
    return text if text and text != query else None


async def op_search(
    ctx: RunContext,
    emit: Emit,
    call_id: str,
    query: str,
    *,
    document_ids: list[str] | None = None,
    block_types: list[str] | None = None,
    mode: str = "hybrid",
    must_contain: list[str] | None = None,
) -> str:
    docs = _doc_ids_for_search(ctx, document_ids)
    base: dict[str, Any] = {
        "kb_ids": ctx.kb_ids,
        "document_ids": docs,
        "include_archived": ctx.include_archived,
        "block_types": block_types or None,
        "mode": mode,
        "top_k": ctx.cfg.top_k,
        "candidate_k": max(ctx.cfg.candidate_k, ctx.cfg.top_k),
        "must_contain": must_contain,
    }
    clock = StepClock(
        emit,
        Step(
            id=f"{call_id}:search",
            name="retrieve",
            parent_id=call_id,
            label="検索",
            status="running",
            input={"query": query, "mode": mode},
            summary="検索しています",
        ),
    )
    res = await _run_search(ctx, SearchRequest(query=query, **base))
    clock.done(f"{len(res.hits)} 件（最高スコア {_best(res):.2f}）", _hits_output(res))
    used = query
    # 関連度による再検索（R17）。rerank が効いていないとき（縮退）はスコアが比較できないので行わない
    tries = 0
    while (
        mode == "hybrid"
        and tries < ctx.cfg.max_retrieve_retries
        and _best(res) < ctx.cfg.grade_threshold
        and "rerank" not in res.degraded
    ):
        tries += 1
        rw = StepClock(
            emit,
            Step(
                id=f"{call_id}:rewrite{tries}",
                name="rewrite_query",
                parent_id=call_id,
                label="クエリの書き換え",
                status="running",
                input={"query": used},
                summary="関連の高い資料が無いため書き換えています",
            ),
        )
        try:
            new_q = await _rewrite(ctx, used, res)
        except Exception as e:
            log.warning("rewrite_failed", error=str(e)[:200])
            rw.done("書き換えに失敗しました", error=True)
            break
        if not new_q:
            rw.done("書き換えられませんでした")
            break
        rw.done(f"「{new_q}」で再検索", {"rewritten": new_q})
        again = StepClock(
            emit,
            Step(
                id=f"{call_id}:search{tries}",
                name="retrieve",
                parent_id=call_id,
                label="再検索",
                status="running",
                input={"query": new_q},
                summary="再検索しています",
            ),
        )
        res2 = await _run_search(ctx, SearchRequest(query=new_q, **base))
        better = _best(res2) > _best(res)
        adopted = "採用" if better else "元の結果を採用"
        again.done(f"{len(res2.hits)} 件（最高スコア {_best(res2):.2f}）・{adopted}", _hits_output(res2))
        if better:
            res, used = res2, new_q
    return _render_hits(ctx, used, res.hits)


async def op_keyword_search(
    ctx: RunContext, emit: Emit, call_id: str, terms: list[str], *, document_ids: list[str] | None = None
) -> str:
    terms = [t.strip() for t in terms if t.strip()][:10]
    if not terms:
        return "検索語を 1 つ以上指定してください。"
    return await op_search(
        ctx, emit, call_id, " ".join(terms), document_ids=document_ids, mode="keyword", must_contain=terms
    )


async def op_list_documents(ctx: RunContext, query: str | None = None) -> str:
    async with ctx.sessionmaker() as s:
        scope = await _scope(s, ctx)
        if scope.empty:
            return "検索範囲に文書がありません。"
        q = (
            select(Document.id, Document.filename, Document.created_at, Content.page_count, Content.status)
            .join(Content, Content.content_hash == Document.content_hash)
            .where(Document.deleted_at.is_(None), Document.kb_id.in_([uuid.UUID(k) for k in scope.kb_ids]))
            .order_by(Document.filename)
            .limit(LIST_MAX + 1)
        )
        if scope.document_ids is not None:
            q = q.where(Document.id.in_([uuid.UUID(d) for d in scope.document_ids]))
        if query and query.strip():
            q = q.where(Document.filename.ilike(f"%{query.strip()}%"))
        rows = (await s.execute(q)).all()
    if not rows:
        return f"「{query}」に一致する文書はありません。" if query else "検索範囲に文書がありません。"
    lines = [f"文書 {min(len(rows), LIST_MAX)} 件{'（先頭 50 件）' if len(rows) > LIST_MAX else ''}:"]
    for r in rows[:LIST_MAX]:
        pages = f"{r.page_count} ページ、" if r.page_count else ""
        state = "" if r.status == "ready" else f"、{r.status}"
        lines.append(f"- {r.filename}（ID: {r.id}、{pages}{r.created_at:%Y-%m-%d}{state}）")
    return "\n".join(lines)


async def _visible_document(s: AsyncSession, ctx: RunContext, ref: str) -> Document | None:
    n = _ref_number(ref)
    cited = ctx.registry.get(n) if n is not None else None
    ids = [cited.document_id] if cited else _uuids([ref])
    if not ids:
        return None
    scope = await _scope(s, ctx)
    if scope.empty:
        return None
    q = select(Document).where(
        Document.id == ids[0],
        Document.deleted_at.is_(None),
        Document.kb_id.in_([uuid.UUID(k) for k in scope.kb_ids]),
    )
    if scope.document_ids is not None:
        q = q.where(Document.id.in_([uuid.UUID(d) for d in scope.document_ids]))
    return (await s.scalars(q)).first()


async def op_get_outline(ctx: RunContext, document: str) -> str:
    async with ctx.sessionmaker() as s:
        doc = await _visible_document(s, ctx, document)
        if doc is None:
            return f"文書「{document}」は見つかりません（文書 ID か出典番号を指定してください）。"
        secs = list(
            await s.scalars(
                select(Section).where(Section.content_hash == doc.content_hash).order_by(Section.ordinal)
            )
        )
    if not secs:
        return f"「{doc.filename}」には章立てがありません。"
    lines = [
        f"「{doc.filename}」の章立て（{len(secs)} 節）。read_section にセクション ID を渡すと本文を読めます:"
    ]
    for sec in secs[:OUTLINE_MAX]:
        indent = "  " * max(0, sec.level - 1)
        page = f"p.{sec.page_start}、" if sec.page_start else ""
        lines.append(
            f"{indent}- {sec.heading_path or '（見出しなし）'}"
            f"（{page}{sec.token_len} トークン、ID: {sec.id}）"
        )
    if len(secs) > OUTLINE_MAX:
        lines.append(f"…ほか {len(secs) - OUTLINE_MAX} 節")
    return "\n".join(lines)


async def op_read_section(ctx: RunContext, section: str) -> str:
    n = _ref_number(section)
    cited = ctx.registry.get(n) if n is not None else None
    sec_ids = [cited.section_id] if cited else _uuids([section])
    if not sec_ids:
        return f"セクション「{section}」は見つかりません（セクション ID か出典番号を指定してください）。"
    async with ctx.sessionmaker() as s:
        sec = await s.get(Section, sec_ids[0])
        if sec is None:
            return f"セクション「{section}」は見つかりません。"
        scope = await _scope(s, ctx)
        if scope.empty:
            return f"セクション「{section}」は見つかりません。"
        q = select(Document).where(
            Document.content_hash == sec.content_hash,
            Document.deleted_at.is_(None),
            Document.kb_id.in_([uuid.UUID(k) for k in scope.kb_ids]),
        )
        if scope.document_ids is not None:
            q = q.where(Document.id.in_([uuid.UUID(d) for d in scope.document_ids]))
        docs = list(await s.scalars(q.order_by(Document.created_at)))
    if not docs:
        return f"セクション「{section}」は見つかりません。"
    doc = next((d for d in docs if cited and d.id == cited.document_id), docs[0])
    text = sec.text
    note = ""
    if len(text) > SECTION_MAX_CHARS:
        text = text[:SECTION_MAX_CHARS]
        note = f"\n（長いため先頭 {SECTION_MAX_CHARS} 文字のみ。続きは search で該当箇所を探してください）"
    num = ctx.registry.add_section(
        document_id=doc.id,
        document_name=doc.filename,
        section_id=sec.id,
        heading_path=sec.heading_path,
        page=sec.page_start,
        text=text,
    )
    c = ctx.registry.get(num)
    assert c is not None
    return format_material(num, c) + note


def now_ms() -> int:
    return round(time.time() * 1000)
