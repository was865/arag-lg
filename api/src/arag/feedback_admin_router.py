"""技術者への報告（フィードバックに過程を付ける。specs/028 R13〜R17）。管理者だけが読める。"""

import base64
import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select

from arag.agent.router import MessageOut, message_out
from arag.audit import AuditEvent
from arag.db.models import Message, MessageFeedback, Thread
from arag.deps import CtxDep
from arag.errors import ApiError

router = APIRouter(tags=["feedback-admin"])

PREVIEW = 80

Rating = Literal["up", "down"]
Status = Literal["open", "resolved"]


class FeedbackRow(BaseModel):
    id: uuid.UUID
    message_id: uuid.UUID
    rating: Rating
    reason_tags: list[str]
    comment: str | None
    query: str
    model_id: str | None
    no_answer_reason: str | None
    status: Status
    user_id: str
    created_at: datetime
    updated_at: datetime


class FeedbackPage(BaseModel):
    items: list[FeedbackRow]
    next_cursor: str | None
    open_count: int


class FeedbackDetail(BaseModel):
    id: uuid.UUID
    rating: Rating
    reason_tags: list[str]
    comment: str | None
    status: Status
    user_id: str
    resolved_by: str | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    thread_id: uuid.UUID
    thread_title: str
    message: MessageOut


def _require_admin(ctx: CtxDep) -> None:
    if not ctx.principal.is_admin:
        raise ApiError(403, "forbidden", "管理者だけが使えます")


def _encode(f: MessageFeedback) -> str:
    return base64.urlsafe_b64encode(f"{f.updated_at.isoformat()}|{f.id}".encode()).decode()


def _decode(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        ts, rid = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(ts), uuid.UUID(rid)
    except Exception as e:
        raise ApiError(422, "invalid_cursor", "カーソルが正しくありません") from e


def _short(text: str | None) -> str | None:
    if text is None:
        return None
    return text if len(text) <= PREVIEW else text[: PREVIEW - 1] + "…"


@router.get("/v1/admin/feedback", response_model=FeedbackPage)
async def list_feedback(
    ctx: CtxDep,
    rating: Rating | None = None,
    status: Status | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> FeedbackPage:
    """報告の一覧（新しい順。質問とコメントは先頭 80 字）。open_count は未対応の「良くない」の件数。"""
    _require_admin(ctx)
    q = select(MessageFeedback, Message).join(Message, Message.id == MessageFeedback.message_id)
    if rating:
        q = q.where(MessageFeedback.rating == rating)
    if status:
        q = q.where(MessageFeedback.status == status)
    if cursor:
        ts, rid = _decode(cursor)
        q = q.where(
            or_(
                MessageFeedback.updated_at < ts,
                and_(MessageFeedback.updated_at == ts, MessageFeedback.id < rid),
            )
        )
    q = q.order_by(MessageFeedback.updated_at.desc(), MessageFeedback.id.desc()).limit(limit + 1)
    rows = [(f, m) for f, m in await ctx.session.execute(q)]
    items = [
        FeedbackRow(
            id=f.id,
            message_id=m.id,
            rating=f.rating,  # type: ignore[arg-type]
            reason_tags=list(f.reason_tags or []),
            comment=_short(f.comment),
            query=_short(m.query) or "",
            model_id=m.model_id,
            no_answer_reason=m.no_answer_reason,
            status=f.status,  # type: ignore[arg-type]
            user_id=f.user_id,
            created_at=f.created_at,
            updated_at=f.updated_at,
        )
        for f, m in rows[:limit]
    ]
    open_count = await ctx.session.scalar(
        select(func.count())
        .select_from(MessageFeedback)
        .where(MessageFeedback.rating == "down", MessageFeedback.status == "open")
    )
    return FeedbackPage(
        items=items,
        next_cursor=_encode(rows[limit - 1][0]) if len(rows) > limit else None,
        open_count=open_count or 0,
    )


async def _load(ctx: CtxDep, feedback_id: uuid.UUID) -> tuple[MessageFeedback, Message, Thread]:
    row = (
        await ctx.session.execute(
            select(MessageFeedback, Message, Thread)
            .join(Message, Message.id == MessageFeedback.message_id)
            .join(Thread, Thread.id == Message.thread_id)
            .where(MessageFeedback.id == feedback_id)
        )
    ).first()
    if row is None:
        raise ApiError(404, "not_found", "報告が見つかりません")
    f, m, t = row
    return f, m, t


def _detail(f: MessageFeedback, m: Message, t: Thread) -> FeedbackDetail:
    return FeedbackDetail(
        id=f.id,
        rating=f.rating,  # type: ignore[arg-type]
        reason_tags=list(f.reason_tags or []),
        comment=f.comment,
        status=f.status,  # type: ignore[arg-type]
        user_id=f.user_id,
        resolved_by=f.resolved_by,
        resolved_at=f.resolved_at,
        created_at=f.created_at,
        updated_at=f.updated_at,
        thread_id=t.id,
        thread_title=t.title,
        message=message_out(m, f),
    )


@router.get("/v1/admin/feedback/{feedback_id}", response_model=FeedbackDetail)
async def get_feedback(feedback_id: uuid.UUID, ctx: CtxDep) -> FeedbackDetail:
    """報告とそのターン（質問・回答・出典・ステップの全記録・実行の情報）。読むだけ。"""
    _require_admin(ctx)
    return _detail(*await _load(ctx, feedback_id))


async def _set_status(ctx: CtxDep, feedback_id: uuid.UUID, status: Status) -> FeedbackDetail:
    _require_admin(ctx)
    f, m, t = await _load(ctx, feedback_id)
    if status == "resolved":
        f.status, f.resolved_by, f.resolved_at = "resolved", ctx.principal.user_id, datetime.now(UTC)
    else:
        f.status, f.resolved_by, f.resolved_at = "open", None, None
    await ctx.audit(
        AuditEvent(
            action="feedback.resolve" if status == "resolved" else "feedback.reopen",
            resource_type="feedback",
            resource_id=str(f.id),
            detail={"message_id": str(m.id), "rating": f.rating},
        )
    )
    await ctx.session.commit()
    return _detail(f, m, t)


@router.post("/v1/admin/feedback/{feedback_id}/resolve", response_model=FeedbackDetail)
async def resolve_feedback(feedback_id: uuid.UUID, ctx: CtxDep) -> FeedbackDetail:
    return await _set_status(ctx, feedback_id, "resolved")


@router.post("/v1/admin/feedback/{feedback_id}/reopen", response_model=FeedbackDetail)
async def reopen_feedback(feedback_id: uuid.UUID, ctx: CtxDep) -> FeedbackDetail:
    return await _set_status(ctx, feedback_id, "open")
