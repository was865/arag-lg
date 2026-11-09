"""部門・共有リスト・人の理由の API（specs/024）。"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Response, status
from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from arag.audit import AuditEvent
from arag.db.models import Department, DepartmentMember, KbShare, KnowledgeBase
from arag.deps import CtxDep
from arag.errors import ApiError, not_found
from arag.kb import permissions as perm
from arag.kb import service, shares
from arag.kb.access import ShareRole, share_matches, stronger
from arag.kb.shares import ShareIn, ShareOut

router = APIRouter(tags=["access"])

DeptRole = Literal["member", "manager"]
UserId = Annotated[str, Path(min_length=1, max_length=64)]


def _dept_name(v: str) -> str:
    v = v.strip()
    if not v or len(v) > 100:
        raise ValueError("部門名は 1〜100 文字にしてください")
    return v


DeptName = Annotated[str, AfterValidator(_dept_name)]


class DepartmentOut(BaseModel):
    id: uuid.UUID
    name: str
    member_count: int
    my_role: DeptRole | None = Field(default=None, description="自分の役割（入っていなければ null）")


class DepartmentIn(BaseModel):
    name: DeptName


class DeptMemberOut(BaseModel):
    user_id: str
    role: DeptRole


class DeptMemberIn(BaseModel):
    role: DeptRole = "member"


class SharesOut(BaseModel):
    shares: list[ShareOut]
    department_members: dict[str, list[str]] = Field(description="共有リストにある部門の user_id")
    can_manage: bool


class SharesIn(BaseModel):
    shares: list[ShareIn]


class AccessReason(BaseModel):
    subject_type: Literal["everyone", "department", "user"]
    subject_id: str
    role: ShareRole


class UserKbAccess(BaseModel):
    kb_id: uuid.UUID
    kb_name: str
    role: ShareRole
    reasons: list[AccessReason]


def _require_admin(ctx: CtxDep) -> None:
    if not ctx.principal.is_admin:
        raise ApiError(403, "forbidden", "管理者だけが使えます")


def _dept_conflict() -> ApiError:
    return ApiError(409, "department_name_conflict", "同じ名前の部門があります")


async def _department(ctx: CtxDep, dept_id: uuid.UUID) -> Department:
    d = await ctx.session.get(Department, dept_id)
    if d is None:
        raise not_found()
    return d


# ---------------------------------------------------------------- 部門（R1〜R3）


@router.get("/v1/departments", response_model=list[DepartmentOut])
async def list_departments(ctx: CtxDep) -> list[DepartmentOut]:
    """部門の一覧（共有リストで選ぶため、ログインしていれば誰でも見られる）。"""
    count = (
        select(func.count())
        .select_from(DepartmentMember)
        .where(DepartmentMember.department_id == Department.id)
        .scalar_subquery()
    )
    mine = (
        select(DepartmentMember.role)
        .where(
            DepartmentMember.department_id == Department.id, DepartmentMember.user_id == ctx.principal.user_id
        )
        .scalar_subquery()
    )
    rows = await ctx.session.execute(select(Department, count, mine).order_by(Department.name))
    return [DepartmentOut(id=d.id, name=d.name, member_count=int(n), my_role=r) for d, n, r in rows]


@router.post("/v1/departments", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
async def create_department(body: DepartmentIn, ctx: CtxDep) -> DepartmentOut:
    _require_admin(ctx)
    d = Department(id=uuid.uuid4(), name=body.name)
    ctx.session.add(d)
    try:
        await ctx.session.flush()
    except IntegrityError as e:
        await ctx.session.rollback()
        raise _dept_conflict() from e
    await ctx.audit(
        AuditEvent(
            action="department.create",
            resource_type="department",
            resource_id=str(d.id),
            detail={"label": d.name},
        )
    )
    await ctx.session.commit()
    return DepartmentOut(id=d.id, name=d.name, member_count=0)


@router.patch("/v1/departments/{dept_id}", response_model=DepartmentOut)
async def rename_department(dept_id: uuid.UUID, body: DepartmentIn, ctx: CtxDep) -> DepartmentOut:
    _require_admin(ctx)
    d = await _department(ctx, dept_id)
    before = d.name
    d.name = body.name
    try:
        await ctx.session.flush()
    except IntegrityError as e:
        await ctx.session.rollback()
        raise _dept_conflict() from e
    await ctx.audit(
        AuditEvent(
            action="department.rename",
            resource_type="department",
            resource_id=str(d.id),
            detail={"label": d.name, "from": before, "to": d.name},
        )
    )
    await ctx.session.commit()
    n = await ctx.session.scalar(
        select(func.count()).select_from(DepartmentMember).where(DepartmentMember.department_id == d.id)
    )
    return DepartmentOut(id=d.id, name=d.name, member_count=int(n or 0))


@router.delete("/v1/departments/{dept_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_department(dept_id: uuid.UUID, ctx: CtxDep) -> Response:
    """部門を消す。その部門を指す共有リストの行も消える（監査に残す）。"""
    _require_admin(ctx)
    d = await _department(ctx, dept_id)
    await shares.remove_department_shares(ctx, str(d.id))
    await ctx.audit(
        AuditEvent(
            action="department.delete",
            resource_type="department",
            resource_id=str(d.id),
            detail={"label": d.name},
        )
    )
    await ctx.session.delete(d)
    await ctx.session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/v1/departments/{dept_id}/members", response_model=list[DeptMemberOut])
async def list_department_members(dept_id: uuid.UUID, ctx: CtxDep) -> list[DeptMemberOut]:
    await _department(ctx, dept_id)
    rows = await ctx.session.scalars(
        select(DepartmentMember)
        .where(DepartmentMember.department_id == dept_id)
        .order_by(DepartmentMember.user_id)
    )
    return [DeptMemberOut(user_id=m.user_id, role=m.role) for m in rows]  # type: ignore[arg-type]


def _can_edit_members(ctx: CtxDep, dept_id: uuid.UUID, *, target_role: str, current: str | None) -> None:
    """admin は何でも。部門管理者は自部門の「メンバー」の追加・削除だけ（R2）。"""
    if ctx.principal.is_admin:
        return
    if str(dept_id) not in ctx.access.managed_department_ids:
        raise ApiError(403, "forbidden", "この部門のメンバーを変える権限がありません")
    if target_role != "member" or current == "manager":
        raise ApiError(403, "forbidden", "部門管理者の指名・解除は管理者だけができます")


@router.put("/v1/departments/{dept_id}/members/{user_id}", response_model=DeptMemberOut)
async def put_department_member(
    dept_id: uuid.UUID, user_id: UserId, body: DeptMemberIn, ctx: CtxDep
) -> DeptMemberOut:
    dept = await _department(ctx, dept_id)
    m = await ctx.session.get(DepartmentMember, (dept_id, user_id))
    _can_edit_members(ctx, dept_id, target_role=body.role, current=m.role if m else None)
    if m is None:
        ctx.session.add(DepartmentMember(department_id=dept_id, user_id=user_id, role=body.role))
        action = "department.member_add"
    elif m.role != body.role:
        m.role = body.role
        action = "department.member_role"
    else:
        return DeptMemberOut(user_id=user_id, role=body.role)
    await ctx.audit(
        AuditEvent(
            action=action,
            resource_type="department",
            resource_id=str(dept_id),
            detail={"label": dept.name, "user_id": user_id, "role": body.role},
        )
    )
    await ctx.session.commit()
    return DeptMemberOut(user_id=user_id, role=body.role)


@router.delete("/v1/departments/{dept_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_department_member(dept_id: uuid.UUID, user_id: UserId, ctx: CtxDep) -> Response:
    dept = await _department(ctx, dept_id)
    m = await ctx.session.get(DepartmentMember, (dept_id, user_id))
    if m is None:
        raise not_found()
    _can_edit_members(ctx, dept_id, target_role="member", current=m.role)
    await ctx.session.delete(m)
    await ctx.audit(
        AuditEvent(
            action="department.member_remove",
            resource_type="department",
            resource_id=str(dept_id),
            detail={"label": dept.name, "user_id": user_id},
        )
    )
    await ctx.session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- 共有リスト（R4〜R8・R12）


async def _share_kb(ctx: CtxDep, kb_id: uuid.UUID) -> KnowledgeBase:
    kb = await service.get_kb_any(ctx.session, kb_id)
    if kb is None or kb.deleted_at is not None or not perm.can_view_shares(ctx.access, kb):
        raise not_found()
    return kb


async def _shares_out(ctx: CtxDep, kb: KnowledgeBase) -> SharesOut:
    items = await shares.list_shares(ctx.session, kb.id)
    depts = [s.subject_id for s in items if s.subject_type == "department"]
    return SharesOut(
        shares=items,
        department_members=await shares.members_of_departments(ctx.session, depts),
        can_manage=perm.can_manage_org_kb(ctx.access, kb),
    )


@router.get("/v1/kbs/{kb_id}/shares", response_model=SharesOut)
async def get_shares(kb_id: uuid.UUID, ctx: CtxDep) -> SharesOut:
    """共有リスト。読める人（誰に見えているかを知るため）と、管理できる人が見られる。"""
    return await _shares_out(ctx, await _share_kb(ctx, kb_id))


@router.put("/v1/kbs/{kb_id}/shares", response_model=SharesOut)
async def put_shares(kb_id: uuid.UUID, body: SharesIn, ctx: CtxDep) -> SharesOut:
    """共有リストを丸ごと置き換える（全員は閲覧だけ・管理が 1 行以上）。差分を監査に残す。"""
    kb = await _share_kb(ctx, kb_id)
    if not perm.can_manage_org_kb(ctx.access, kb):
        raise ApiError(403, "forbidden", "この知識ベースの共有を変える権限がありません")
    await shares.replace_shares(ctx, kb, body.shares)
    await ctx.session.commit()
    return await _shares_out(await shares.reloaded(ctx), kb)


# ---------------------------------------------------------------- 人の理由（R13）


@router.get("/v1/admin/users/{user_id}/access", response_model=list[UserKbAccess])
async def user_access(user_id: UserId, ctx: CtxDep) -> list[UserKbAccess]:
    """その人が見られる共有 KB と、どの行から来たか（admin だけ）。"""
    _require_admin(ctx)
    depts = frozenset(
        str(d)
        for d in await ctx.session.scalars(
            select(DepartmentMember.department_id).where(DepartmentMember.user_id == user_id)
        )
    )
    rows = await ctx.session.execute(
        select(KbShare, KnowledgeBase)
        .join(KnowledgeBase, KnowledgeBase.id == KbShare.kb_id)
        .where(KnowledgeBase.deleted_at.is_(None), share_matches(user_id, depts))
        .order_by(KnowledgeBase.name)
    )
    out: dict[uuid.UUID, UserKbAccess] = {}
    for s, kb in rows:
        r = out.setdefault(kb.id, UserKbAccess(kb_id=kb.id, kb_name=kb.name, role=s.role, reasons=[]))  # type: ignore[arg-type]
        r.role = stronger(r.role, s.role)  # type: ignore[assignment]
        r.reasons.append(AccessReason(subject_type=s.subject_type, subject_id=s.subject_id, role=s.role))  # type: ignore[arg-type]
    for r in out.values():
        r.reasons.sort(key=lambda x: (shares.SUBJECT_ORDER[x.subject_type], x.subject_id))
    return list(out.values())
