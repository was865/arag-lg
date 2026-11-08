"""アップロード（specs/003-ingestion R7〜R12、design §4 の並行アップロード）。"""

import asyncio
import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from fastapi import UploadFile
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from arag.db.models import Content, Document, Folder, IngestJob
from arag.errors import ApiError
from arag.ingest import queue
from arag.kb.schemas import _valid_name
from arag.storage import Storage, content_prefix

# 拡張子 → MIME（R11）
SUPPORTED: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "doc": "application/msword",
    "xls": "application/vnd.ms-excel",
    "ppt": "application/vnd.ms-powerpoint",
    "rtf": "application/rtf",
    "odt": "application/vnd.oasis.opendocument.text",
    "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "odp": "application/vnd.oasis.opendocument.presentation",
    "html": "text/html",
    "htm": "text/html",
    "md": "text/markdown",
    "markdown": "text/markdown",
    "txt": "text/plain",
    "csv": "text/csv",
    "json": "application/json",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "webp": "image/webp",
}

UploadStatus = Literal["queued", "skipped", "duplicate"]


@dataclass(slots=True)
class Staged:
    """一時保存済みのアップロード。"""

    filename: str
    folder_parts: list[str]
    ext: str
    path: Path
    content_hash: str
    size: int


@dataclass(slots=True)
class UploadOutcome:
    filename: str
    document_id: uuid.UUID
    job_id: uuid.UUID | None
    status: UploadStatus


def split_relative_path(raw_name: str, relative_path: str | None) -> tuple[str, list[str]]:
    """相対パス（`a/b/c.pdf`）→（表示名, フォルダ部分）。`..` や空要素は捨てる（R10）。"""
    path = (relative_path or raw_name or "").replace("\\", "/")
    parts = [p for p in PurePosixPath(path).parts if p not in ("", ".", "..", "/")]
    if not parts:
        raise ApiError(400, "invalid_filename", "ファイル名がありません")
    try:
        return _valid_name(parts[-1]), [_valid_name(p) for p in parts[:-1]]
    except ValueError as e:
        raise ApiError(400, "invalid_filename", "ファイル名またはフォルダ名が正しくありません") from e


def extension_of(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in SUPPORTED:
        raise ApiError(415, "unsupported_media_type", f"対応していない形式です: {filename}")
    return ext


async def stage_upload(
    upload: UploadFile, relative_path: str | None, tmp_dir: Path, max_bytes: int
) -> Staged:
    """一時ファイルへ書きながら SHA-256 とサイズを計る。上限超過は 413（R11）。"""
    filename, folders = split_relative_path(upload.filename or "", relative_path)
    ext = extension_of(filename)
    await asyncio.to_thread(tmp_dir.mkdir, parents=True, exist_ok=True)
    tmp = tmp_dir / f"upload-{uuid.uuid4().hex}.{ext}"
    digest = hashlib.sha256()
    size = 0
    out = await asyncio.to_thread(tmp.open, "wb")
    try:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                raise ApiError(
                    413,
                    "payload_too_large",
                    f"ファイルが大きすぎます（上限 {max_bytes // (1024 * 1024)} MB）: {filename}",
                )
            digest.update(chunk)
            await asyncio.to_thread(out.write, chunk)
        if size == 0:
            raise ApiError(400, "empty_file", f"空のファイルです: {filename}")
    except BaseException:
        await asyncio.to_thread(out.close)
        await asyncio.to_thread(tmp.unlink, missing_ok=True)
        raise
    await asyncio.to_thread(out.close)
    return Staged(
        filename=filename, folder_parts=folders, ext=ext, path=tmp, content_hash=digest.hexdigest(), size=size
    )


async def ensure_folder_path(
    session: AsyncSession, kb_id: uuid.UUID, base: uuid.UUID | None, parts: list[str]
) -> uuid.UUID | None:
    """`a/b` のフォルダを（無ければ）作り、末端の ID を返す。並行作成は UNIQUE で吸収する。"""
    parent = base
    for name in parts:
        found = await session.scalar(
            select(Folder.id).where(
                Folder.kb_id == kb_id,
                Folder.parent_id.is_(None) if parent is None else Folder.parent_id == parent,
                Folder.name == name,
                Folder.deleted_at.is_(None),
            )
        )
        if found is None:
            try:
                async with session.begin_nested():
                    folder = Folder(id=uuid.uuid4(), kb_id=kb_id, parent_id=parent, name=name)
                    session.add(folder)
                found = folder.id
            except IntegrityError:
                found = await session.scalar(
                    select(Folder.id).where(
                        Folder.kb_id == kb_id,
                        Folder.parent_id.is_(None) if parent is None else Folder.parent_id == parent,
                        Folder.name == name,
                        Folder.deleted_at.is_(None),
                    )
                )
                assert found is not None
        parent = found
    return parent


async def _latest_job(session: AsyncSession, content_hash: str) -> IngestJob | None:
    return await session.scalar(
        select(IngestJob)
        .where(IngestJob.content_hash == content_hash)
        .order_by(IngestJob.created_at.desc())
        .limit(1)
    )


async def register(
    session: AsyncSession,
    storage: Storage,
    staged: Staged,
    *,
    kb_id: uuid.UUID,
    folder_id: uuid.UUID | None,
    user_id: str,
) -> UploadOutcome:
    """1 ファイル分の内容・ジョブ・文書を作る。呼び出し側がコミットする。"""
    h = staged.content_hash
    inserted = await session.scalar(
        pg_insert(Content)
        .values(
            content_hash=h,
            mime=SUPPORTED[staged.ext],
            ext=staged.ext,
            size=staged.size,
            status="queued",
            ref_count=0,
        )
        .on_conflict_do_nothing(index_elements=["content_hash"])
        .returning(Content.content_hash)
    )
    key = f"{content_prefix(h)}/original.{staged.ext}"
    job: IngestJob | None
    if inserted:
        # 初回: 原本を保存してジョブを積む（並行要求の他方は ON CONFLICT で待ってから既存扱い。R9）
        await storage.put_file(key, staged.path)
        job = await queue.enqueue(session, h)
        content_status: UploadStatus = "queued"
    else:
        content = await session.get(Content, h, with_for_update=True)
        assert content is not None
        if not await storage.exists(f"{content_prefix(h)}/original.{content.ext}"):
            await storage.put_file(f"{content_prefix(h)}/original.{content.ext}", staged.path)
        job = await _latest_job(session, h)
        if content.status in ("error", "cancelled") or job is None:
            # 前回失敗・取消した内容はもう一度解析する
            if job is None:
                job = await queue.enqueue(session, h)
            else:
                await queue.reset_for_retry(session, job)
            content.status = "queued"
            content_status = "queued"
        else:
            content_status = "skipped"  # 解析済み・解析中（R8）
        if content.status == "ready":
            job = None
    await asyncio.to_thread(staged.path.unlink, missing_ok=True)

    doc_id = await session.scalar(
        pg_insert(Document)
        .values(
            id=uuid.uuid4(),
            kb_id=kb_id,
            content_hash=h,
            folder_id=folder_id,
            filename=staged.filename,
            uploaded_by=user_id,
        )
        .on_conflict_do_nothing(index_elements=["kb_id", "content_hash"])
        .returning(Document.id)
    )
    if doc_id is not None:
        await session.execute(
            update(Content).where(Content.content_hash == h).values(ref_count=Content.ref_count + 1)
        )
        return UploadOutcome(staged.filename, doc_id, job.id if job else None, content_status)

    # 同じ KB に同じ内容が既にある（R8）。ごみ箱にあれば戻して今回のフォルダへ置く。
    existing = await session.scalar(
        select(Document).where(Document.kb_id == kb_id, Document.content_hash == h)
    )
    assert existing is not None
    if existing.deleted_at is not None:
        existing.deleted_at = None
        existing.deleted_by = None
        existing.folder_id = folder_id
    return UploadOutcome(staged.filename, existing.id, job.id if job else None, "duplicate")


def tmp_dir_for(storage_root: str) -> Path:
    return Path(os.path.abspath(storage_root)) / ".tmp"
