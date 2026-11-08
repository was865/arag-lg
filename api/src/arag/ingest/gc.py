"""ごみ箱の物理削除と、参照の無くなった内容の回収（R35・R36）。"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from arag.audit import AuditEvent, write_audit
from arag.db.models import Content, Document, Folder, KnowledgeBase
from arag.ingest.pipeline import Index
from arag.logging import get_logger
from arag.storage import Storage, content_prefix

log = get_logger("arag.ingest.gc")


async def delete_documents(session: AsyncSession, doc_ids: list[uuid.UUID]) -> set[str]:
    """文書行を物理削除して ref_count を減らす。影響した内容ハッシュを返す。"""
    if not doc_ids:
        return set()
    hashes = list(
        await session.scalars(
            delete(Document).where(Document.id.in_(doc_ids)).returning(Document.content_hash)
        )
    )
    for h in hashes:
        await session.execute(
            update(Content)
            .where(Content.content_hash == h)
            .values(ref_count=func.greatest(Content.ref_count - 1, 0))
        )
    return set(hashes)


async def purge_expired(session: AsyncSession, now: datetime, retention: timedelta) -> dict[str, int]:
    """保持期間を過ぎたごみ箱の文書・フォルダ・KB を物理削除する。"""
    cutoff = now - retention
    expired_kbs = list(
        await session.scalars(select(KnowledgeBase.id).where(KnowledgeBase.deleted_at < cutoff))
    )
    doc_ids = list(
        await session.scalars(
            select(Document.id).where(or_(Document.deleted_at < cutoff, Document.kb_id.in_(expired_kbs)))
        )
    )
    await delete_documents(session, doc_ids)
    folders = await session.execute(
        delete(Folder).where(or_(Folder.deleted_at < cutoff, Folder.kb_id.in_(expired_kbs)))
    )
    kbs = await session.execute(delete(KnowledgeBase).where(KnowledgeBase.id.in_(expired_kbs)))
    return {
        "documents": len(doc_ids),
        "folders": folders.rowcount or 0,  # type: ignore[attr-defined]
        "kbs": kbs.rowcount or 0,  # type: ignore[attr-defined]
    }


async def collect_orphans(session: AsyncSession, storage: Storage, index: Index) -> list[str]:
    """どの文書からも参照されない内容の原本・成果物・チャンク・点を消す（R35）。"""
    orphans = list(
        await session.scalars(
            select(Content.content_hash).where(~exists().where(Document.content_hash == Content.content_hash))
        )
    )
    for h in orphans:
        await index.delete_content(h)
        await storage.delete_prefix(content_prefix(h))
        # sections / chunks / ingest_jobs は ON DELETE CASCADE
        await session.execute(delete(Content).where(Content.content_hash == h))
    return orphans


async def run_gc(
    session: AsyncSession, storage: Storage, index: Index, *, now: datetime, retention: timedelta
) -> dict[str, int]:
    counts = await purge_expired(session, now, retention)
    orphans = await collect_orphans(session, storage, index)
    counts["contents"] = len(orphans)
    if any(counts.values()):
        await write_audit(session, AuditEvent(action="gc.purge", detail=counts))
    await session.commit()
    if any(counts.values()):
        log.info("gc_done", **counts)
    return counts
