"""文書・参照・ごみ箱 API（specs/000-overview/api.md §3.5、R31〜R38）。"""

import base64
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, Query, Request, Response, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from arag.audit import AuditEvent
from arag.db.models import (
    Chunk,
    Citation,
    Content,
    Document,
    Folder,
    IngestJob,
    KnowledgeBase,
    Message,
    Section,
)
from arag.deps import CtxDep
from arag.errors import ApiError, not_found
from arag.ingest.gc import collect_orphans, delete_documents
from arag.ingest.report import load_report_dict
from arag.kb import permissions as perm
from arag.kb import service
from arag.kb.access import Access
from arag.kb.schemas import Name
from arag.settings import Settings
from arag.storage import Storage, StorageError, content_prefix

router = APIRouter(tags=["documents"])

MAX_BULK = 500
RANGE_CHUNK = 1024 * 1024


# ---------------------------------------------------------------- 入出力


class DocumentOut(BaseModel):
    id: uuid.UUID
    kb_id: uuid.UUID
    folder_id: uuid.UUID | None
    filename: str
    mime: str
    size: int
    status: str
    page_count: int | None
    chunk_count: int
    parse_warnings: int | None = None
    job_id: uuid.UUID | None
    writable: bool
    uploaded_by: str
    created_at: datetime
    deleted_at: datetime | None = None


class DocumentPage(BaseModel):
    items: list[DocumentOut]
    next_cursor: str | None


class DocumentStats(BaseModel):
    documents: int
    total_bytes: int
    by_status: dict[str, int]


class ExtCount(BaseModel):
    ext: str = Field(description="拡張子（小文字・ドット無し。無ければ空）")
    documents: int
    bytes: int


class CitedDocument(BaseModel):
    document: DocumentOut
    citations: int = Field(description="期間内に回答で引用された回数")


class DocumentOverview(BaseModel):
    """ナレッジベースの概要（specs/023）。"""

    documents: int
    total_bytes: int
    by_status: dict[str, int]
    by_ext: list[ExtCount] = Field(description="文書数の多い順")
    added_7d: int = Field(description="この 7 日に追加された文書の数")
    recent: list[DocumentOut] = Field(description="最近追加された文書（新しい順に最大 5 件）")
    failed: list[DocumentOut] = Field(description="処理に失敗した文書（新しい順に最大 5 件）")
    top_cited: list[CitedDocument] = Field(description="この 30 日によく引用された文書（最大 5 件）")


class DocumentUpdate(BaseModel):
    """folder_id を明示的に null にするとルートへ移動する。"""

    filename: Name | None = None
    folder_id: uuid.UUID | None = None


class BulkMove(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_BULK)
    folder_id: uuid.UUID | None = None


class BulkIds(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_BULK)


class BulkResult(BaseModel):
    updated: int


class OutlineSection(BaseModel):
    id: uuid.UUID
    ordinal: int
    heading_path: str
    level: int
    page_start: int | None
    page_end: int | None
    token_len: int
    chunk_count: int


class SectionOut(OutlineSection):
    text: str


class ChunkOut(BaseModel):
    id: uuid.UUID
    section_id: uuid.UUID
    ordinal: int
    block_type: str
    heading_path: str
    page_start: int | None
    page_end: int | None
    text: str
    context: str
    context_source: str
    token_len: int
    boxes: list[dict[str, Any]]
    body: str
    """埋め込みに送った本文（文脈 + チャンクの文。specs/030 R10）"""


class TrashItem(BaseModel):
    kind: Literal["document", "folder", "kb"]
    id: uuid.UUID
    name: str
    kb_id: uuid.UUID
    kb_name: str
    deleted_at: datetime
    deleted_by: str | None
    remaining_days: int
    purgeable: bool


# ---------------------------------------------------------------- 共通


def _readable_kb_filter(a: Access) -> Any:
    return and_(KnowledgeBase.deleted_at.is_(None), service.readable_kb_clause(a))


def _latest_job_id(content_hash: Any) -> Any:
    return (
        select(IngestJob.id)
        .where(IngestJob.content_hash == content_hash)
        .order_by(IngestJob.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )


def _chunk_count(content_hash: Any) -> Any:
    return select(func.count(Chunk.id)).where(Chunk.content_hash == content_hash).scalar_subquery()


def _doc_query() -> Select[Any]:
    return (
        select(
            Document,
            Content,
            KnowledgeBase,
            _chunk_count(Document.content_hash),
            _latest_job_id(Document.content_hash),
        )
        .join(Content, Content.content_hash == Document.content_hash)
        .join(KnowledgeBase, KnowledgeBase.id == Document.kb_id)
    )


def _doc_out(p: Access, row: Any) -> DocumentOut:
    doc, content, kb, chunks, job_id = row
    return DocumentOut(
        id=doc.id,
        kb_id=doc.kb_id,
        folder_id=doc.folder_id,
        filename=doc.filename,
        mime=content.mime,
        size=content.size,
        status=content.status,
        page_count=content.page_count,
        chunk_count=int(chunks or 0),
        parse_warnings=content.parse_warnings,
        job_id=job_id,
        writable=perm.can_write(p, kb),
        uploaded_by=doc.uploaded_by,
        created_at=doc.created_at,
        deleted_at=doc.deleted_at,
    )


def _encode_cursor(doc: Document) -> str:
    return base64.urlsafe_b64encode(f"{doc.created_at.isoformat()}|{doc.id}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        ts, did = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(ts), uuid.UUID(did)
    except Exception as e:
        raise ApiError(400, "invalid_cursor", "カーソルが正しくありません") from e


async def _readable_doc(ctx: CtxDep, doc_id: uuid.UUID) -> tuple[Document, KnowledgeBase]:
    doc = await ctx.session.get(Document, doc_id)
    if doc is None or doc.deleted_at is not None:
        raise not_found()
    kb = await service.get_readable_kb(ctx.session, ctx.access, doc.kb_id)
    return doc, kb


async def _writable_doc(
    ctx: CtxDep, doc_id: uuid.UUID, *, trashed: bool = False
) -> tuple[Document, KnowledgeBase]:
    doc = await ctx.session.get(Document, doc_id)
    if doc is None or (doc.deleted_at is not None) != trashed:
        raise not_found()
    kb = await service.get_writable_kb(ctx.session, ctx.access, doc.kb_id)
    return doc, kb


async def _one_out(ctx: CtxDep, doc_id: uuid.UUID) -> DocumentOut:
    row = (await ctx.session.execute(_doc_query().where(Document.id == doc_id))).one()
    return _doc_out(ctx.access, row)


# ---------------------------------------------------------------- 一覧・統計（R31）


@router.get("/v1/documents", response_model=DocumentPage)
async def list_documents(
    ctx: CtxDep,
    kb_id: uuid.UUID | None = None,
    folder_id: uuid.UUID | None = None,
    root_only: Annotated[bool, Query(description="true ならフォルダ外（ルート直下）だけ")] = False,
    status_filter: Annotated[str | None, Query(alias="status", description="カンマ区切りで複数可")] = None,
    q: Annotated[str | None, Query(max_length=200, description="ファイル名の部分一致")] = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> DocumentPage:
    stmt = _doc_query().where(Document.deleted_at.is_(None), _readable_kb_filter(ctx.access))
    if kb_id is not None:
        await service.get_readable_kb(ctx.session, ctx.access, kb_id)
        stmt = stmt.where(Document.kb_id == kb_id)
    if folder_id is not None:
        stmt = stmt.where(Document.folder_id == folder_id)
    elif root_only:
        stmt = stmt.where(Document.folder_id.is_(None))
    if status_filter:
        stmt = stmt.where(Content.status.in_([s.strip() for s in status_filter.split(",") if s.strip()]))
    if q and q.strip():
        # LIKE の特殊文字は文字どおりに扱う
        pattern = re.sub(r"([\\%_])", r"\\\1", q.strip())
        stmt = stmt.where(Document.filename.ilike(f"%{pattern}%", escape="\\"))
    if cursor:
        ts, did = _decode_cursor(cursor)
        stmt = stmt.where(or_(Document.created_at < ts, and_(Document.created_at == ts, Document.id < did)))
    stmt = stmt.order_by(Document.created_at.desc(), Document.id.desc()).limit(limit + 1)
    rows = (await ctx.session.execute(stmt)).all()
    items = [_doc_out(ctx.access, r) for r in rows[:limit]]
    next_cursor = _encode_cursor(rows[limit - 1][0]) if len(rows) > limit else None
    return DocumentPage(items=items, next_cursor=next_cursor)


@router.get("/v1/documents/stats", response_model=DocumentStats)
async def document_stats(ctx: CtxDep, kb_id: uuid.UUID | None = None) -> DocumentStats:
    q = (
        select(Content.status, func.count(Document.id), func.coalesce(func.sum(Content.size), 0))
        .join(Content, Content.content_hash == Document.content_hash)
        .join(KnowledgeBase, KnowledgeBase.id == Document.kb_id)
        .where(Document.deleted_at.is_(None), _readable_kb_filter(ctx.access))
        .group_by(Content.status)
    )
    if kb_id is not None:
        q = q.where(Document.kb_id == kb_id)
    rows = (await ctx.session.execute(q)).all()
    return DocumentStats(
        documents=sum(int(n) for _, n, _ in rows),
        total_bytes=sum(int(b) for _, _, b in rows),
        by_status={s: int(n) for s, n, _ in rows},
    )


OVERVIEW_LIST = 5
CITED_DAYS = 30


@router.get("/v1/documents/overview", response_model=DocumentOverview)
async def document_overview(ctx: CtxDep, kb_id: uuid.UUID | None = None) -> DocumentOverview:
    """読めるナレッジベース（kb_id があればその 1 つ）の概要。

    引用の回数は全員の回答を数えるが、出す文書は読めるものだけ。
    """
    if kb_id is not None:
        await service.get_readable_kb(ctx.session, ctx.access, kb_id)
    scope = [Document.deleted_at.is_(None), _readable_kb_filter(ctx.access)]
    if kb_id is not None:
        scope.append(Document.kb_id == kb_id)
    s = ctx.session
    base = (
        select(Content.ext, Content.status, func.count(Document.id), func.coalesce(func.sum(Content.size), 0))
        .join(Content, Content.content_hash == Document.content_hash)
        .join(KnowledgeBase, KnowledgeBase.id == Document.kb_id)
        .where(*scope)
        .group_by(Content.ext, Content.status)
    )
    by_status: dict[str, int] = {}
    by_ext: dict[str, list[int]] = {}
    for ext, st, n, b in (await s.execute(base)).all():
        by_status[st] = by_status.get(st, 0) + int(n)
        e = by_ext.setdefault(ext or "", [0, 0])
        e[0] += int(n)
        e[1] += int(b)
    now = datetime.now(UTC)
    added = await s.scalar(
        select(func.count(Document.id))
        .join(KnowledgeBase, KnowledgeBase.id == Document.kb_id)
        .where(*scope, Document.created_at >= now - timedelta(days=7))
    )
    newest = _doc_query().where(*scope).order_by(Document.created_at.desc(), Document.id.desc())
    recent = (await s.execute(newest.limit(OVERVIEW_LIST))).all()
    failed = (await s.execute(newest.where(Content.status == "error").limit(OVERVIEW_LIST))).all()
    cited = (
        select(Citation.document_id, func.count(Citation.id).label("n"))
        .join(Message, Message.id == Citation.message_id)
        .where(Citation.document_id.is_not(None), Message.created_at >= now - timedelta(days=CITED_DAYS))
        .group_by(Citation.document_id)
        .subquery()
    )
    top = (
        await s.execute(
            _doc_query()
            .add_columns(cited.c.n)
            .join(cited, cited.c.document_id == Document.id)
            .where(*scope)
            .order_by(cited.c.n.desc(), Document.filename)
            .limit(OVERVIEW_LIST)
        )
    ).all()
    p = ctx.access
    return DocumentOverview(
        documents=sum(by_status.values()),
        total_bytes=sum(b for _, b in by_ext.values()),
        by_status=by_status,
        by_ext=[
            ExtCount(ext=e, documents=n, bytes=b)
            for e, (n, b) in sorted(by_ext.items(), key=lambda x: (-x[1][0], x[0]))
        ],
        added_7d=int(added or 0),
        recent=[_doc_out(p, r) for r in recent],
        failed=[_doc_out(p, r) for r in failed],
        top_cited=[CitedDocument(document=_doc_out(p, r[:5]), citations=int(r[5])) for r in top],
    )


# ---------------------------------------------------------------- 1 件（R32〜R34）


@router.get("/v1/documents/{doc_id}", response_model=DocumentOut)
async def get_document(doc_id: uuid.UUID, ctx: CtxDep) -> DocumentOut:
    await _readable_doc(ctx, doc_id)
    return await _one_out(ctx, doc_id)


@router.patch("/v1/documents/{doc_id}", response_model=DocumentOut)
async def update_document(doc_id: uuid.UUID, body: DocumentUpdate, ctx: CtxDep) -> DocumentOut:
    doc, _ = await _writable_doc(ctx, doc_id)
    if body.filename is not None:
        doc.filename = body.filename
    if "folder_id" in body.model_fields_set:
        await service.require_live_folder_in_kb(ctx.session, doc.kb_id, body.folder_id)
        doc.folder_id = body.folder_id
    await ctx.session.commit()
    return await _one_out(ctx, doc_id)


async def _bulk_writable(ctx: CtxDep, ids: list[uuid.UUID], *, trashed: bool = False) -> list[Document]:
    docs = [await _writable_doc(ctx, i, trashed=trashed) for i in dict.fromkeys(ids)]
    return [d for d, _ in docs]


@router.post("/v1/documents/bulk-move", response_model=BulkResult)
async def bulk_move(body: BulkMove, ctx: CtxDep) -> BulkResult:
    docs = await _bulk_writable(ctx, body.ids)
    for d in docs:
        await service.require_live_folder_in_kb(ctx.session, d.kb_id, body.folder_id)
        d.folder_id = body.folder_id
    await ctx.session.commit()
    return BulkResult(updated=len(docs))


async def _trash(ctx: CtxDep, docs: list[Document]) -> None:
    now = service.utcnow()
    for d in docs:
        d.deleted_at = now
        d.deleted_by = ctx.principal.user_id
        await ctx.audit(AuditEvent(action="document.delete", resource_type="document", resource_id=str(d.id)))
    await ctx.session.commit()
    await ctx.payload_sync.sync({d.content_hash for d in docs})


@router.post("/v1/documents/bulk-delete", response_model=BulkResult)
async def bulk_delete(body: BulkIds, ctx: CtxDep) -> BulkResult:
    docs = await _bulk_writable(ctx, body.ids)
    await _trash(ctx, docs)
    return BulkResult(updated=len(docs))


@router.delete("/v1/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def trash_document(doc_id: uuid.UUID, ctx: CtxDep) -> Response:
    doc, _ = await _writable_doc(ctx, doc_id)
    await _trash(ctx, [doc])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/v1/documents/{doc_id}/restore", response_model=DocumentOut)
async def restore_document(doc_id: uuid.UUID, ctx: CtxDep) -> DocumentOut:
    doc, _ = await _writable_doc(ctx, doc_id, trashed=True)
    # 削除済みの祖先フォルダも生き返らせる（R33）
    await service.revive_ancestors(ctx.session, doc.folder_id)
    doc.deleted_at = None
    doc.deleted_by = None
    await ctx.audit(AuditEvent(action="document.restore", resource_type="document", resource_id=str(doc.id)))
    await ctx.session.commit()
    await ctx.payload_sync.sync([doc.content_hash])
    return await _one_out(ctx, doc_id)


@router.delete("/v1/documents/{doc_id}/purge", status_code=status.HTTP_204_NO_CONTENT)
async def purge_document(request: Request, doc_id: uuid.UUID, ctx: CtxDep) -> Response:
    doc = await ctx.session.get(Document, doc_id)
    if doc is None or doc.deleted_at is None:
        raise not_found()
    kb = await service.get_kb_any(ctx.session, doc.kb_id)
    assert kb is not None
    if not perm.can_see_ignoring_trash(ctx.access, kb):
        raise not_found()
    if not perm.can_purge(ctx.access, kb, doc, service.utcnow()):
        raise ApiError(403, "forbidden", "完全削除できるのは、削除から 24 時間以内の本人か管理者だけです")
    h = doc.content_hash
    await delete_documents(ctx.session, [doc.id])
    await ctx.audit(AuditEvent(action="document.purge", resource_type="document", resource_id=str(doc_id)))
    # どこからも参照されなくなった内容は実体まで消す（R35）
    orphans = await collect_orphans(ctx.session, request.app.state.storage, request.app.state.index, only=[h])
    await ctx.session.commit()
    if not orphans:
        await ctx.payload_sync.sync([h])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- 参照（R37・R38）


_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


async def _content_of(session: AsyncSession, doc: Document) -> Content:
    content = await session.get(Content, doc.content_hash)
    assert content is not None
    return content


@router.get("/v1/documents/{doc_id}/original")
async def original(
    request: Request,
    doc_id: uuid.UUID,
    ctx: CtxDep,
    range_header: Annotated[str | None, Header(alias="range")] = None,
) -> Response:
    doc, _ = await _readable_doc(ctx, doc_id)
    content = await _content_of(ctx.session, doc)
    storage: Storage = request.app.state.storage
    key = f"{content_prefix(content.content_hash)}/original.{content.ext}"
    if not await storage.exists(key):
        raise not_found("原本ファイルが見つかりません")
    size = await storage.size(key)
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f"inline; filename*=UTF-8''{_quote(doc.filename)}",
    }
    if range_header:
        m = _RANGE.match(range_header.strip())
        if not m or (not m.group(1) and not m.group(2)):
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        if m.group(1):
            start = int(m.group(1))
            end = min(int(m.group(2)) if m.group(2) else size - 1, size - 1)
        else:  # bytes=-N（末尾 N バイト）
            start, end = max(size - int(m.group(2)), 0), size - 1
        if start > end or start >= size:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        end = min(end, start + 16 * RANGE_CHUNK - 1)  # 1 回の応答は 16 MB まで
        data = await storage.read_range(key, start, end)
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        return Response(data, status_code=206, media_type=content.mime, headers=headers)
    return Response(await storage.read(key), media_type=content.mime, headers=headers)


def _quote(name: str) -> str:
    from urllib.parse import quote

    return quote(name, safe="")


@router.get("/v1/documents/{doc_id}/rendered", response_class=PlainTextResponse)
async def rendered(request: Request, doc_id: uuid.UUID, ctx: CtxDep) -> PlainTextResponse:
    doc, _ = await _readable_doc(ctx, doc_id)
    key = f"{content_prefix(doc.content_hash)}/rendered.md"
    storage: Storage = request.app.state.storage
    if not await storage.exists(key):
        raise not_found("解析結果がまだありません")
    return PlainTextResponse((await storage.read(key)).decode(), media_type="text/markdown; charset=utf-8")


@router.get("/v1/documents/{doc_id}/parse-report")
async def parse_report(request: Request, doc_id: uuid.UUID, ctx: CtxDep) -> dict[str, Any]:
    """解析の記録（本文は含まない。specs/030 R3）。"""
    doc, _ = await _readable_doc(ctx, doc_id)
    storage: Storage = request.app.state.storage
    report = await load_report_dict(storage, content_prefix(doc.content_hash))
    if report is None:
        raise not_found("解析の記録がありません")
    return report


@router.get("/v1/documents/{doc_id}/docling")
async def docling_json(request: Request, doc_id: uuid.UUID, ctx: CtxDep) -> Response:
    """Docling の生の JSON（管理者だけ。specs/030 R4）。"""
    doc, _ = await _readable_doc(ctx, doc_id)
    if not ctx.access.is_admin:
        raise ApiError(403, "forbidden", "管理者だけが見られます")
    storage: Storage = request.app.state.storage
    key = f"{content_prefix(doc.content_hash)}/docling.json"
    if not await storage.exists(key):
        raise not_found("解析結果がまだありません")
    return Response(await storage.read(key), media_type="application/json")


def _section_counts() -> Any:
    return select(func.count(Chunk.id)).where(Chunk.section_id == Section.id).scalar_subquery()


def _outline(row: Any) -> dict[str, Any]:
    sec, n = row
    return {
        "id": sec.id,
        "ordinal": sec.ordinal,
        "heading_path": sec.heading_path,
        "level": sec.level,
        "page_start": sec.page_start,
        "page_end": sec.page_end,
        "token_len": sec.token_len,
        "chunk_count": int(n or 0),
    }


@router.get("/v1/documents/{doc_id}/outline", response_model=list[OutlineSection])
async def outline(doc_id: uuid.UUID, ctx: CtxDep) -> list[OutlineSection]:
    doc, _ = await _readable_doc(ctx, doc_id)
    rows = await ctx.session.execute(
        select(Section, _section_counts())
        .where(Section.content_hash == doc.content_hash)
        .order_by(Section.ordinal)
    )
    return [OutlineSection(**_outline(r)) for r in rows]


@router.get("/v1/documents/{doc_id}/sections", response_model=list[SectionOut])
async def sections(
    doc_id: uuid.UUID,
    ctx: CtxDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[SectionOut]:
    """章を順に本文つきで返す（文書ビューアの整形表示、specs/007-document-viewer R10）。"""
    doc, _ = await _readable_doc(ctx, doc_id)
    rows = await ctx.session.execute(
        select(Section, _section_counts())
        .where(Section.content_hash == doc.content_hash)
        .order_by(Section.ordinal)
        .offset(offset)
        .limit(limit)
    )
    return [SectionOut(**_outline(r), text=r[0].text) for r in rows]


@router.get("/v1/documents/{doc_id}/sections/{section_id}", response_model=SectionOut)
async def section(doc_id: uuid.UUID, section_id: uuid.UUID, ctx: CtxDep) -> SectionOut:
    doc, _ = await _readable_doc(ctx, doc_id)
    row = (
        await ctx.session.execute(
            select(Section, _section_counts()).where(
                Section.id == section_id, Section.content_hash == doc.content_hash
            )
        )
    ).one_or_none()
    if row is None:
        raise not_found()
    return SectionOut(**_outline(row), text=row[0].text)


@router.get("/v1/documents/{doc_id}/chunks", response_model=list[ChunkOut])
async def chunks(
    doc_id: uuid.UUID,
    ctx: CtxDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[ChunkOut]:
    doc, _ = await _readable_doc(ctx, doc_id)
    rows = await ctx.session.scalars(
        select(Chunk)
        .where(Chunk.content_hash == doc.content_hash)
        .order_by(Chunk.ordinal)
        .offset(offset)
        .limit(limit)
    )
    return [
        ChunkOut(
            id=c.id,
            section_id=c.section_id,
            ordinal=c.ordinal,
            block_type=c.block_type,
            heading_path=c.heading_path,
            page_start=c.page_start,
            page_end=c.page_end,
            text=c.text,
            context=c.context,
            context_source=c.context_source,
            token_len=c.token_len,
            boxes=c.boxes,
            body=f"{c.context}\n\n{c.text}" if c.context else c.text,
        )
        for c in rows
    ]


_ASSET = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_ASSET_MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}


@router.get("/v1/documents/{doc_id}/assets/{name}")
async def asset(request: Request, doc_id: uuid.UUID, name: str, ctx: CtxDep) -> Response:
    doc, _ = await _readable_doc(ctx, doc_id)
    if not _ASSET.match(name) or name.startswith("."):
        raise not_found()
    storage: Storage = request.app.state.storage
    key = f"{content_prefix(doc.content_hash)}/assets/{name}"
    try:
        if not await storage.exists(key):
            raise not_found()
        data = await storage.read(key)
    except StorageError as e:
        raise not_found() from e
    mime = _ASSET_MIME.get(name.rsplit(".", 1)[-1].lower(), "application/octet-stream")
    return Response(data, media_type=mime, headers={"Cache-Control": "private, max-age=86400"})


# ---------------------------------------------------------------- ごみ箱


@router.get("/v1/trash", response_model=list[TrashItem])
async def trash(request: Request, ctx: CtxDep) -> list[TrashItem]:
    """自分が復元できるもの（書込権のある KB 内）だけを、削除の新しい順に返す。"""
    settings: Settings = request.app.state.settings
    retention = timedelta(days=settings.trash_retention_days)
    now = service.utcnow()
    p = ctx.access
    writable_kb = service.writable_kb_clause(p)
    # ごみ箱の KB を戻せる人: 個人 KB の持ち主と、共有 KB の管理者・admin（specs/024）
    managed_kb = or_(
        and_(KnowledgeBase.kind == "personal", KnowledgeBase.owner_user_id == p.user_id),
        and_(
            KnowledgeBase.kind == "org",
            KnowledgeBase.id.is_not(None)
            if p.is_admin
            else KnowledgeBase.id.in_(p.org_kb_ids_at_least("manager")),
        ),
    )

    def remaining(ts: datetime) -> int:
        return max(0, (ts + retention - now).days)

    items: list[TrashItem] = []
    kbs = await ctx.session.scalars(
        select(KnowledgeBase).where(KnowledgeBase.deleted_at.is_not(None), managed_kb)
    )
    for kb in kbs:
        assert kb.deleted_at is not None
        items.append(
            TrashItem(
                kind="kb",
                id=kb.id,
                name=kb.name,
                kb_id=kb.id,
                kb_name=kb.name,
                deleted_at=kb.deleted_at,
                deleted_by=kb.deleted_by,
                remaining_days=remaining(kb.deleted_at),
                purgeable=False,
            )
        )
    parent = Folder.__table__.alias("parent")
    folders = await ctx.session.execute(
        select(Folder, KnowledgeBase)
        .join(KnowledgeBase, KnowledgeBase.id == Folder.kb_id)
        .outerjoin(parent, parent.c.id == Folder.parent_id)
        .where(
            Folder.deleted_at.is_not(None),
            KnowledgeBase.deleted_at.is_(None),
            writable_kb,
            # 同じ操作で消えた配下は親にまとめて表示する
            or_(parent.c.id.is_(None), parent.c.deleted_at.is_distinct_from(Folder.deleted_at)),
        )
    )
    for f, kb in folders:
        assert f.deleted_at is not None
        # 完全削除できるか（配下の文書も同じ規則で確かめる）
        if perm.can_write_ignoring_trash(p, kb) and perm.purge_any_time(p, kb):
            purgeable = True
        else:
            sub = await service.subtree_ids(ctx.session, f.id)
            sub_docs = list(await ctx.session.scalars(select(Document).where(Document.folder_id.in_(sub))))
            purgeable = perm.can_purge_folder(p, kb, f, sub_docs, now)
        items.append(
            TrashItem(
                kind="folder",
                id=f.id,
                name=f.name,
                kb_id=kb.id,
                kb_name=kb.name,
                deleted_at=f.deleted_at,
                deleted_by=f.deleted_by,
                remaining_days=remaining(f.deleted_at),
                purgeable=purgeable,
            )
        )
    docs = await ctx.session.execute(
        select(Document, KnowledgeBase, Folder.deleted_at)
        .join(KnowledgeBase, KnowledgeBase.id == Document.kb_id)
        .outerjoin(Folder, Folder.id == Document.folder_id)
        .where(Document.deleted_at.is_not(None), KnowledgeBase.deleted_at.is_(None), writable_kb)
    )
    for d, kb, folder_deleted_at in docs:
        assert d.deleted_at is not None
        if folder_deleted_at is not None and folder_deleted_at == d.deleted_at:
            continue  # フォルダごと消えたもの
        items.append(
            TrashItem(
                kind="document",
                id=d.id,
                name=d.filename,
                kb_id=kb.id,
                kb_name=kb.name,
                deleted_at=d.deleted_at,
                deleted_by=d.deleted_by,
                remaining_days=remaining(d.deleted_at),
                purgeable=perm.can_purge(p, kb, d, now),
            )
        )
    items.sort(key=lambda i: i.deleted_at, reverse=True)
    return items
