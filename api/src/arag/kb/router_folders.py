"""フォルダ API（specs/000-overview/api.md §3.4）。"""

import uuid

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from arag.audit import AuditEvent
from arag.db.models import Folder
from arag.deps import CtxDep
from arag.errors import ApiError, not_found
from arag.ingest.gc import collect_orphans, delete_documents
from arag.kb import permissions as perm
from arag.kb import service
from arag.kb.schemas import FolderCreate, FolderOut, FolderUpdate

router = APIRouter(tags=["folders"])


def _out(folder: Folder, count: int = 0) -> FolderOut:
    return FolderOut(
        id=folder.id,
        kb_id=folder.kb_id,
        parent_id=folder.parent_id,
        name=folder.name,
        document_count=count,
        created_at=folder.created_at,
    )


async def _writable_folder(ctx: CtxDep, folder_id: uuid.UUID, *, trashed: bool) -> Folder:
    folder = await service.get_folder(ctx.session, folder_id)
    if folder is None or (folder.deleted_at is not None) != trashed:
        raise not_found()
    await service.get_writable_kb(ctx.session, ctx.access, folder.kb_id)
    return folder


@router.get("/v1/kbs/{kb_id}/folders", response_model=list[FolderOut])
async def list_folders(kb_id: uuid.UUID, ctx: CtxDep) -> list[FolderOut]:
    await service.get_readable_kb(ctx.session, ctx.access, kb_id)
    return [_out(f, n) for f, n in await service.list_folders(ctx.session, kb_id)]


@router.post("/v1/kbs/{kb_id}/folders", response_model=FolderOut, status_code=status.HTTP_201_CREATED)
async def create_folder(kb_id: uuid.UUID, body: FolderCreate, ctx: CtxDep) -> FolderOut:
    await service.get_writable_kb(ctx.session, ctx.access, kb_id)
    folder = await service.create_folder(ctx.session, kb_id, body.name, body.parent_id)
    await ctx.session.commit()
    await ctx.session.refresh(folder)
    return _out(folder)


@router.patch("/v1/folders/{folder_id}", response_model=FolderOut)
async def update_folder(folder_id: uuid.UUID, body: FolderUpdate, ctx: CtxDep) -> FolderOut:
    folder = await _writable_folder(ctx, folder_id, trashed=False)
    folder = await service.update_folder(
        ctx.session,
        folder,
        name=body.name,
        move="parent_id" in body.model_fields_set,
        parent_id=body.parent_id,
    )
    await ctx.session.commit()
    return _out(folder)


@router.delete("/v1/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def trash_folder(folder_id: uuid.UUID, ctx: CtxDep) -> Response:
    folder = await _writable_folder(ctx, folder_id, trashed=False)
    hashes = await service.trash_folder(ctx.session, folder, ctx.principal.user_id)
    await ctx.audit(
        AuditEvent(
            action="folder.delete",
            resource_type="folder",
            resource_id=str(folder.id),
            detail={"documents": len(hashes)},
        )
    )
    await ctx.session.commit()
    await ctx.payload_sync.sync(hashes)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/v1/folders/{folder_id}/restore", response_model=FolderOut)
async def restore_folder(folder_id: uuid.UUID, ctx: CtxDep) -> FolderOut:
    folder = await _writable_folder(ctx, folder_id, trashed=True)
    kb = await service.get_kb_any(ctx.session, folder.kb_id)
    assert kb is not None and perm.can_write(ctx.access, kb)
    try:
        hashes = await service.restore_folder(ctx.session, folder)
    except IntegrityError as e:
        await ctx.session.rollback()
        raise service.folder_conflict() from e
    await ctx.audit(AuditEvent(action="folder.restore", resource_type="folder", resource_id=str(folder.id)))
    await ctx.session.commit()
    await ctx.payload_sync.sync(hashes)
    await ctx.session.refresh(folder)
    return _out(folder)


@router.delete("/v1/folders/{folder_id}/purge", status_code=status.HTTP_204_NO_CONTENT)
async def purge_folder(request: Request, folder_id: uuid.UUID, ctx: CtxDep) -> Response:
    """ごみ箱のフォルダを配下ごと完全に削除する（文書の完全削除と同じ権限。R34）。"""
    folder = await service.get_folder(ctx.session, folder_id)
    if folder is None or folder.deleted_at is None:
        raise not_found()
    kb = await service.get_kb_any(ctx.session, folder.kb_id)
    if kb is None or not perm.can_see_ignoring_trash(ctx.access, kb):
        raise not_found()
    ids, docs = await service.folder_purge_plan(ctx.session, folder)
    if not perm.can_purge_folder(ctx.access, kb, folder, docs, service.utcnow()):
        raise ApiError(403, "forbidden", "完全削除できるのは、削除から 24 時間以内の本人か管理者だけです")
    hashes = await delete_documents(ctx.session, [d.id for d in docs])
    # 子から順に消す（parent_id の参照を残さない）
    for fid in reversed(ids):
        await ctx.session.execute(delete(Folder).where(Folder.id == fid))
    await ctx.audit(
        AuditEvent(
            action="folder.purge",
            resource_type="folder",
            resource_id=str(folder_id),
            detail={"name": folder.name, "folders": len(ids), "documents": len(docs)},
        )
    )
    orphans = await collect_orphans(
        ctx.session, request.app.state.storage, request.app.state.index, only=list(hashes)
    )
    await ctx.session.commit()
    # 他の文書と共有している内容は payload を同期する
    rest = [h for h in hashes if h not in orphans]
    if rest:
        await ctx.payload_sync.sync(rest)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
