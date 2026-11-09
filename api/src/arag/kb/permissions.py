"""KB の権限判定（純関数。specs/003-ingestion R4〜R6・R34、specs/024）。

- 個人 KB: 持ち主だけが「管理」。admin でも他人の個人 KB は見えない。
- 共有 KB（kind=org）: 共有リスト（Access.kb_roles）の役割。閲覧 < 編集 < 管理。
  admin は共有リストの変更・名前変更・アーカイブ・削除・復元ができるが、
  役割が無ければ中身は読めない（Q1 案 A）。
- アーカイブは検索から外すだけで、閲覧・書込は変わらない（旧版どおり）。
- ごみ箱の KB は閲覧・書込とも不可（復元と完全削除だけが対象）。
"""

from datetime import datetime, timedelta

from arag.db.models import Document, Folder, KnowledgeBase
from arag.kb.access import RANK, Access

PURGE_GRACE = timedelta(hours=24)


def role_of(a: Access, kb: KnowledgeBase) -> str | None:
    if kb.kind == "personal":
        return "manager" if kb.owner_user_id == a.user_id else None
    return a.kb_roles.get(kb.id)


def _at_least(a: Access, kb: KnowledgeBase, role: str) -> bool:
    r = role_of(a, kb)
    return r is not None and RANK[r] >= RANK[role]


def can_see_ignoring_trash(a: Access, kb: KnowledgeBase) -> bool:
    """ごみ箱状態を無視した閲覧権（ごみ箱一覧・復元の判定用）。"""
    return role_of(a, kb) is not None


def can_write_ignoring_trash(a: Access, kb: KnowledgeBase) -> bool:
    return _at_least(a, kb, "editor")


def can_read(a: Access, kb: KnowledgeBase) -> bool:
    return kb.deleted_at is None and can_see_ignoring_trash(a, kb)


def can_write(a: Access, kb: KnowledgeBase) -> bool:
    return kb.deleted_at is None and can_write_ignoring_trash(a, kb)


def can_manage_org_kb(a: Access, kb: KnowledgeBase) -> bool:
    """共有リスト・名前変更・アーカイブ・削除・復元。個人 KB は対象外（P5 の退職処理で扱う）。"""
    return kb.kind == "org" and (a.is_admin or _at_least(a, kb, "manager"))


def can_view_shares(a: Access, kb: KnowledgeBase) -> bool:
    """共有リストを見られる: 読める人（誰に見えているかを知るため）と、管理できる人。"""
    return kb.kind == "org" and (can_see_ignoring_trash(a, kb) or can_manage_org_kb(a, kb))


def can_rename_kb(a: Access, kb: KnowledgeBase) -> bool:
    if kb.deleted_at is not None:
        return False
    return can_manage_org_kb(a, kb) if kb.kind == "org" else role_of(a, kb) is not None


def purge_any_time(a: Access, kb: KnowledgeBase) -> bool:
    if kb.kind == "org" and _at_least(a, kb, "manager"):
        return True
    return a.is_admin and can_write_ignoring_trash(a, kb)


def can_purge(a: Access, kb: KnowledgeBase, doc: Document, now: datetime) -> bool:
    """完全削除: 共有 KB の管理者と書ける admin はいつでも、アップロード本人は削除後 24 時間以内（R34）。"""
    if doc.deleted_at is None or not can_write_ignoring_trash(a, kb):
        return False
    if purge_any_time(a, kb):
        return True
    return doc.uploaded_by == a.user_id and now - doc.deleted_at <= PURGE_GRACE


def can_purge_folder(
    a: Access, kb: KnowledgeBase, folder: Folder, docs: list[Document], now: datetime
) -> bool:
    """フォルダの完全削除: 管理者はいつでも。本人は削除後 24 時間以内で、配下の文書がすべて自分のものなら。"""
    if folder.deleted_at is None or not can_write_ignoring_trash(a, kb):
        return False
    if purge_any_time(a, kb):
        return True
    if folder.deleted_by != a.user_id or now - folder.deleted_at > PURGE_GRACE:
        return False
    return all(can_purge(a, kb, d, now) for d in docs)
