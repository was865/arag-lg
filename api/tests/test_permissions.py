"""KB 権限の表駆動テスト（specs/003-ingestion B1、specs/024）。"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from arag.auth.principal import Principal, Role
from arag.db.models import Document, KnowledgeBase
from arag.kb import permissions as perm
from arag.kb.access import Access, ShareRole, stronger

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
ORG_ID = uuid.UUID(int=1)


def _kb(kind: str, owner: str | None = None, deleted: bool = False) -> KnowledgeBase:
    return KnowledgeBase(
        id=ORG_ID if kind == "org" else uuid.UUID(int=2),
        kind=kind,
        owner_user_id=owner,
        name="kb",
        deleted_at=NOW if deleted else None,
    )


def _a(role: Role, share: ShareRole | None = None, uid: str = "me") -> Access:
    """利用者。share は共有 KB（ORG_ID）での役割（共有リストから来るもの）。"""
    return Access(principal=Principal(user_id=uid, role=role), kb_roles={ORG_ID: share} if share else {})


# (KB, 利用者, 閲覧, 書込)
CASES = [
    (_kb("personal", "me"), _a("member"), True, True),
    (_kb("personal", "other"), _a("member"), False, False),
    (_kb("personal", "other"), _a("admin"), False, False),
    (_kb("personal", "other"), _a("owner"), False, False),
    (_kb("org"), _a("member", "viewer"), True, False),
    (_kb("org"), _a("member", "editor"), True, True),
    (_kb("org"), _a("member", "manager"), True, True),
    # 共有リストに無ければ、member も admin も読めない（Q1 案 A）
    (_kb("org"), _a("member"), False, False),
    (_kb("org"), _a("admin"), False, False),
    (_kb("org"), _a("owner"), False, False),
    (_kb("org"), _a("admin", "editor"), True, True),
    (_kb("org", deleted=True), _a("admin", "manager"), False, False),
    (_kb("personal", "me", deleted=True), _a("member"), False, False),
]


@pytest.mark.parametrize(("kb", "a", "read", "write"), CASES)
def test_read_write(kb: KnowledgeBase, a: Access, read: bool, write: bool) -> None:
    assert perm.can_read(a, kb) is read
    assert perm.can_write(a, kb) is write


@pytest.mark.parametrize(
    ("kb", "a", "manage", "view_shares"),
    [
        (_kb("org"), _a("admin"), True, True),  # admin は中身を読めなくても共有リストを管理できる
        (_kb("org"), _a("member", "manager"), True, True),
        (_kb("org"), _a("member", "editor"), False, True),
        (_kb("org"), _a("member", "viewer"), False, True),
        (_kb("org"), _a("member"), False, False),
        (_kb("personal", "me"), _a("admin", uid="me"), False, False),
    ],
)
def test_manage_and_view_shares(kb: KnowledgeBase, a: Access, manage: bool, view_shares: bool) -> None:
    assert perm.can_manage_org_kb(a, kb) is manage
    assert perm.can_view_shares(a, kb) is view_shares


@pytest.mark.parametrize(
    ("kb", "a", "expected"),
    [
        (_kb("personal", "me"), _a("member"), True),
        (_kb("org"), _a("admin"), True),
        (_kb("org"), _a("member", "manager"), True),
        (_kb("org"), _a("member", "editor"), False),
        (_kb("org", deleted=True), _a("admin"), False),
    ],
)
def test_rename(kb: KnowledgeBase, a: Access, expected: bool) -> None:
    assert perm.can_rename_kb(a, kb) is expected


def _doc(uploaded_by: str, deleted_ago: timedelta | None) -> Document:
    return Document(
        filename="a.pdf",
        uploaded_by=uploaded_by,
        deleted_at=None if deleted_ago is None else NOW - deleted_ago,
    )


@pytest.mark.parametrize(
    ("kb", "a", "doc", "expected"),
    [
        # 本人: 24 時間以内なら可、過ぎたら不可
        (_kb("personal", "me"), _a("member"), _doc("me", timedelta(hours=23)), True),
        (_kb("personal", "me"), _a("member"), _doc("me", timedelta(hours=25)), False),
        # 共有 KB の管理者と、書ける admin はいつでも
        (_kb("org"), _a("member", "manager"), _doc("someone", timedelta(days=10)), True),
        (_kb("org"), _a("admin", "editor"), _doc("someone", timedelta(days=10)), True),
        # 編集者の本人は 24 時間以内だけ
        (_kb("org"), _a("member", "editor"), _doc("me", timedelta(hours=1)), True),
        (_kb("org"), _a("member", "editor"), _doc("me", timedelta(hours=25)), False),
        # 書込権の無い本人・役割の無い admin は不可
        (_kb("org"), _a("member", "viewer"), _doc("me", timedelta(hours=1)), False),
        (_kb("org"), _a("admin"), _doc("someone", timedelta(days=1)), False),
        # ごみ箱に入っていない文書は完全削除できない
        (_kb("org"), _a("member", "manager"), _doc("me", None), False),
        # admin でも他人の個人 KB は不可
        (_kb("personal", "other"), _a("admin"), _doc("other", timedelta(hours=1)), False),
        # KB ごとごみ箱でも、権限があれば可
        (_kb("org", deleted=True), _a("member", "manager"), _doc("x", timedelta(days=1)), True),
    ],
)
def test_can_purge(kb: KnowledgeBase, a: Access, doc: Document, expected: bool) -> None:
    assert perm.can_purge(a, kb, doc, NOW) is expected


def test_stronger_role_wins() -> None:
    assert stronger("viewer", "editor") == "editor"
    assert stronger("manager", "viewer") == "manager"
    assert stronger(None, "viewer") == "viewer"
