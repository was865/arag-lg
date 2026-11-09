"""KB の権限判定（純関数。specs/003-ingestion R4〜R6・R34）。

- 個人 KB: 所有者だけが閲覧・書込。admin でも他人の個人 KB は見えない。
- 全社 KB: 閲覧は全員、書込と管理（名前変更・アーカイブ・削除・復元）は admin。
- アーカイブは検索から外すだけで、閲覧・書込は変わらない（旧版どおり）。
- ごみ箱の KB は閲覧・書込とも不可（復元と完全削除だけが対象）。
"""

from datetime import datetime, timedelta

from arag.auth.principal import Principal
from arag.db.models import Document, Folder, KnowledgeBase

PURGE_GRACE = timedelta(hours=24)


def _owns(p: Principal, kb: KnowledgeBase) -> bool:
    return kb.kind == "personal" and kb.owner_user_id == p.user_id


def can_see_ignoring_trash(p: Principal, kb: KnowledgeBase) -> bool:
    """ごみ箱状態を無視した閲覧権（ごみ箱一覧・復元の判定用）。"""
    return _owns(p, kb) if kb.kind == "personal" else True


def can_write_ignoring_trash(p: Principal, kb: KnowledgeBase) -> bool:
    return _owns(p, kb) if kb.kind == "personal" else p.is_admin


def can_read(p: Principal, kb: KnowledgeBase) -> bool:
    return kb.deleted_at is None and can_see_ignoring_trash(p, kb)


def can_write(p: Principal, kb: KnowledgeBase) -> bool:
    return kb.deleted_at is None and can_write_ignoring_trash(p, kb)


def can_rename_kb(p: Principal, kb: KnowledgeBase) -> bool:
    return can_write(p, kb)


def can_manage_org_kb(p: Principal, kb: KnowledgeBase) -> bool:
    """アーカイブ・削除・復元。個人 KB は対象外（P5 の退職処理で扱う）。"""
    return kb.kind == "org" and p.is_admin


def can_purge(p: Principal, kb: KnowledgeBase, doc: Document, now: datetime) -> bool:
    """完全削除: admin はいつでも、アップロード本人は削除後 24 時間以内（R34）。"""
    if doc.deleted_at is None or not can_write_ignoring_trash(p, kb):
        return False
    if p.is_admin:
        return True
    return doc.uploaded_by == p.user_id and now - doc.deleted_at <= PURGE_GRACE


def can_purge_folder(
    p: Principal, kb: KnowledgeBase, folder: Folder, docs: list[Document], now: datetime
) -> bool:
    """フォルダの完全削除: admin はいつでも。本人は削除後 24 時間以内で、配下の文書がすべて自分のものなら。"""
    if folder.deleted_at is None or not can_write_ignoring_trash(p, kb):
        return False
    if p.is_admin:
        return True
    if folder.deleted_by != p.user_id or now - folder.deleted_at > PURGE_GRACE:
        return False
    return all(can_purge(p, kb, d, now) for d in docs)
