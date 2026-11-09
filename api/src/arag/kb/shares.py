"""共有 KB の共有リストの読み書き（specs/024 R4〜R9・R17）。"""

import dataclasses
import uuid

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from arag.audit import AuditEvent
from arag.db.models import Department, DepartmentMember, KbShare, KnowledgeBase
from arag.deps import Ctx
from arag.errors import ApiError
from arag.kb.access import ShareRole, SubjectType, load_access

SUBJECT_ORDER = {"everyone": 0, "department": 1, "user": 2}
MAX_SHARES = 200


class ShareIn(BaseModel):
    subject_type: SubjectType
    subject_id: str = Field(default="", max_length=64, description="部門の id か user_id。全員なら空")
    role: ShareRole

    @model_validator(mode="after")
    def _check(self) -> "ShareIn":
        if self.subject_type == "everyone":
            self.subject_id = ""
        elif not self.subject_id.strip():
            raise ValueError("部門か人を指定してください")
        return self

    @property
    def key(self) -> tuple[str, str]:
        return (self.subject_type, self.subject_id)


class ShareOut(BaseModel):
    subject_type: SubjectType
    subject_id: str
    role: ShareRole


def bad_shares(message: str) -> ApiError:
    return ApiError(400, "invalid_shares", message)


async def reloaded(ctx: Ctx) -> Ctx:
    """共有リストを変えたあとの役割で作り直した Ctx。"""
    return dataclasses.replace(ctx, access=await load_access(ctx.session, ctx.principal))


async def department_exists(session: AsyncSession, dept_id: str) -> bool:
    try:
        did = uuid.UUID(dept_id)
    except ValueError:
        return False
    return await session.get(Department, did) is not None


async def kbs_shared_with_everyone(session: AsyncSession, kb_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    if not kb_ids:
        return set()
    rows = await session.scalars(
        select(KbShare.kb_id).where(KbShare.kb_id.in_(kb_ids), KbShare.subject_type == "everyone")
    )
    return set(rows)


async def list_shares(session: AsyncSession, kb_id: uuid.UUID) -> list[ShareOut]:
    rows = await session.scalars(select(KbShare).where(KbShare.kb_id == kb_id))
    out = [ShareOut(subject_type=r.subject_type, subject_id=r.subject_id, role=r.role) for r in rows]  # type: ignore[arg-type]
    return sorted(out, key=lambda x: (SUBJECT_ORDER[x.subject_type], x.subject_id))


async def members_of_departments(session: AsyncSession, dept_ids: list[str]) -> dict[str, list[str]]:
    ids = [uuid.UUID(d) for d in dept_ids]
    out: dict[str, list[str]] = {d: [] for d in dept_ids}
    if not ids:
        return out
    rows = await session.execute(
        select(DepartmentMember.department_id, DepartmentMember.user_id)
        .where(DepartmentMember.department_id.in_(ids))
        .order_by(DepartmentMember.user_id)
    )
    for d, u in rows:
        out[str(d)].append(u)
    return out


async def _validate(session: AsyncSession, items: list[ShareIn]) -> None:
    if len(items) > MAX_SHARES:
        raise bad_shares(f"共有リストは {MAX_SHARES} 行までです")
    keys = [i.key for i in items]
    if len(set(keys)) != len(keys):
        raise bad_shares("同じ相手が 2 回あります")
    if any(i.subject_type == "everyone" and i.role != "viewer" for i in items):
        raise bad_shares("全員には閲覧だけを付けられます")
    if not any(i.role == "manager" for i in items):
        raise bad_shares("管理できる人（部門）を 1 つ以上残してください")
    for i in items:
        if i.subject_type == "department" and not await department_exists(session, i.subject_id):
            raise bad_shares("指定した部門が見つかりません")


async def replace_shares(ctx: Ctx, kb: KnowledgeBase, items: list[ShareIn], *, audit: bool = True) -> None:
    """共有リストを丸ごと置き換え、差分を監査に残す（呼ぶ側で commit）。"""
    await _validate(ctx.session, items)
    before = {
        (r.subject_type, r.subject_id): r
        for r in await ctx.session.scalars(select(KbShare).where(KbShare.kb_id == kb.id))
    }
    after = {i.key: i for i in items}
    events: list[tuple[str, str, str, str | None, str | None]] = []
    for key, row in before.items():
        if key not in after:
            await ctx.session.delete(row)
            events.append(("kb.share_remove", key[0], key[1], row.role, None))
        elif row.role != after[key].role:
            events.append(("kb.share_change", key[0], key[1], row.role, after[key].role))
            row.role = after[key].role
    for key, i in after.items():
        if key not in before:
            ctx.session.add(
                KbShare(
                    id=uuid.uuid4(),
                    kb_id=kb.id,
                    subject_type=i.subject_type,
                    subject_id=i.subject_id,
                    role=i.role,
                    created_by=ctx.principal.user_id,
                )
            )
            events.append(("kb.share_add", key[0], key[1], None, i.role))
    await ctx.session.flush()
    if audit:
        for action, st, sid, old, new in events:
            await ctx.audit(
                AuditEvent(
                    action=action,
                    resource_type="kb",
                    resource_id=str(kb.id),
                    detail={"subject_type": st, "subject_id": sid, "from": old, "to": new},
                )
            )


async def remove_department_shares(ctx: Ctx, dept_id: str) -> None:
    rows = list(
        await ctx.session.scalars(
            select(KbShare).where(KbShare.subject_type == "department", KbShare.subject_id == dept_id)
        )
    )
    for r in rows:
        await ctx.audit(
            AuditEvent(
                action="kb.share_remove",
                resource_type="kb",
                resource_id=str(r.kb_id),
                detail={"subject_type": "department", "subject_id": dept_id, "from": r.role, "to": None},
            )
        )
    await ctx.session.execute(
        delete(KbShare).where(KbShare.subject_type == "department", KbShare.subject_id == dept_id)
    )
