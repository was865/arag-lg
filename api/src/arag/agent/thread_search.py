"""スレッドの検索（specs/022 R1）。題名・質問・回答の本文から、空白で区切った語をすべて含むスレッドを探す。"""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import ColumnElement, and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from arag.db.models import Message, Thread

Match = Literal["title", "query", "answer"]
SNIPPET_CHARS = 80
MAX_TERMS = 8


@dataclass(frozen=True, slots=True)
class Hit:
    thread: Thread
    match: Match
    snippet: str
    message_id: str | None


def terms_of(q: str) -> list[str]:
    """空白（全角を含む）で区切った語。重複は除き、多すぎる語は切る。"""
    out: list[str] = []
    for t in q.split():
        if t.casefold() not in (x.casefold() for x in out):
            out.append(t)
    return out[:MAX_TERMS]


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def snippet(text: str, term: str, width: int = SNIPPET_CHARS) -> str:
    """語の前後を切り出す（改行は空白にし、切ったところに … を付ける）。"""
    flat = " ".join(text.split())
    i = flat.casefold().find(term.casefold())
    if i < 0 or len(flat) <= width:
        return flat[:width] + ("…" if len(flat) > width else "")
    start = max(0, min(i - width // 3, len(flat) - width))
    end = start + width
    return ("…" if start > 0 else "") + flat[start:end] + ("…" if end < len(flat) else "")


def _contains_all(text: str, terms: list[str]) -> bool:
    t = text.casefold()
    return all(x.casefold() in t for x in terms)


def _contains_any(text: str, terms: list[str]) -> str | None:
    t = text.casefold()
    return next((x for x in terms if x.casefold() in t), None)


async def search_threads(s: AsyncSession, user_id: str, q: str, limit: int) -> list[Hit]:
    terms = terms_of(q)
    if not terms:
        return []
    conds: list[ColumnElement[bool]] = []
    for term in terms:
        p = _like(term)
        in_messages = exists().where(
            Message.thread_id == Thread.id,
            or_(Message.query.ilike(p, escape="\\"), Message.answer_text.ilike(p, escape="\\")),
        )
        conds.append(or_(Thread.title.ilike(p, escape="\\"), in_messages))
    threads = list(
        await s.scalars(
            select(Thread)
            .where(Thread.user_id == user_id, and_(*conds))
            .order_by(Thread.updated_at.desc())
            .limit(limit)
        )
    )
    if not threads:
        return []
    msgs: dict[object, list[Message]] = {}
    rows = await s.scalars(
        select(Message).where(Message.thread_id.in_([t.id for t in threads])).order_by(Message.ordinal)
    )
    for m in rows:
        msgs.setdefault(m.thread_id, []).append(m)
    return [_hit(t, msgs.get(t.id, []), terms) for t in threads]


def _hit(t: Thread, msgs: list[Message], terms: list[str]) -> Hit:
    if _contains_all(t.title, terms):
        return Hit(t, "title", t.title, None)
    # 質問を先に見る（短く、利用者の言葉なので見分けやすい）。語を多く含むメッセージを選ぶ
    for field in ("query", "answer"):
        best: tuple[int, Message, str] | None = None
        for m in msgs:
            text = m.query if field == "query" else m.answer_text
            n = sum(1 for x in terms if x.casefold() in text.casefold())
            first = _contains_any(text, terms)
            if first and (best is None or n > best[0]):
                best = (n, m, first)
        if best is not None:
            _, m, first = best
            text = m.query if field == "query" else m.answer_text
            return Hit(t, field, snippet(text, first), str(m.id))
    return Hit(t, "title", t.title, None)
