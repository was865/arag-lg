"""KB・フォルダの操作（権限判定は呼び出し前に kb.permissions で行う）。"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from arag.db.models import Chunk, Document, Folder, KnowledgeBase
from arag.errors import ApiError, not_found
from arag.kb import permissions as perm
from arag.kb.access import Access

PERSONAL_KB_NAME = "個人ナレッジベース"


def utcnow() -> datetime:
    return datetime.now(UTC)


def folder_conflict() -> ApiError:
    return ApiError(409, "folder_name_conflict", "同じ場所に同じ名前のフォルダがあります")


# ---------------------------------------------------------------- KB


async def ensure_personal_kb(session: AsyncSession, user_id: str) -> None:
    """個人 KB を（無ければ）1 つ作る。部分 UNIQUE で並行要求でも 1 件（R3）。"""
    stmt = (
        pg_insert(KnowledgeBase)
        .values(id=uuid.uuid4(), kind="personal", owner_user_id=user_id, name=PERSONAL_KB_NAME)
        .on_conflict_do_nothing(
            index_elements=["owner_user_id"],
            index_where=text("kind = 'personal' AND deleted_at IS NULL"),
        )
    )
    await session.execute(stmt)


def readable_kb_clause(a: Access) -> Any:
    """読める KB（個人 KB の持ち主か、共有リストに当たる共有 KB）。ごみ箱は呼ぶ側で除く。"""
    return or_(
        (KnowledgeBase.kind == "personal") & (KnowledgeBase.owner_user_id == a.user_id),
        (KnowledgeBase.kind == "org") & KnowledgeBase.id.in_(a.readable_org_kb_ids),
    )


def writable_kb_clause(a: Access) -> Any:
    return or_(
        (KnowledgeBase.kind == "personal") & (KnowledgeBase.owner_user_id == a.user_id),
        (KnowledgeBase.kind == "org") & KnowledgeBase.id.in_(a.org_kb_ids_at_least("editor")),
    )


async def list_kbs(
    session: AsyncSession, a: Access, *, manageable: bool = False
) -> list[tuple[KnowledgeBase, int]]:
    """読める KB。manageable なら、admin には読めない共有 KB も足す（共有リストの管理のため）。"""
    doc_count = (
        select(func.count(Document.id))
        .where(Document.kb_id == KnowledgeBase.id, Document.deleted_at.is_(None))
        .scalar_subquery()
    )
    rows = await session.execute(
        select(KnowledgeBase, doc_count)
        .where(
            KnowledgeBase.deleted_at.is_(None),
            or_(readable_kb_clause(a), KnowledgeBase.kind == "org")
            if manageable and a.is_admin
            else readable_kb_clause(a),
        )
        .order_by(KnowledgeBase.kind.desc(), KnowledgeBase.created_at)  # personal → org
    )
    return [(kb, int(n)) for kb, n in rows]


async def get_kb_any(session: AsyncSession, kb_id: uuid.UUID) -> KnowledgeBase | None:
    return await session.get(KnowledgeBase, kb_id)


async def get_readable_kb(session: AsyncSession, a: Access, kb_id: uuid.UUID) -> KnowledgeBase:
    kb = await session.get(KnowledgeBase, kb_id)
    if kb is None or not perm.can_read(a, kb):
        raise not_found()
    return kb


async def get_writable_kb(session: AsyncSession, a: Access, kb_id: uuid.UUID) -> KnowledgeBase:
    kb = await get_readable_kb(session, a, kb_id)
    if not perm.can_write(a, kb):
        raise ApiError(403, "forbidden", "このナレッジベースを変更する権限がありません")
    return kb


async def count_docs(session: AsyncSession, kb_id: uuid.UUID) -> int:
    n = await session.scalar(
        select(func.count(Document.id)).where(Document.kb_id == kb_id, Document.deleted_at.is_(None))
    )
    return int(n or 0)


async def content_hashes_of_kb(session: AsyncSession, kb_id: uuid.UUID) -> set[str]:
    rows = await session.scalars(select(Document.content_hash).where(Document.kb_id == kb_id).distinct())
    return set(rows)


# ---------------------------------------------------------------- フォルダ


async def list_folders(session: AsyncSession, kb_id: uuid.UUID) -> list[tuple[Folder, int]]:
    doc_count = (
        select(func.count(Document.id))
        .where(Document.folder_id == Folder.id, Document.deleted_at.is_(None))
        .scalar_subquery()
    )
    rows = await session.execute(
        select(Folder, doc_count)
        .where(Folder.kb_id == kb_id, Folder.deleted_at.is_(None))
        .order_by(Folder.name)
    )
    return [(f, int(n)) for f, n in rows]


async def get_folder(session: AsyncSession, folder_id: uuid.UUID) -> Folder | None:
    return await session.get(Folder, folder_id)


async def require_live_folder_in_kb(
    session: AsyncSession, kb_id: uuid.UUID, folder_id: uuid.UUID | None
) -> Folder | None:
    if folder_id is None:
        return None
    folder = await session.get(Folder, folder_id)
    if folder is None or folder.kb_id != kb_id or folder.deleted_at is not None:
        raise ApiError(400, "invalid_folder", "指定したフォルダが見つかりません")
    return folder


async def _flush_or_conflict(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise folder_conflict() from e


async def create_folder(
    session: AsyncSession, kb_id: uuid.UUID, name: str, parent_id: uuid.UUID | None
) -> Folder:
    await require_live_folder_in_kb(session, kb_id, parent_id)
    folder = Folder(id=uuid.uuid4(), kb_id=kb_id, parent_id=parent_id, name=name)
    session.add(folder)
    await _flush_or_conflict(session)
    return folder


async def ancestor_ids(session: AsyncSession, folder_id: uuid.UUID) -> list[uuid.UUID]:
    """自分を含む祖先の ID（近い順）。"""
    rows = await session.execute(
        text(
            """
            WITH RECURSIVE a AS (
              SELECT id, parent_id, 0 AS depth FROM app.folders WHERE id = :id
              UNION ALL
              SELECT f.id, f.parent_id, a.depth + 1 FROM app.folders f JOIN a ON f.id = a.parent_id
            )
            SELECT id FROM a ORDER BY depth
            """
        ),
        {"id": folder_id},
    )
    return [r[0] for r in rows]


async def update_folder(
    session: AsyncSession,
    folder: Folder,
    *,
    name: str | None,
    move: bool,
    parent_id: uuid.UUID | None,
) -> Folder:
    if move and parent_id != folder.parent_id:
        await require_live_folder_in_kb(session, folder.kb_id, parent_id)
        if parent_id is not None and folder.id in await ancestor_ids(session, parent_id):
            raise ApiError(400, "folder_cycle", "フォルダを自分自身や配下のフォルダへは移動できません")
        folder.parent_id = parent_id
    if name is not None:
        folder.name = name
    await _flush_or_conflict(session)
    return folder


async def subtree_ids(session: AsyncSession, folder_id: uuid.UUID) -> list[uuid.UUID]:
    rows = await session.execute(
        text(
            """
            WITH RECURSIVE t AS (
              SELECT id FROM app.folders WHERE id = :id
              UNION ALL
              SELECT f.id FROM app.folders f JOIN t ON f.parent_id = t.id
            )
            SELECT id FROM t
            """
        ),
        {"id": folder_id},
    )
    return [r[0] for r in rows]


async def trash_folder(session: AsyncSession, folder: Folder, user_id: str) -> set[str]:
    """フォルダを配下ごとごみ箱へ（R33）。影響した内容ハッシュを返す（Qdrant payload 同期用）。"""
    now = utcnow()
    ids = await subtree_ids(session, folder.id)
    await session.execute(
        update(Folder)
        .where(Folder.id.in_(ids), Folder.deleted_at.is_(None))
        .values(deleted_at=now, deleted_by=user_id)
    )
    hashes = await session.scalars(
        update(Document)
        .where(Document.folder_id.in_(ids), Document.deleted_at.is_(None))
        .values(deleted_at=now, deleted_by=user_id)
        .returning(Document.content_hash)
    )
    return set(hashes)


async def folder_purge_plan(session: AsyncSession, folder: Folder) -> tuple[list[uuid.UUID], list[Document]]:
    """完全削除の対象（配下のフォルダ id・文書）。配下にごみ箱にないものがあれば 409。"""
    ids = await subtree_ids(session, folder.id)
    live = await session.scalar(
        select(func.count()).select_from(Folder).where(Folder.id.in_(ids), Folder.deleted_at.is_(None))
    )
    live_docs = await session.scalar(
        select(func.count())
        .select_from(Document)
        .where(Document.folder_id.in_(ids), Document.deleted_at.is_(None))
    )
    if live or live_docs:
        raise ApiError(409, "folder_has_live_items", "このフォルダの中に、ごみ箱にないものがあります")
    docs = list(await session.scalars(select(Document).where(Document.folder_id.in_(ids))))
    return ids, docs


async def revive_ancestors(session: AsyncSession, folder_id: uuid.UUID | None) -> None:
    """削除済みの祖先フォルダを生き返らせる（その祖先の他の配下は戻さない）。"""
    if folder_id is None:
        return
    ids: Sequence[uuid.UUID] = await ancestor_ids(session, folder_id)
    await session.execute(
        update(Folder)
        .where(Folder.id.in_(ids), Folder.deleted_at.is_not(None))
        .values(deleted_at=None, deleted_by=None)
    )


async def restore_folder(session: AsyncSession, folder: Folder) -> set[str]:
    """同じ削除操作（同じ deleted_at）で消えた配下と文書を戻し、祖先も復活させる（R33）。"""
    ts = folder.deleted_at
    if ts is None:
        return set()
    ids = await subtree_ids(session, folder.id)
    await revive_ancestors(session, folder.parent_id)
    await session.execute(
        update(Folder)
        .where(Folder.id.in_(ids), Folder.deleted_at == ts)
        .values(deleted_at=None, deleted_by=None)
    )
    hashes = await session.scalars(
        update(Document)
        .where(Document.folder_id.in_(ids), Document.deleted_at == ts)
        .values(deleted_at=None, deleted_by=None)
        .returning(Document.content_hash)
    )
    result = set(hashes)
    await _flush_or_conflict(session)
    return result


# ---------------------------------------------------------------- 内容単位の可視性（ジョブ・進捗）


async def visible_document_for_content(
    session: AsyncSession, a: Access, content_hash: str, *, write: bool = False
) -> Document | None:
    """利用者が見られる（write=True なら書ける）生存文書のうち最新の 1 件。R30。"""
    doc: Document | None = await session.scalar(
        select(Document)
        .join(KnowledgeBase, KnowledgeBase.id == Document.kb_id)
        .where(
            Document.content_hash == content_hash,
            Document.deleted_at.is_(None),
            KnowledgeBase.deleted_at.is_(None),
            writable_kb_clause(a) if write else readable_kb_clause(a),
        )
        .order_by(Document.created_at.desc())
        .limit(1)
    )
    return doc


async def count_chunks(session: AsyncSession, content_hash: str) -> int:
    n = await session.scalar(select(func.count(Chunk.id)).where(Chunk.content_hash == content_hash))
    return int(n or 0)
