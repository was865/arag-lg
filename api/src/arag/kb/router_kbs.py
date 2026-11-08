"""KB API（specs/000-overview/api.md §3.3）。"""

import uuid

from fastapi import APIRouter, Response, status

from arag.audit import AuditEvent
from arag.db.models import KnowledgeBase
from arag.deps import CtxDep
from arag.errors import ApiError, not_found
from arag.kb import permissions as perm
from arag.kb import service
from arag.kb.schemas import KbCreate, KbOut, KbUpdate

router = APIRouter(prefix="/v1/kbs", tags=["kbs"])


def _out(ctx: CtxDep, kb: KnowledgeBase, count: int) -> KbOut:
    return KbOut(
        id=kb.id,
        kind=kb.kind,  # type: ignore[arg-type]
        name=kb.name,
        status=kb.status,  # type: ignore[arg-type]
        writable=perm.can_write(ctx.principal, kb),
        document_count=count,
        created_at=kb.created_at,
    )


async def _managed_org_kb(ctx: CtxDep, kb_id: uuid.UUID, *, trashed: bool) -> KnowledgeBase:
    kb = await service.get_kb_any(ctx.session, kb_id)
    if kb is None or not perm.can_see_ignoring_trash(ctx.principal, kb):
        raise not_found()
    if (kb.deleted_at is not None) != trashed:
        raise not_found()
    if not perm.can_manage_org_kb(ctx.principal, kb):
        raise ApiError(403, "forbidden", "この知識ベースを管理する権限がありません")
    return kb


@router.get("", response_model=list[KbOut])
async def list_kbs(ctx: CtxDep) -> list[KbOut]:
    await service.ensure_personal_kb(ctx.session, ctx.principal.user_id)
    await ctx.session.commit()
    return [_out(ctx, kb, n) for kb, n in await service.list_kbs(ctx.session, ctx.principal)]


@router.post("", response_model=KbOut, status_code=status.HTTP_201_CREATED)
async def create_kb(body: KbCreate, ctx: CtxDep) -> KbOut:
    if not ctx.principal.is_admin:
        raise ApiError(403, "forbidden", "全社の知識ベースを作成できるのは管理者だけです")
    kb = KnowledgeBase(id=uuid.uuid4(), kind="org", name=body.name, status="active")
    ctx.session.add(kb)
    await ctx.session.flush()
    await ctx.audit(AuditEvent(action="kb.create", resource_type="kb", resource_id=str(kb.id)))
    await ctx.session.commit()
    await ctx.session.refresh(kb)
    return _out(ctx, kb, 0)


@router.patch("/{kb_id}", response_model=KbOut)
async def rename_kb(kb_id: uuid.UUID, body: KbUpdate, ctx: CtxDep) -> KbOut:
    kb = await service.get_readable_kb(ctx.session, ctx.principal, kb_id)
    if not perm.can_rename_kb(ctx.principal, kb):
        raise ApiError(403, "forbidden", "この知識ベースを変更する権限がありません")
    kb.name = body.name
    await ctx.session.commit()
    return _out(ctx, kb, await service.count_docs(ctx.session, kb.id))


async def _set_status(kb_id: uuid.UUID, ctx: CtxDep, new: str) -> KbOut:
    kb = await _managed_org_kb(ctx, kb_id, trashed=False)
    if kb.status != new:  # 同じ状態への変更は監査ログを汚さない
        kb.status = new
        action = "kb.archive" if new == "archived" else "kb.unarchive"
        await ctx.audit(AuditEvent(action=action, resource_type="kb", resource_id=str(kb.id)))
        await ctx.session.commit()
        # アーカイブは検索対象から外す（payload の kb_ids を更新）
        await ctx.payload_sync.sync(await service.content_hashes_of_kb(ctx.session, kb.id))
    return _out(ctx, kb, await service.count_docs(ctx.session, kb.id))


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
    return _out(ctx, kb, await service.count_docs(ctx.session, kb.id))
