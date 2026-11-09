"""監査ログの一覧と、Web（メンバー管理）からの書き込み（specs/011-audit-log）。"""

import base64
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select

from arag.audit import AuditEvent
from arag.db.models import AuditLog
from arag.deps import CtxDep
from arag.errors import ApiError

router = APIRouter(tags=["audit"])

# Web のサーバが書ける操作（R3）。ほかの操作は API が自分で書く
WEB_ACTIONS = frozenset(
    {"member.invite", "member.role", "member.ban", "member.unban", "member.resend_invite"}
)


class AuditOut(BaseModel):
    id: uuid.UUID
    ts: datetime
    actor_id: str | None
    actor_email: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    result: str
    ip: str | None
    detail: dict[str, Any] | None


class AuditPage(BaseModel):
    items: list[AuditOut]
    next_cursor: str | None


class AuditIn(BaseModel):
    action: str = Field(max_length=64)
    resource_id: str | None = Field(default=None, max_length=128)
    detail: dict[str, Any] | None = None


def _require_admin(ctx: CtxDep) -> None:
    if not ctx.principal.is_admin:
        raise ApiError(403, "forbidden", "管理者だけが使えます")


def _encode(row: AuditLog) -> str:
    return base64.urlsafe_b64encode(f"{row.ts.isoformat()}|{row.id}".encode()).decode()


def _decode(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        ts, rid = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(ts), uuid.UUID(rid)
    except Exception as e:
        raise ApiError(422, "invalid_cursor", "カーソルが正しくありません") from e


def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/v1/admin/audit", response_model=AuditPage)
async def list_audit(
    ctx: CtxDep,
    action: Annotated[str | None, Query(max_length=64)] = None,
    actor: Annotated[str | None, Query(max_length=320)] = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditPage:
    _require_admin(ctx)
    q = select(AuditLog)
    if action:
        q = q.where(AuditLog.action.startswith(action, autoescape=True))
    if actor:
        pat = f"%{_escape_like(actor.lower())}%"
        q = q.where(
            or_(
                AuditLog.actor_id == actor,
                func.lower(AuditLog.actor_email).like(pat, escape="\\"),
            )
        )
    if from_ is not None:
        q = q.where(AuditLog.ts >= from_)
    if to is not None:
        q = q.where(AuditLog.ts < to)
    if cursor:
        ts, rid = _decode(cursor)
        q = q.where(or_(AuditLog.ts < ts, and_(AuditLog.ts == ts, AuditLog.id < rid)))
    rows = list(
        await ctx.session.scalars(q.order_by(AuditLog.ts.desc(), AuditLog.id.desc()).limit(limit + 1))
    )
    items = [AuditOut.model_validate(r, from_attributes=True) for r in rows[:limit]]
    return AuditPage(items=items, next_cursor=_encode(rows[limit - 1]) if len(rows) > limit else None)


@router.post("/v1/admin/audit", status_code=201)
async def write_web_audit(body: AuditIn, ctx: CtxDep) -> dict[str, bool]:
    _require_admin(ctx)
    if body.action not in WEB_ACTIONS:
        raise ApiError(422, "invalid_action", "記録できない操作です")
    await ctx.audit(
        AuditEvent(action=body.action, resource_type="user", resource_id=body.resource_id, detail=body.detail)
    )
    await ctx.session.commit()
    return {"ok": True}
