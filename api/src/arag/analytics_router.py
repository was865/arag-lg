"""利用状況の分析（specs/012-analytics）。owner・admin だけが見られる。"""

from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import Date, cast, func, select

from arag.db.models import Citation, Message, MessageFeedback, Thread
from arag.deps import CtxDep
from arag.errors import ApiError

router = APIRouter(tags=["analytics"])

PERIODS = (7, 30, 90)


class Totals(BaseModel):
    questions: int
    users: int
    answered_rate: float | None
    median_duration_ms: int | None
    tokens_in: int
    tokens_out: int


class Daily(BaseModel):
    date: date
    questions: int
    no_answer: int


class ReasonCount(BaseModel):
    reason: str
    count: int


class Gap(BaseModel):
    query: str
    reason: str
    created_at: datetime


class TagCount(BaseModel):
    tag: str
    count: int


class FeedbackSummary(BaseModel):
    up: int
    down: int
    top_down_tags: list[TagCount]


class TopDocument(BaseModel):
    title: str
    citations: int
    answers: int


class AnalyticsOut(BaseModel):
    days: int
    since: datetime
    totals: Totals
    daily: list[Daily]
    no_answer_reasons: list[ReasonCount]
    recent_gaps: list[Gap]
    feedback: FeedbackSummary
    top_documents: list[TopDocument]


@router.get("/v1/admin/analytics", response_model=AnalyticsOut)
async def analytics(ctx: CtxDep, days: Annotated[int, Query()] = 30) -> AnalyticsOut:
    if not ctx.principal.is_admin:
        raise ApiError(403, "forbidden", "管理者だけが使えます")
    if days not in PERIODS:
        raise ApiError(422, "invalid_days", "期間は 7・30・90 日から選んでください")
    s = ctx.session
    today = datetime.now(UTC).date()
    first = today - timedelta(days=days - 1)
    since = datetime.combine(first, time(), tzinfo=UTC)
    in_window = Message.created_at >= since
    no_answer = Message.no_answer_reason.is_not(None)

    t = (
        await s.execute(
            select(
                func.count(),
                func.count(func.distinct(Thread.user_id)),
                func.count().filter(Message.status == "completed"),
                func.count().filter(Message.status == "completed", Message.no_answer_reason.is_(None)),
                func.percentile_cont(0.5).within_group(Message.duration_ms),
                func.coalesce(func.sum(Message.tokens_in), 0),
                func.coalesce(func.sum(Message.tokens_out), 0),
            )
            .select_from(Message)
            .join(Thread, Thread.id == Message.thread_id)
            .where(in_window)
        )
    ).one()
    questions, users, completed, answered, median, tok_in, tok_out = t

    day = cast(func.timezone("UTC", Message.created_at), Date)
    per_day = {
        d: (n, gaps)
        for d, n, gaps in await s.execute(
            select(day, func.count(), func.count().filter(no_answer)).where(in_window).group_by(day)
        )
    }
    daily = [
        Daily(date=d, questions=per_day.get(d, (0, 0))[0], no_answer=per_day.get(d, (0, 0))[1])
        for d in (first + timedelta(days=i) for i in range(days))
    ]

    reasons = [
        ReasonCount(reason=r or "", count=n)
        for r, n in await s.execute(
            select(Message.no_answer_reason, func.count())
            .where(in_window, no_answer)
            .group_by(Message.no_answer_reason)
            .order_by(func.count().desc(), Message.no_answer_reason)
        )
    ]
    gaps = [
        Gap(query=q, reason=r or "", created_at=c)
        for q, r, c in await s.execute(
            select(Message.query, Message.no_answer_reason, Message.created_at)
            .where(in_window, no_answer)
            .order_by(Message.created_at.desc())
            .limit(20)
        )
    ]

    fb = list(
        await s.execute(
            select(MessageFeedback.rating, MessageFeedback.reason_tags)
            .join(Message, Message.id == MessageFeedback.message_id)
            .where(in_window)
        )
    )
    tags = Counter(tag for rating, ts in fb if rating == "down" for tag in ts)
    feedback = FeedbackSummary(
        up=sum(1 for r, _ in fb if r == "up"),
        down=sum(1 for r, _ in fb if r == "down"),
        top_down_tags=[
            TagCount(tag=k, count=v) for k, v in sorted(tags.items(), key=lambda x: (-x[1], x[0]))[:5]
        ],
    )

    cites = func.count()
    top = [
        TopDocument(title=title, citations=n, answers=m)
        for title, n, m in await s.execute(
            select(Citation.document_title, cites, func.count(func.distinct(Citation.message_id)))
            .join(Message, Message.id == Citation.message_id)
            .where(in_window)
            .group_by(Citation.document_title)
            .order_by(cites.desc(), Citation.document_title)
            .limit(10)
        )
    ]

    return AnalyticsOut(
        days=days,
        since=since,
        totals=Totals(
            questions=questions,
            users=users,
            answered_rate=(answered / completed) if completed else None,
            median_duration_ms=round(median) if median is not None else None,
            tokens_in=int(tok_in),
            tokens_out=int(tok_out),
        ),
        daily=daily,
        no_answer_reasons=reasons,
        recent_gaps=gaps,
        feedback=feedback,
        top_documents=top,
    )
