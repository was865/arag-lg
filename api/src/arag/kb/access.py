"""利用者ごとの KB の役割（specs/024）。

共有 KB の権限は共有リスト（kb_shares）の行からだけ来る。1 人に複数の行が当たれば、いちばん強い役割。
admin でも、共有リストに当たる行が無ければ中身は読めない（Q1 案 A）。
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from arag.auth.principal import Principal
from arag.db.models import DepartmentMember, KbShare

ShareRole = Literal["viewer", "editor", "manager"]
SubjectType = Literal["everyone", "department", "user"]
RANK: dict[str, int] = {"viewer": 1, "editor": 2, "manager": 3}
SHARE_ROLES: tuple[ShareRole, ...] = ("viewer", "editor", "manager")


def stronger(a: str | None, b: str | None) -> str | None:
    if a is None:
        return b
    if b is None:
        return a
    return a if RANK[a] >= RANK[b] else b


@dataclass(frozen=True, slots=True)
class Access:
    principal: Principal
    department_ids: frozenset[str] = frozenset()
    managed_department_ids: frozenset[str] = frozenset()
    kb_roles: Mapping[uuid.UUID, ShareRole] = field(default_factory=dict)

    @property
    def user_id(self) -> str:
        return self.principal.user_id

    @property
    def is_admin(self) -> bool:
        return self.principal.is_admin

    @property
    def readable_org_kb_ids(self) -> list[uuid.UUID]:
        return list(self.kb_roles)

    def org_kb_ids_at_least(self, role: ShareRole) -> list[uuid.UUID]:
        return [k for k, r in self.kb_roles.items() if RANK[r] >= RANK[role]]


def share_matches(a_user_id: str, department_ids: frozenset[str]) -> ColumnElement[bool]:
    """共有リストの行のうち、この人に当たるもの（SQL の条件）。"""
    return or_(
        KbShare.subject_type == "everyone",
        and_(KbShare.subject_type == "user", KbShare.subject_id == a_user_id),
        and_(KbShare.subject_type == "department", KbShare.subject_id.in_(sorted(department_ids))),
    )


async def load_access(session: AsyncSession, p: Principal) -> Access:
    rows = (
        await session.execute(
            select(DepartmentMember.department_id, DepartmentMember.role).where(
                DepartmentMember.user_id == p.user_id
            )
        )
    ).all()
    depts = frozenset(str(d) for d, _ in rows)
    managed = frozenset(str(d) for d, r in rows if r == "manager")
    roles: dict[uuid.UUID, ShareRole] = {}
    shares = await session.execute(select(KbShare.kb_id, KbShare.role).where(share_matches(p.user_id, depts)))
    for kb_id, role in shares.all():
        best = stronger(roles.get(kb_id), role)
        if best is not None:
            roles[kb_id] = best  # type: ignore[assignment]
    return Access(principal=p, department_ids=depts, managed_department_ids=managed, kb_roles=roles)
