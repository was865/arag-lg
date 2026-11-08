"""監査ログ（追記専用。specs/003-ingestion R36）。"""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from arag.auth.principal import Principal
from arag.db.models import AuditLog


@dataclass(frozen=True, slots=True)
class AuditEvent:
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    result: str = "ok"  # ok / denied / error
    detail: dict[str, Any] | None = field(default=None)


def build_audit_row(
    event: AuditEvent,
    *,
    principal: Principal | None = None,
    request_id: str | None = None,
    ip: str | None = None,
) -> dict[str, Any]:
    return {
        "actor_id": principal.user_id if principal else None,
        "actor_email": principal.email if principal else None,
        "action": event.action,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "result": event.result,
        "ip": ip,
        "request_id": request_id,
        "detail": event.detail,
    }


async def write_audit(
    session: AsyncSession,
    event: AuditEvent,
    *,
    principal: Principal | None = None,
    request_id: str | None = None,
    ip: str | None = None,
) -> None:
    """呼び出し側のトランザクションに乗せて書く（本体の変更と同時に確定する）。"""
    await session.execute(
        insert(AuditLog).values(build_audit_row(event, principal=principal, request_id=request_id, ip=ip))
    )
