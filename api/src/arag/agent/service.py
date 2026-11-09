"""スレッドと run の作成・取得（specs/005-agent R1〜R6・R26・R27）。"""

import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from arag.agent.config import AgentCfg
from arag.agent.query_image import DEFAULT_QUERY
from arag.auth.principal import Principal
from arag.db.models import Message, Run, Thread
from arag.errors import ApiError, not_found

RUNS_CHANNEL = "agent_runs"
QUERY_MAX = 4000
TITLE_MAX = 40
ACTIVE = ("queued", "running")


class QueryImageIn(BaseModel):
    # 元画像 8MB の base64 ＋ data URL の接頭辞まで
    data: str = Field(min_length=1, max_length=11_000_000)


class RunRequest(BaseModel):
    query: str
    model_id: str | None = None
    kb_ids: list[uuid.UUID] | None = None
    include_archived: bool = False
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)
    agent_cfg: dict[str, Any] | None = None
    from_message_id: uuid.UUID | None = None
    # 質問に添える画像（specs/017）。base64（data URL も可）。検証・縮小は API で行う
    image: QueryImageIn | None = None

    @field_validator("query")
    @classmethod
    def _query(cls, v: str) -> str:
        v = v.strip()
        if len(v) > QUERY_MAX:
            raise ValueError(f"質問は {QUERY_MAX} 文字以内にしてください")
        return v

    @model_validator(mode="after")
    def _query_or_image(self) -> "RunRequest":
        if not self.query:
            if self.image is None:
                raise ValueError("質問を入力してください")
            self.query = DEFAULT_QUERY  # 画像だけで送ったとき（R7）
        return self


def title_from(query: str) -> str:
    line = " ".join(query.split())
    return line[:TITLE_MAX] + ("…" if len(line) > TITLE_MAX else "")


async def get_thread(session: AsyncSession, p: Principal, thread_id: uuid.UUID) -> Thread:
    t = await session.get(Thread, thread_id)
    if t is None or t.user_id != p.user_id:
        raise not_found("スレッドが見つかりません")
    return t


async def get_run(session: AsyncSession, p: Principal, run_id: uuid.UUID) -> Run:
    r = await session.get(Run, run_id)
    if r is None or r.user_id != p.user_id:
        raise not_found("実行が見つかりません")
    return r


async def active_run(session: AsyncSession, thread_id: uuid.UUID) -> Run | None:
    return (
        await session.scalars(select(Run).where(Run.thread_id == thread_id, Run.status.in_(ACTIVE)))
    ).first()


async def create_run(
    session: AsyncSession,
    p: Principal,
    thread: Thread | None,
    req: RunRequest,
    model_id: str,
    image: dict[str, Any] | None = None,
) -> tuple[Thread, Run]:
    """run を queued で作る（コミットは呼び出し側）。分岐なら対象ターンの位置と checkpoint を覚える。"""
    if thread is None:
        thread = Thread(id=uuid.uuid4(), user_id=p.user_id, title=title_from(req.query))
        session.add(thread)
        await session.flush()
    branch_ckpt: str | None = None
    if req.from_message_id is not None:
        msg = await session.get(Message, req.from_message_id)
        if msg is None or msg.thread_id != thread.id:
            raise not_found("分岐元のメッセージが見つかりません")
        ordinal, branch_ckpt, branch = msg.ordinal, msg.checkpoint_id, True
    else:
        last = await session.scalar(select(func.max(Message.ordinal)).where(Message.thread_id == thread.id))
        ordinal, branch = (last or 0) + 1, False
    cfg = AgentCfg.clamped(req.agent_cfg)
    run = Run(
        id=uuid.uuid4(),
        thread_id=thread.id,
        message_id=uuid.uuid4(),
        user_id=p.user_id,
        status="queued",
        model_id=model_id,
        request={
            "query": req.query,
            "kb_ids": [str(k) for k in req.kb_ids] if req.kb_ids is not None else None,
            "document_ids": [str(d) for d in req.document_ids] if req.document_ids is not None else None,
            "include_archived": req.include_archived,
            "agent_cfg": cfg.as_dict(),
            "ordinal": ordinal,
            "branch": branch,
            "branch_checkpoint_id": branch_ckpt,
            "principal": {"user_id": p.user_id, "role": p.role, "email": p.email},
            **({"image": image} if image else {}),
        },
    )
    try:
        async with session.begin_nested():
            session.add(run)
    except IntegrityError as e:
        raise ApiError(409, "run_in_progress", "このスレッドでは回答を生成中です") from e
    await session.execute(text("SELECT pg_notify(:ch, :id)"), {"ch": RUNS_CHANNEL, "id": str(run.id)})
    return thread, run


async def delete_messages_from(session: AsyncSession, thread_id: uuid.UUID, ordinal: int) -> None:
    await session.execute(delete(Message).where(Message.thread_id == thread_id, Message.ordinal >= ordinal))
