"""フォルダ API（specs/000-overview/api.md §3.4）。"""

import uuid

from fastapi import APIRouter, Response, status
from sqlalchemy.exc import IntegrityError

from arag.audit import AuditEvent
from arag.db.models import Folder
from arag.deps import CtxDep
from arag.errors import not_found
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
    await service.get_writable_kb(ctx.session, ctx.principal, folder.kb_id)
    return folder


@router.get("/v1/kbs/{kb_id}/folders", response_model=list[FolderOut])
async def list_folders(kb_id: uuid.UUID, ctx: CtxDep) -> list[FolderOut]:
    await service.get_readable_kb(ctx.session, ctx.principal, kb_id)
    return [_out(f, n) for f, n in await service.list_folders(ctx.session, kb_id)]


@router.post("/v1/kbs/{kb_id}/folders", response_model=FolderOut, status_code=status.HTTP_201_CREATED)
async def create_folder(kb_id: uuid.UUID, body: FolderCreate, ctx: CtxDep) -> FolderOut:
    await service.get_writable_kb(ctx.session, ctx.principal, kb_id)
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
    assert kb is not None and perm.can_write(ctx.principal, kb)
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
