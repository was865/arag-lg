"""KB API（specs/000-overview/api.md §3.3）。"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from arag.audit import AuditEvent
from arag.db.models import KnowledgeBase
from arag.deps import CtxDep
from arag.errors import ApiError, not_found
from arag.kb import permissions as perm
from arag.kb import service, shares
from arag.kb.schemas import KbCreate, KbOut, KbUpdate
from arag.kb.shares import ShareIn

router = APIRouter(prefix="/v1/kbs", tags=["kbs"])


def _out(ctx: CtxDep, kb: KnowledgeBase, count: int, everyone: set[uuid.UUID] | None = None) -> KbOut:
    role = perm.role_of(ctx.access, kb) if kb.deleted_at is None else None
    return KbOut(
        id=kb.id,
        kind=kb.kind,  # type: ignore[arg-type]
        name=kb.name,
        status=kb.status,  # type: ignore[arg-type]
        writable=perm.can_write(ctx.access, kb),
        # 読めない KB（admin の管理用一覧）は文書の数も出さない
        document_count=count if role is not None else 0,
        created_at=kb.created_at,
        role=role,  # type: ignore[arg-type]
        can_manage=perm.can_manage_org_kb(ctx.access, kb),
        shared_with_everyone=kb.id in everyone if everyone is not None else False,
    )


async def _one(ctx: CtxDep, kb: KnowledgeBase) -> KbOut:
    everyone = await shares.kbs_shared_with_everyone(ctx.session, [kb.id])
    return _out(ctx, kb, await service.count_docs(ctx.session, kb.id), everyone)


async def _managed_org_kb(ctx: CtxDep, kb_id: uuid.UUID, *, trashed: bool) -> KnowledgeBase:
    kb = await service.get_kb_any(ctx.session, kb_id)
    if kb is None or not (
        perm.can_see_ignoring_trash(ctx.access, kb) or perm.can_manage_org_kb(ctx.access, kb)
    ):
        raise not_found()
    if (kb.deleted_at is not None) != trashed:
        raise not_found()
    if not perm.can_manage_org_kb(ctx.access, kb):
        raise ApiError(403, "forbidden", "この知識ベースを管理する権限がありません")
    return kb


@router.get("", response_model=list[KbOut])
async def list_kbs(
    ctx: CtxDep,
    manageable: Annotated[
        bool, Query(description="true なら admin には読めない共有 KB も返す（共有リストの管理用）")
    ] = False,
) -> list[KbOut]:
    await service.ensure_personal_kb(ctx.session, ctx.principal.user_id)
    await ctx.session.commit()
    rows = await service.list_kbs(ctx.session, ctx.access, manageable=manageable)
    everyone = await shares.kbs_shared_with_everyone(ctx.session, [kb.id for kb, _ in rows])
    return [_out(ctx, kb, n, everyone) for kb, n in rows]


@router.post("", response_model=KbOut, status_code=status.HTTP_201_CREATED)
async def create_kb(body: KbCreate, ctx: CtxDep) -> KbOut:
    """admin は誰向けにも、部門管理者は自分の部門向けに作れる（specs/024 R9）。"""
    a = ctx.access
    dept = str(body.department_id) if body.department_id else None
    if dept is not None and not await shares.department_exists(ctx.session, dept):
        raise ApiError(400, "invalid_department", "指定した部門が見つかりません")
    if not a.is_admin and (dept is None or dept not in a.managed_department_ids):
        raise ApiError(
            403, "forbidden", "共有の知識ベースを作れるのは管理者と、自分の部門向けの部門管理者だけです"
        )
    kb = KnowledgeBase(id=uuid.uuid4(), kind="org", name=body.name, status="active")
    ctx.session.add(kb)
    await ctx.session.flush()
    first = (
        ShareIn(subject_type="department", subject_id=dept, role="viewer")
        if dept
        else ShareIn(subject_type="everyone", role="viewer")
    )
    me = ShareIn(subject_type="user", subject_id=a.user_id, role="manager")
    await shares.replace_shares(ctx, kb, [first, me], audit=False)
    await ctx.audit(
        AuditEvent(
            action="kb.create", resource_type="kb", resource_id=str(kb.id), detail={"department_id": dept}
        )
    )
    await ctx.session.commit()
    await ctx.session.refresh(kb)
    ctx_after = await shares.reloaded(ctx)
    return _out(ctx_after, kb, 0, {kb.id} if dept is None else set())


@router.patch("/{kb_id}", response_model=KbOut)
async def rename_kb(kb_id: uuid.UUID, body: KbUpdate, ctx: CtxDep) -> KbOut:
    kb = await service.get_kb_any(ctx.session, kb_id)
    if (
        kb is None
        or kb.deleted_at is not None
        or not (perm.can_read(ctx.access, kb) or perm.can_manage_org_kb(ctx.access, kb))
    ):
        raise not_found()
    if not perm.can_rename_kb(ctx.access, kb):
        raise ApiError(403, "forbidden", "この知識ベースを変更する権限がありません")
    kb.name = body.name
    await ctx.session.commit()
    return await _one(ctx, kb)


async def _set_status(kb_id: uuid.UUID, ctx: CtxDep, new: str) -> KbOut:
    kb = await _managed_org_kb(ctx, kb_id, trashed=False)
    if kb.status != new:  # 同じ状態への変更は監査ログを汚さない
        kb.status = new
        action = "kb.archive" if new == "archived" else "kb.unarchive"
        await ctx.audit(AuditEvent(action=action, resource_type="kb", resource_id=str(kb.id)))
        await ctx.session.commit()
        # payload は変えない。アーカイブ済みの除外は検索時のフィルタで行う（specs/004-retrieval R5）
    return await _one(ctx, kb)


@router.post("/{kb_id}/archive", response_model=KbOut)
async def archive_kb(kb_id: uuid.UUID, ctx: CtxDep) -> KbOut:
    return await _set_status(kb_id, ctx, "archived")


@router.post("/{kb_id}/unarchive", response_model=KbOut)
async def unarchive_kb(kb_id: uuid.UUID, ctx: CtxDep) -> KbOut:
    return await _set_status(kb_id, ctx, "active")


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def trash_kb(kb_id: uuid.UUID, ctx: CtxDep) -> Response:
    kb = await _managed_org_kb(ctx, kb_id, trashed=False)
    kb.deleted_at = service.utcnow()
    kb.deleted_by = ctx.principal.user_id
    await ctx.audit(AuditEvent(action="kb.delete", resource_type="kb", resource_id=str(kb.id)))
    await ctx.session.commit()
    await ctx.payload_sync.sync(await service.content_hashes_of_kb(ctx.session, kb.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{kb_id}/restore", response_model=KbOut)
async def restore_kb(kb_id: uuid.UUID, ctx: CtxDep) -> KbOut:
    kb = await _managed_org_kb(ctx, kb_id, trashed=True)
    kb.deleted_at = None
    kb.deleted_by = None
    await ctx.audit(AuditEvent(action="kb.restore", resource_type="kb", resource_id=str(kb.id)))
    await ctx.session.commit()
    await ctx.payload_sync.sync(await service.content_hashes_of_kb(ctx.session, kb.id))
    return await _one(ctx, kb)
