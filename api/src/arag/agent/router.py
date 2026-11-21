"""対話の API（specs/005-agent R1〜R12・R26〜R30）。"""

import secrets
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from arag.agent.adapters.redis_stream import EventSink, read_events, request_cancel, stream_exists
from arag.agent.catalog import load_catalog
from arag.agent.config import ModelCatalog, ModelNotFound
from arag.agent.events import CitationRef, SourceView
from arag.agent.query_image import ImageRejected, decode_query_image, image_key
from arag.agent.service import (
    QueryImageIn,
    RunRequest,
    active_run,
    create_run,
    get_run,
    get_thread,
)
from arag.agent.steps import Step
from arag.agent.thread_search import Match, search_threads
from arag.audit import AuditEvent
from arag.auth.principal import CurrentPrincipal, OptionalPrincipal, Principal
from arag.db.models import Document, KnowledgeBase, Message, MessageFeedback, Run, Thread
from arag.deps import CtxDep, get_session
from arag.errors import ApiError, not_found
from arag.kb.access import load_access
from arag.kb.service import readable_kb_clause
from arag.settings import Settings
from arag.storage import Storage

router = APIRouter(tags=["chat"])
Session = Annotated[AsyncSession, Depends(get_session)]


def _settings(request: Request) -> Settings:
    s: Settings = request.app.state.settings
    return s


def _redis(request: Request) -> Redis:
    r: Redis = request.app.state.redis
    return r


async def _catalog(request: Request, s: AsyncSession) -> ModelCatalog:
    # DB の目録と .env の合成（specs/013-llm-keys R5）。変更がすぐ効くよう毎回読む
    return await load_catalog(s, _settings(request))


# --- モデル ---


class ModelOut(BaseModel):
    id: str
    label: str
    tags: list[str]
    available: bool


class ModelsOut(BaseModel):
    models: list[ModelOut]
    default_id: str | None
    # 質問に画像を添えられるか（図の説明用モデルが設定されているか。specs/017 R3）
    image_input: bool = False


@router.get("/v1/models", response_model=ModelsOut)
async def list_models(request: Request, _p: CurrentPrincipal, s: Session) -> ModelsOut:
    cat = await _catalog(request, s)
    try:
        default: str | None = cat.default().id
    except ModelNotFound:
        default = None
    return ModelsOut(
        models=[
            ModelOut(id=m.id, label=m.label, tags=list(m.tags), available=m.available) for m in cat.models
        ],
        default_id=default,
        image_input=bool(_settings(request).vlm_model),
    )


# --- スレッド ---


Visibility = Literal["private", "org", "public"]


class ThreadOut(BaseModel):
    id: uuid.UUID
    title: str
    pinned: bool
    visibility: Visibility = "private"
    share_token: str | None = None
    created_at: datetime
    updated_at: datetime


class ThreadList(BaseModel):
    items: list[ThreadOut]


class ThreadSearchHit(BaseModel):
    thread: ThreadOut
    match: Match = Field(description="当たった場所（題名・質問・回答）")
    snippet: str = Field(description="当たった語の前後")
    message_id: uuid.UUID | None = Field(default=None, description="当たったメッセージ（題名のときは無し）")


class ThreadSearchResult(BaseModel):
    items: list[ThreadSearchHit]


class FeedbackOut(BaseModel):
    rating: Literal["up", "down"]
    reason_tags: list[str]
    comment: str | None


class QueryImageOut(BaseModel):
    """質問に添えた画像（本体は /v1/threads/{id}/messages/{id}/image）。"""

    width: int
    height: int
    description: str | None = None


def _image_out(request: dict[str, Any]) -> QueryImageOut | None:
    img = request.get("image")
    if not isinstance(img, dict) or not img.get("key"):
        return None
    return QueryImageOut(width=img["width"], height=img["height"], description=img.get("description"))


class MessageOut(BaseModel):
    id: uuid.UUID
    ordinal: int
    query: str
    answer: str
    status: str
    model_id: str | None
    tokens_in: int
    tokens_out: int
    duration_ms: int
    steps: list[Step]
    sources: list[SourceView]
    citation_map: dict[str, CitationRef]
    no_answer_reason: str | None
    created_at: datetime
    # 続けて聞く質問の候補（specs/028 R1）
    suggestions: list[str] = []
    feedback: FeedbackOut | None = None
    image: QueryImageOut | None = None


class ActiveRunOut(BaseModel):
    run_id: uuid.UUID
    message_id: uuid.UUID
    query: str
    status: str


class ThreadDetail(ThreadOut):
    messages: list[MessageOut]
    active_run: ActiveRunOut | None


class ThreadCreate(BaseModel):
    title: str = Field("新しいチャット", min_length=1, max_length=200)


class ThreadPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    pinned: bool | None = None
    visibility: Visibility | None = None


def _thread_out(t: Thread) -> ThreadOut:
    return ThreadOut(
        id=t.id,
        title=t.title,
        pinned=t.pinned,
        visibility=t.visibility,  # type: ignore[arg-type]
        share_token=t.share_token,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


def _active_out(r: Run | None) -> ActiveRunOut | None:
    if r is None:
        return None
    return ActiveRunOut(
        run_id=r.id, message_id=r.message_id, query=r.request.get("query", ""), status=r.status
    )


@router.get("/v1/threads", response_model=ThreadList)
async def list_threads(
    p: CurrentPrincipal,
    s: Session,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    before: datetime | None = None,
) -> ThreadList:
    q = select(Thread).where(Thread.user_id == p.user_id)
    if before is not None:
        q = q.where(Thread.updated_at < before)
    rows = await s.scalars(q.order_by(Thread.pinned.desc(), Thread.updated_at.desc()).limit(limit))
    return ThreadList(items=[_thread_out(t) for t in rows])


@router.get("/v1/threads/search", response_model=ThreadSearchResult)
async def search_thread_list(
    p: CurrentPrincipal,
    s: Session,
    q: Annotated[str, Query(min_length=1, max_length=200, pattern=r"\S")],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> ThreadSearchResult:
    """自分のスレッドを、題名・質問・回答の本文で探す（空白で区切った語はすべて含む）。"""
    hits = await search_threads(s, p.user_id, q, limit)
    return ThreadSearchResult(
        items=[
            ThreadSearchHit(
                thread=_thread_out(h.thread),
                match=h.match,
                snippet=h.snippet,
                message_id=uuid.UUID(h.message_id) if h.message_id else None,
            )
            for h in hits
        ]
    )


@router.post("/v1/threads", response_model=ThreadOut, status_code=201)
async def create_thread(p: CurrentPrincipal, s: Session, body: ThreadCreate) -> ThreadOut:
    t = Thread(id=uuid.uuid4(), user_id=p.user_id, title=body.title)
    s.add(t)
    await s.commit()
    await s.refresh(t)
    return _thread_out(t)


@router.get("/v1/threads/{thread_id}", response_model=ThreadDetail)
async def get_thread_detail(thread_id: uuid.UUID, p: CurrentPrincipal, s: Session) -> ThreadDetail:
    t = await get_thread(s, p, thread_id)
    msgs = list(await s.scalars(select(Message).where(Message.thread_id == t.id).order_by(Message.ordinal)))
    fb = {
        f.message_id: f
        for f in await s.scalars(
            select(MessageFeedback).where(MessageFeedback.message_id.in_([m.id for m in msgs]))
        )
    }
    return ThreadDetail(
        **_thread_out(t).model_dump(),
        messages=[message_out(m, fb.get(m.id)) for m in msgs],
        active_run=_active_out(await active_run(s, t.id)),
    )


def message_out(m: Message, f: MessageFeedback | None = None) -> MessageOut:
    """保存したターンを API の形にする（スレッドの詳細と、管理者が読む報告の詳細で共用）。"""
    return MessageOut(
        id=m.id,
        ordinal=m.ordinal,
        query=m.query,
        answer=m.answer_text,
        status=m.status,
        model_id=m.model_id,
        tokens_in=m.tokens_in,
        tokens_out=m.tokens_out,
        duration_ms=m.duration_ms,
        steps=[Step.model_validate(x) for x in m.steps],
        sources=[SourceView.model_validate(x) for x in m.sources],
        citation_map={k: CitationRef.model_validate(v) for k, v in m.citation_map.items()},
        suggestions=list(m.suggestions or []),
        no_answer_reason=m.no_answer_reason,
        created_at=m.created_at,
        image=_image_out(m.request),
        feedback=FeedbackOut(rating=f.rating, reason_tags=f.reason_tags, comment=f.comment)  # type: ignore[arg-type]
        if f is not None
        else None,
    )


@router.get(
    "/v1/threads/{thread_id}/messages/{message_id}/image",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
)
async def get_message_image(
    thread_id: uuid.UUID, message_id: uuid.UUID, request: Request, p: CurrentPrincipal, s: Session
) -> Response:
    """質問に添えた画像。スレッドの持ち主だけが見られる（specs/017 R6）。"""
    t = await get_thread(s, p, thread_id)
    m = await s.get(Message, message_id)
    img = (m.request or {}).get("image") if m is not None and m.thread_id == t.id else None
    storage: Storage = request.app.state.storage
    if not isinstance(img, dict) or not img.get("key") or not await storage.exists(img["key"]):
        raise not_found("画像が見つかりません")
    return Response(
        await storage.read(img["key"]),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.patch("/v1/threads/{thread_id}", response_model=ThreadOut)
async def patch_thread(thread_id: uuid.UUID, ctx: CtxDep, body: ThreadPatch) -> ThreadOut:
    s = ctx.session
    t = await get_thread(s, ctx.principal, thread_id)
    if body.title is not None:
        t.title = body.title.strip() or t.title
    if body.pinned is not None:
        t.pinned = body.pinned
    if body.visibility is not None and body.visibility != t.visibility:
        t.visibility = body.visibility
        # 公開するときに初めてトークンを出す。private に戻しても保つ（R2）
        if body.visibility != "private" and t.share_token is None:
            t.share_token = secrets.token_urlsafe(16)
        await ctx.audit(
            AuditEvent(
                action="thread.share",
                resource_type="thread",
                resource_id=str(t.id),
                detail={"visibility": body.visibility},
            )
        )
    await s.commit()
    await s.refresh(t)
    return _thread_out(t)


@router.delete("/v1/threads/{thread_id}", status_code=204)
async def delete_thread(thread_id: uuid.UUID, request: Request, p: CurrentPrincipal, s: Session) -> Response:
    t = await get_thread(s, p, thread_id)
    r = await active_run(s, t.id)
    if r is not None:
        await request_cancel(_redis(request), str(r.id))
    # 質問に添えた画像（保存済みのメッセージと、まだ終わっていない run の分。specs/017 R8）
    reqs = [*await s.scalars(select(Message.request).where(Message.thread_id == t.id))]
    reqs += [*await s.scalars(select(Run.request).where(Run.thread_id == t.id))]
    image_keys = {
        img["key"] for q in reqs if isinstance(img := (q or {}).get("image"), dict) and img.get("key")
    }
    # checkpoint（スキーマ lg）も消す。表が無い（runner 未起動）なら何もしない
    for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
        exists = await s.scalar(text("SELECT to_regclass(:t)"), {"t": f"lg.{table}"})
        if exists:
            await s.execute(text(f"DELETE FROM lg.{table} WHERE thread_id = :id"), {"id": str(t.id)})
    await s.delete(t)
    await s.commit()
    storage: Storage = request.app.state.storage
    for key in image_keys:
        await storage.delete(key)
    return Response(status_code=204)


# --- run ---


class RunCreated(BaseModel):
    run_id: uuid.UUID
    message_id: uuid.UUID
    thread_id: uuid.UUID


async def _check_limits(request: Request, s: AsyncSession, p: Principal) -> None:
    settings = _settings(request)
    if settings.rate_limit_runs_per_min > 0:
        r = _redis(request)
        key = f"rl:runs:{p.user_id}:{int(datetime.now(UTC).timestamp() // 60)}"
        n = await r.incr(key)
        if n == 1:
            await r.expire(key, 70)
        if n > settings.rate_limit_runs_per_min:
            raise ApiError(429, "rate_limited", "短時間に質問が多すぎます。少し待ってからお試しください")
    if settings.monthly_token_limit > 0:
        month = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        used = await s.scalar(
            select(func.coalesce(func.sum(Message.tokens_in + Message.tokens_out), 0))
            .join(Thread, Thread.id == Message.thread_id)
            .where(Thread.user_id == p.user_id, Message.created_at >= month)
        )
        if (used or 0) >= settings.monthly_token_limit:
            raise ApiError(429, "monthly_quota_exceeded", "今月の利用上限に達しました")


async def _store_image(request: Request, p: Principal, img: QueryImageIn) -> dict[str, Any]:
    """検証・縮小して保存し、run の request に入れる情報を返す（specs/017 R2・R3）。"""
    settings = _settings(request)
    if not settings.vlm_model:
        raise ApiError(422, "image_unsupported", "画像の読み取りが設定されていないため、画像は添えられません")
    try:
        q = decode_query_image(
            img.data, max_px=settings.query_image_max_px, max_bytes=settings.query_image_max_bytes
        )
    except ImageRejected as e:
        raise ApiError(422, "invalid_image", str(e)) from e
    image_id = uuid.uuid4().hex
    key = image_key(p.user_id, image_id)
    storage: Storage = request.app.state.storage
    await storage.put(key, q.data)
    return {"id": image_id, "key": key, "width": q.width, "height": q.height}


async def _start(
    request: Request, s: AsyncSession, p: Principal, thread: Thread | None, body: RunRequest
) -> RunCreated:
    if not p.email_verified:
        raise ApiError(403, "email_not_verified", "メールアドレスの確認が必要です")
    try:
        model = (await _catalog(request, s)).resolve(body.model_id)
    except ModelNotFound as e:
        raise ApiError(422, "model_unavailable", str(e)) from e
    await _check_limits(request, s, p)
    image = await _store_image(request, p, body.image) if body.image is not None else None
    t, run = await create_run(s, p, thread, body, model.id, image=image)
    await s.commit()
    return RunCreated(run_id=run.id, message_id=run.message_id, thread_id=t.id)


@router.post("/v1/runs", response_model=RunCreated, status_code=202)
async def start_run_new_thread(
    request: Request, p: CurrentPrincipal, s: Session, body: RunRequest
) -> RunCreated:
    return await _start(request, s, p, None, body)


@router.post("/v1/threads/{thread_id}/runs", response_model=RunCreated, status_code=202)
async def start_run(
    thread_id: uuid.UUID, request: Request, p: CurrentPrincipal, s: Session, body: RunRequest
) -> RunCreated:
    t = await get_thread(s, p, thread_id)
    return await _start(request, s, p, t, body)


@router.get(
    "/v1/threads/{thread_id}/active-run",
    response_model=ActiveRunOut,
    responses={204: {"description": "実行中の run は無い"}},
)
async def get_active_run(thread_id: uuid.UUID, p: CurrentPrincipal, s: Session) -> Any:
    t = await get_thread(s, p, thread_id)
    out = _active_out(await active_run(s, t.id))
    return out if out is not None else Response(status_code=204)


@router.post("/v1/runs/{run_id}/cancel", status_code=202)
async def cancel_run(run_id: uuid.UUID, request: Request, p: CurrentPrincipal, s: Session) -> Response:
    run = await get_run(s, p, run_id)
    settings = _settings(request)
    # まだ runner が取っていなければその場で取り消す
    res = await s.execute(
        update(Run)
        .where(Run.id == run.id, Run.status == "queued")
        .values(status="cancelled", finished_at=datetime.now(UTC))
        .returning(Run.id)
    )
    await s.commit()
    if res.scalar_one_or_none() is not None:
        sink = EventSink(_redis(request), str(run.id), ttl_sec=settings.run_events_ttl_sec)
        await sink.emit({"type": "run.cancelled", "message_id": str(run.message_id)})
    elif run.status == "running":
        await request_cancel(_redis(request), str(run.id), ttl_sec=settings.run_events_ttl_sec)
    return Response(status_code=202)


def _sse(entry_id: str, typ: str, data: str) -> str:
    return f"id: {entry_id}\nevent: {typ}\ndata: {data}\n\n"


@router.get(
    "/v1/runs/{run_id}/stream",
    responses={
        200: {"content": {"text/event-stream": {"schema": {"$ref": "#/components/schemas/RunEvent"}}}}
    },
)
async def stream_run(
    run_id: uuid.UUID,
    request: Request,
    p: CurrentPrincipal,
    s: Session,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    run = await get_run(s, p, run_id)
    redis = _redis(request)
    if run.status not in ("queued", "running") and not await stream_exists(redis, str(run.id)):
        raise ApiError(
            410, "run_expired", "この回答のストリームは終了しています。スレッドを開き直してください"
        )
    start = last_event_id if last_event_id and _valid_id(last_event_id) else "0"
    await s.close()

    async def gen() -> AsyncIterator[str]:
        yield "retry: 2000\n\n"
        async for item in read_events(redis, str(run_id), start):
            if await request.is_disconnected():
                return
            if item is None:
                yield ": keep-alive\n\n"
                continue
            yield _sse(*item)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _valid_id(v: str) -> bool:
    a, _, b = v.partition("-")
    return a.isdigit() and (b == "" or b.isdigit())


# --- 評価（👍👎）---


# 「良くない」の理由（web の FEEDBACK_REASON_TAGS と同じ。error は specs/028 R12）
FeedbackReason = Literal["outdated", "wrong", "no_source", "irrelevant", "other", "error"]


class FeedbackIn(BaseModel):
    rating: Literal["up", "down"]
    reason_tags: list[FeedbackReason] = Field(default_factory=list, max_length=10)
    comment: str | None = Field(None, max_length=2000)


@router.put("/v1/messages/{message_id}/feedback", response_model=FeedbackOut)
async def put_feedback(
    message_id: uuid.UUID, p: CurrentPrincipal, s: Session, body: FeedbackIn
) -> FeedbackOut:
    msg = await s.get(Message, message_id)
    if msg is None:
        raise not_found()
    await get_thread(s, p, msg.thread_id)
    fb = (await s.scalars(select(MessageFeedback).where(MessageFeedback.message_id == msg.id))).first()
    if fb is None:
        fb = MessageFeedback(message_id=msg.id, user_id=p.user_id, rating=body.rating)
        s.add(fb)
    fb.rating = body.rating
    fb.reason_tags = list(body.reason_tags)
    fb.comment = body.comment
    fb.updated_at = datetime.now(UTC)
    # 利用者が直した報告は、対応済みでも未対応に戻す（技術者が読み直す）
    fb.status, fb.resolved_by, fb.resolved_at = "open", None, None
    await s.commit()
    return FeedbackOut(rating=body.rating, reason_tags=list(body.reason_tags), comment=body.comment)


# ── 共有（specs/008-thread-share）────────────────────────────────────────


class SharedSource(BaseModel):
    n: int
    title: str
    # 同じ文書の別の箇所を見分けるための見出しとページ（本文は出さない）
    heading: str | None = None
    page: int | None = None
    # 見る人が読めない文書（specs/024 R16）。文書名・見出し・ページは伏せる
    restricted: bool = False


RESTRICTED_TITLE = "閲覧できない資料"


class SharedMessage(BaseModel):
    query: str
    answer: str
    created_at: datetime
    sources: list[SharedSource]
    # 画像そのものは共有しない（specs/017 R6）
    has_image: bool = False


class SharedThreadOut(BaseModel):
    """共有ページに渡す最小限（R5）。ステップ・章本文・文書 ID・利用者は含めない。"""

    title: str
    visibility: Visibility
    messages: list[SharedMessage]


def shared_sources(
    citation_map: dict[str, Any], sources: list[dict[str, Any]], readable: set[str] | None = None
) -> list[SharedSource]:
    """引用番号 → 文書名と箇所（見出し・ページ。番号順）。出典が見つからない番号は除く。

    readable を渡すと、そこに無い文書は文書名・見出し・ページを伏せる（specs/024 R16）。
    """
    titles = {str(x.get("id")): str(x.get("title", "")) for x in sources}
    # 社内システムの出典は文書の権限で伏せない。行は共有ページに出さず、名前と取得の時点だけ（specs/032 R22）
    systems = {str(x.get("id")) for x in sources if x.get("kind") == "system"}
    sections: dict[str, dict[str, Any]] = {
        str(sec.get("id")): sec for x in sources for sec in (x.get("sections") or []) if isinstance(sec, dict)
    }
    out: list[SharedSource] = []
    for key, ref in citation_map.items():
        if not key.isdigit() or not isinstance(ref, dict):
            continue
        title = titles.get(str(ref.get("source_id")))
        if title is None:
            continue
        if readable is not None and str(ref.get("source_id")) not in readable | systems:
            out.append(SharedSource(n=int(key), title=RESTRICTED_TITLE, restricted=True))
            continue
        sec = sections.get(str(ref.get("section_id")), {})
        heading = str(sec.get("heading") or "").strip() or None
        page = sec.get("page")
        out.append(
            SharedSource(
                n=int(key), title=title, heading=heading, page=page if isinstance(page, int) else None
            )
        )
    return sorted(out, key=lambda x: x.n)


async def _readable_documents(s: AsyncSession, p: Principal | None, msgs: list[Message]) -> set[str]:
    """引用された文書のうち、見る人が今読めるもの。ログインしていなければ「全員」に共有された KB だけ。"""
    ids: set[uuid.UUID] = set()
    for m in msgs:
        for ref in (m.citation_map or {}).values():
            if isinstance(ref, dict):
                try:
                    ids.add(uuid.UUID(str(ref.get("source_id"))))
                except ValueError:
                    continue
    if not ids:
        return set()
    a = await load_access(s, p or Principal(user_id=""))
    rows = await s.scalars(
        select(Document.id)
        .join(KnowledgeBase, KnowledgeBase.id == Document.kb_id)
        .where(
            Document.id.in_(ids),
            Document.deleted_at.is_(None),
            KnowledgeBase.deleted_at.is_(None),
            readable_kb_clause(a),
        )
    )
    return {str(d) for d in rows}


@router.get("/v1/shared/{token}", response_model=SharedThreadOut)
async def get_shared_thread(token: str, p: OptionalPrincipal, s: Session) -> SharedThreadOut:
    t = (
        (await s.scalars(select(Thread).where(Thread.share_token == token))).first()
        if len(token) <= 32
        else None
    )
    # private と存在しないものは区別しない（R4）
    if t is None or t.visibility == "private":
        raise not_found("共有されたスレッドが見つかりません")
    if t.visibility == "org" and p is None:
        raise ApiError(401, "unauthenticated", "このスレッドを見るにはログインが必要です")
    msgs = list(
        await s.scalars(
            select(Message)
            .where(Message.thread_id == t.id, Message.status.in_(("completed", "cancelled")))
            .order_by(Message.ordinal)
        )
    )
    readable = await _readable_documents(s, p, msgs)
    return SharedThreadOut(
        title=t.title,
        visibility=t.visibility,  # type: ignore[arg-type]
        messages=[
            SharedMessage(
                query=m.query,
                answer=m.answer_text,
                created_at=m.created_at,
                sources=shared_sources(m.citation_map, m.sources, readable),
                has_image=_image_out(m.request) is not None,
            )
            for m in msgs
        ],
    )
