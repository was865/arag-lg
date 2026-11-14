"""ツールの中身（specs/005-agent R14〜R17）。@tool の包みは tools.py。

どの関数も利用者の閲覧範囲と run の検索範囲（RunContext）の中だけを見る。
"""

import re
import time
import uuid
from typing import Any, NamedTuple

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arag.agent.citations import format_material, wrap_material
from arag.agent.context import Emit, RunContext
from arag.agent.steps import Step, StepClock, record_system
from arag.agent.table import EXAMPLES, TableError, describe_tables, error_hint, parse_tables, run_query
from arag.agent.table import render as render_table
from arag.agent.table import summarize as summarize_table
from arag.db.models import Content, Document, Section
from arag.logging import get_logger
from arag.prompts import load_prompt
from arag.search.schemas import SearchHit, SearchRequest, SearchResult
from arag.search.scope import Scope, resolve_scope
from arag.search.service import candidates_hook, stage_hook

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


def _doc_ids_for_search(ctx: RunContext, refs: list[str] | None) -> tuple[list[uuid.UUID] | None, list[str]]:
    """モデルが指定した文書（ID または出典番号）を run の範囲と重ねる。解決できなかった指定も返す。

    出典番号はターンごとに振るので、前のターンの番号を渡されることがある。全部解決できなければ絞らない。
    """
    if not refs:
        return ctx.document_ids, []
    ids: list[uuid.UUID] = []
    unknown: list[str] = []
    for r in refs:
        n = _ref_number(r)
        c = ctx.registry.get(n) if n is not None else None
        if c is not None:
            ids.append(c.document_id)
        elif found := _uuids([r]):
            ids.extend(found)
        else:
            unknown.append(r)
    if not ids:
        return ctx.document_ids, unknown
    if ctx.document_ids is not None:
        allowed = set(ctx.document_ids)
        ids = [i for i in ids if i in allowed]
    return ids, unknown


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


# 検索結果のどれも関連度が低いときの前置き（最初の検索が空振りしたかの判定にも使う）
LOW_RELEVANCE_NOTE = "注意: どの資料も質問との関連度が低い"
_HAS_MATERIAL = re.compile(r"<資料 n=")


def weak_result(text: str) -> bool:
    """検索結果が 0 件か、関連度が低い資料だけか。"""
    return not _HAS_MATERIAL.search(text) or text.startswith(LOW_RELEVANCE_NOTE)


# キーワード検索が 0 件で意味検索に切り替えたときの前置き（ステップの要約もこれで見分ける）
KEYWORD_FALLBACK_NOTE = "注意: 語をすべて含む資料が無かったため、意味の近い資料を示します。"
# 型番・番号だけに絞って見つかったときの前置き（後ろに語の説明が続く）
KEYWORD_RELAX_NOTE = "注意: すべての語を含む資料が無かったため、型番・番号だけで探しました。"

# 型番・条項番号などの「そのまま出るはずの語」（数字を含む・英大文字の略語）
_CODE = re.compile(r"\d|^[A-Z][A-Z0-9_.\-]+$")


def code_terms(terms: list[str]) -> list[str]:
    return [t for t in terms if _CODE.search(t)]


def diversify(hits: list[SearchHit], *, k: int, per_document: int) -> list[SearchHit]:
    """スコア順のまま、1 文書 per_document 件までで k 件選ぶ。足りなければ残りから順に埋める。"""
    if per_document <= 0:
        return hits[:k]
    count: dict[Any, int] = {}
    picked: list[SearchHit] = []
    rest: list[SearchHit] = []
    for h in hits:
        if len(picked) < k and count.get(h.document_id, 0) < per_document:
            count[h.document_id] = count.get(h.document_id, 0) + 1
            picked.append(h)
        else:
            rest.append(h)
    chosen = {id(h) for h in picked + rest[: k - len(picked)]}
    return [h for h in hits if id(h) in chosen]


async def _run_search(ctx: RunContext, req: SearchRequest) -> SearchResult:
    """検索して、1 文書に偏らないよう top_k 件に絞る（多めに取ってから選ぶ）。"""
    k, per = req.top_k, ctx.cfg.per_document
    if per > 0:
        req = req.model_copy(update={"top_k": min(k * 2, req.candidate_k)})
    async with ctx.sessionmaker() as s:
        res = await ctx.search(s, ctx.principal, req)
    if per > 0:
        res = res.model_copy(update={"hits": diversify(res.hits, k=k, per_document=per)})
    return res


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


_MODE_NAME = {"hybrid": "ハイブリッド（意味＋語句）", "dense": "意味", "keyword": "語句"}


class StageEmitter:
    """検索の内部の段（埋め込み → 候補 → 絞り込み → rerank）を、終わった順に子ステップとして送る。

    `search.service.stage_hook` に `on_stage` を掛けて使う。
    rerank は検索が終わってから、残った上位を足して送り直す。
    """

    def __init__(
        self, emit: Emit, parent_id: str, step_id: str, query: str, *, mode: str, candidate_k: int
    ) -> None:
        self.emit, self.parent_id, self.step_id, self.query = emit, parent_id, step_id, query
        self.mode, self.candidate_k = mode, candidate_k
        self.seen: dict[str, Any] = {}
        self.cands: list[dict[str, Any]] = []

    def _put(
        self,
        name: str,
        label: str,
        summary: str,
        took: int,
        inp: dict[str, Any],
        out: dict[str, Any] | None = None,
    ) -> None:
        step = Step(
            id=f"{self.step_id}:{name}",
            name=name,
            parent_id=self.parent_id,
            label=label,
            status="done",
            duration_ms=took,
            input=inp,
            output=out,
            summary=summary,
        )
        self.emit({"type": "step", "step": step.model_dump()})

    def on_candidates(self, hits: list[dict[str, Any]]) -> None:
        # 融合スコア（RRF）は小さい値なので、最高を 1 にした相対値で見せる
        top = max((h["score"] for h in hits), default=0.0) or 1.0
        self.cands = [{**h, "score": round(h["score"] / top, 3)} for h in hits]

    def on_stage(self, st: Any) -> None:
        self.seen[st.name] = st
        q = {"query": self.query}
        if st.name == "embed":
            if self.mode == "keyword":
                self._put("embed", "検索語の解析", "語句検索のために語に分けた", st.ms, q)
            else:
                self._put(
                    "embed", "クエリの埋め込み", "意味（密）と語句（疎）の両方のベクトルにした", st.ms, q
                )
        elif st.name == "query":
            self._candidates(st.ms)
        elif st.name == "hydrate":
            self._candidates(self.seen["query"].ms + st.ms)
        elif st.name == "rerank" and st.count:
            self._put(
                "rerank",
                "再ランキング",
                f"{st.count} 件を質問との関連で並べ替えた",
                st.ms,
                {"candidates": st.count},
            )

    def _candidates(self, took: int, mode: str | None = None) -> None:
        q, h = self.seen["query"], self.seen.get("hydrate")
        text = f"{_MODE_NAME[mode or self.mode]}で候補 {q.count} 件"
        if h and h.count is not None and h.count != q.count:
            text += f" → 閲覧できる本文 {h.count} 件"
        self._put(
            "candidates",
            "候補の取得",
            text,
            took,
            {
                "mode": mode or self.mode,
                "candidate_k": self.candidate_k,
                "score": "融合スコア（最高を 1 とした相対値）",
            },
            {"hits": self.cands} if self.cands else None,
        )

    def finish(self, res: SearchResult) -> None:
        """縮退（埋め込み・rerank に接続できなかった）と、rerank の最終の上位を足して送り直す。"""
        if "dense" in res.degraded and "embed" in self.seen:
            st = self.seen["embed"]
            self._put(
                "embed",
                "クエリの埋め込み",
                "埋め込みに接続できず、語句検索だけで続行",
                st.ms,
                {"query": self.query},
                {"degraded": True},
            )
            if "query" in self.seen:
                self._candidates(
                    self.seen["query"].ms + (self.seen["hydrate"].ms if "hydrate" in self.seen else 0),
                    "keyword",
                )
        r = self.seen.get("rerank")
        if r is None:
            return
        if "rerank" in res.degraded:
            self._put(
                "rerank",
                "再ランキング",
                "rerank に接続できず、検索の順位のまま",
                r.ms,
                {"candidates": self.seen["query"].count},
                {"selected": []},
            )
        elif r.count:
            selected = [
                {
                    "id": str(i),
                    "score": round(x.score, 3),
                    "title": f"{x.document_name} — {x.heading_path}" if x.heading_path else x.document_name,
                }
                for i, x in enumerate(res.hits, start=1)
            ]
            self._put(
                "rerank",
                "再ランキング",
                f"{r.count} 件を質問との関連で並べ替え → 上位 {len(res.hits)} 件（最高 {_best(res):.2f}）",
                r.ms,
                {"candidates": r.count, "top_n": len(res.hits)},
                {"selected": selected},
            )


async def _search_traced(
    ctx: RunContext, emit: Emit, parent_id: str, step_id: str, req: SearchRequest
) -> SearchResult:
    """検索を行い、内部の段を終わった順に送る。"""
    se = StageEmitter(emit, parent_id, step_id, req.query, mode=req.mode, candidate_k=req.candidate_k)
    token, token2 = stage_hook.set(se.on_stage), candidates_hook.set(se.on_candidates)
    try:
        res = await _run_search(ctx, req)
    finally:
        stage_hook.reset(token)
        candidates_hook.reset(token2)
    se.finish(res)
    return res


_JA = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")


def rewrite_message(question: str, query: str, hits: list[SearchHit]) -> str:
    heads = "\n".join(f"- {h.document_name} > {h.heading_path}" for h in hits[:3]) or "（なし）"
    msg = f"質問: {question}\n直前の検索クエリ: {query}\n上位の資料:\n{heads}"
    if not _JA.search(question):
        # 日本語の rerank は英日の組で点が低く出る。小さいモデルは指示が無いと英語のまま言い換える
        msg += "\n\n質問は日本語以外です。日本語に訳した検索クエリを出力してください。"
    return msg


async def _rewrite(ctx: RunContext, query: str, res: SearchResult) -> str | None:
    if ctx.utility_model is None:
        return None
    msg = rewrite_message(ctx.question, query, res.hits)
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
    step_tag: str = "",
    label: str = "検索",
    running: str = "検索中",
    next_on_empty: str | None = None,
) -> str:
    """step_tag は同じ呼び出しで 2 回検索するときのステップ ID の区別（親は call_id のまま）。"""
    sid = f"{call_id}:{step_tag}" if step_tag else call_id
    docs, unknown = _doc_ids_for_search(ctx, document_ids)
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
    t0 = time.perf_counter()
    # 内部の段（埋め込み → 候補 → rerank）を終わった順に送り、結果の行は最後に出す
    res = await _search_traced(ctx, emit, call_id, f"{sid}:search", SearchRequest(query=query, **base))
    clock = StepClock(
        emit,
        Step(
            id=f"{sid}:search",
            name="retrieve",
            parent_id=call_id,
            label=label,
            status="running",
            input={"query": query, "mode": mode},
            summary=running,
        ),
    )
    clock.t0 = t0
    if must_contain and not res.hits:
        # 何が足りなかったのか・次に何をするのかを画面で分かるようにする
        words = "".join(f"「{t}」" for t in must_contain)
        detail: dict[str, Any] = {**_hits_output(res), "terms": must_contain}
        if next_on_empty:
            detail["fallback"] = next_on_empty
        clock.done(f"0 件（{words}をすべて含む箇所なし）", detail)
    else:
        clock.done(f"{len(res.hits)} 件（最高スコア {_best(res):.2f}）", _hits_output(res))
    used = query
    # 関連度による再検索（R17）。rerank が効いていないとき（縮退）はスコアが比較できないので行わない
    tries = 0
    while tries < ctx.cfg.max_retrieve_retries and _is_low(ctx, res, mode):
        tries += 1
        rw = StepClock(
            emit,
            Step(
                id=f"{sid}:rewrite{tries}",
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
        t1 = time.perf_counter()
        res2 = await _search_traced(
            ctx, emit, call_id, f"{sid}:search{tries}", SearchRequest(query=new_q, **base)
        )
        again = StepClock(
            emit,
            Step(
                id=f"{sid}:search{tries}",
                name="retrieve",
                parent_id=call_id,
                label="再検索",
                status="running",
                input={"query": new_q},
                summary="再検索しています",
            ),
        )
        again.t0 = t1
        better = _best(res2) > _best(res)
        adopted = "採用" if better else "元の結果を採用"
        again.done(f"{len(res2.hits)} 件（最高スコア {_best(res2):.2f}）・{adopted}", _hits_output(res2))
        if better:
            res, used = res2, new_q
    out = _render_hits(ctx, used, res.hits)
    if unknown:
        out = (
            f"注意: 文書の指定 {', '.join(unknown)} はこのターンの出典番号・文書 ID ではないため無視しました"
            f"{'（文書を絞らずに検索）' if docs == ctx.document_ids else ''}。"
            "出典番号はターンごとに振り直されます。\n\n" + out
        )
    if res.hits and _is_low(ctx, res, mode):
        # 小さいモデルは無関係な資料でも答えを組み立てがちなので、関連の薄さを明示する
        out = (
            f"{LOW_RELEVANCE_NOTE}（最高スコア {_best(res):.2f}）。"
            "質問に直接答える記述が無ければ、資料からは見つからなかったと（質問と同じ言語で）答えること。"
            "言葉が似ているだけの無関係な資料を根拠にしない。\n\n" + out
        )
    return out


def _is_low(ctx: RunContext, res: SearchResult, mode: str) -> bool:
    return mode == "hybrid" and "rerank" not in res.degraded and _best(res) < ctx.cfg.grade_threshold


async def op_keyword_search(
    ctx: RunContext, emit: Emit, call_id: str, terms: list[str], *, document_ids: list[str] | None = None
) -> str:
    """全語の完全一致 → 型番・番号だけ → 意味検索、の順に広げる。各段は子ステップとして見せる。"""
    terms = [t.strip() for t in terms if t.strip()][:10]
    if not terms:
        return "検索語を 1 つ以上指定してください。"
    query = " ".join(terms)
    codes = code_terms(terms)
    relax = bool(codes) and len(codes) < len(terms)
    out = await op_search(
        ctx,
        emit,
        call_id,
        query,
        document_ids=document_ids,
        mode="keyword",
        must_contain=terms,
        next_on_empty="codes" if relax else "semantic",
    )
    if "<資料 " in out:
        return out
    if relax:
        # 「MX-17」「異常時の対応」のように説明的な語が混ざると全語一致しにくい。型番だけで探し直す
        dropped = "".join(f"「{t}」" for t in terms if t not in codes)
        out = await op_search(
            ctx,
            emit,
            call_id,
            query,
            document_ids=document_ids,
            mode="keyword",
            must_contain=codes,
            step_tag="c",
            label="型番のみで再検索",
            running=f"{dropped}を除外し、型番のみで検索中",
            next_on_empty="semantic",
        )
        if "<資料 " in out:
            return (
                f"{KEYWORD_RELAX_NOTE}{dropped}は資料に無い言い回しかもしれません。"
                f"一般的な規定や手順も要るなら、{dropped}の内容を search で調べてください。\n\n{out}"
            )
    # 表記ゆれ（「ISO認証」と「ISO 27001認証」など）で 0 件になりやすいので、意味検索で補う
    alt = await op_search(
        ctx,
        emit,
        call_id,
        query,
        document_ids=document_ids,
        step_tag="h",
        label="セマンティック検索で補完",
        running="完全一致なし。セマンティック検索中",
    )
    return f"{KEYWORD_FALLBACK_NOTE}\n\n{alt}"


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
        if not query:
            return "検索範囲に文書がありません。"
        # 小さいモデルは内容の語で文書名を探して諦めがちなので、本文の検索へ誘導する
        return f"「{query}」を名前に含む文書はありません。文書の内容を探すときは search を使ってください。"
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


async def _visible_section(ctx: RunContext, ref: str) -> tuple[Section, Document] | None:
    """出典番号かセクション ID から、利用者に見える章とその文書を得る。"""
    n = _ref_number(ref)
    cited = ctx.registry.get(n) if n is not None else None
    sec_ids = [cited.section_id] if cited else _uuids([ref])
    if not sec_ids:
        return None
    async with ctx.sessionmaker() as s:
        sec = await s.get(Section, sec_ids[0])
        if sec is None:
            return None
        scope = await _scope(s, ctx)
        if scope.empty:
            return None
        q = select(Document).where(
            Document.content_hash == sec.content_hash,
            Document.deleted_at.is_(None),
            Document.kb_id.in_([uuid.UUID(k) for k in scope.kb_ids]),
        )
        if scope.document_ids is not None:
            q = q.where(Document.id.in_([uuid.UUID(d) for d in scope.document_ids]))
        docs = list(await s.scalars(q.order_by(Document.created_at)))
    if not docs:
        return None
    return sec, next((d for d in docs if cited and d.id == cited.document_id), docs[0])


async def op_read_section(ctx: RunContext, section: str) -> str:
    found = await _visible_section(ctx, section)
    if found is None:
        return f"セクション「{section}」は見つかりません（セクション ID か出典番号を指定してください）。"
    sec, doc = found
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


class _Failure(NamedTuple):
    """table_query の失敗（モデルに返す文）。"""

    text: str


REPEAT_BLOCKED_NOTE = (
    "同じ指定では失敗する（前回この指定で失敗した: {error}）。"
    "式を変えるか、表の値を書き写して calculate を使ってください。"
)


async def op_table_query(
    ctx: RunContext,
    source: str,
    where: str = "",
    compute: str = "",
    table: int = 1,
    *,
    emit: Emit | None = None,
    call_id: str = "",
) -> str:
    """資料の表から、条件に合う行と合計を計算で求める（specs/026 R12・R13）。

    失敗した指定はターンの間覚えておき、同じ指定でもう一度呼ばれたら計算せずに止める（T12）。
    """
    key = (source.strip(), where.strip(), compute.strip(), table)
    if (prev := ctx.table_failures.get(key)) is not None:
        note = REPEAT_BLOCKED_NOTE.format(error=prev[:300])
        if emit is not None:
            record_system(
                emit,
                f"system-repeat-blocked-{len(ctx.table_failures)}",
                "repeat_blocked",
                "同じ指定の繰り返しを止めた",
                "前に失敗した table_query と同じ指定で呼ばれたため、計算せずに式を変えるよう返した",
                input={"source": key[0], "where": key[1], "compute": key[2], "table": key[3]},
                output={"note": note},
            )
        return note
    out = await _table_query(ctx, source, where, compute, table, call_id)
    if isinstance(out, _Failure):
        ctx.table_failures[key] = out.text
        return out.text
    return out


async def _table_query(
    ctx: RunContext, source: str, where: str, compute: str, table: int, call_id: str = ""
) -> str | _Failure:
    found = await _visible_section(ctx, source)
    if found is None:
        return _Failure(
            f'資料「{source}」は見つかりません。source には、表のある資料の出典番号（例 "1"）か'
            "セクション ID を指定してください。"
        )
    sec, doc = found
    tables = parse_tables(sec.text)
    if not tables:
        return _Failure(
            f"「{doc.filename}」のこの箇所に表はありません。"
            "表のある資料の出典番号を指定するか、search で表を探してください。"
        )
    if not 1 <= table <= len(tables):
        return _Failure(
            f"table は 1〜{len(tables)} で指定してください。\n{describe_tables(tables)}\n{EXAMPLES}"
        )
    target = tables[table - 1]
    try:
        result = run_query(target, where, compute)
    except TableError as e:
        # 誤りには必ず使える列名と書き方の例を添える（R13）
        hint = EXAMPLES if "使える列" in str(e) else error_hint(target)
        return _Failure(f"表を集計できませんでした: {e}\n{hint}")
    body = render_table(result, where, compute)
    if call_id:
        ctx.table_outputs[call_id] = summarize_table(result, compute)
    if len(tables) > 1:
        body += f"\n（この資料には表が {len(tables)} つあります）\n{describe_tables(tables)}"
    # 引用は章の番号にそろえる（表の結果も同じ資料の一部）
    num = ctx.registry.add_section(
        document_id=doc.id,
        document_name=doc.filename,
        section_id=sec.id,
        heading_path=sec.heading_path,
        page=sec.page_start,
        text=sec.text[:SECTION_MAX_CHARS],
    )
    c = ctx.registry.get(num)
    assert c is not None
    return wrap_material(num, c, body)


def now_ms() -> int:
    return round(time.time() * 1000)
