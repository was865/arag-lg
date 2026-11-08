"""KB 権限の表駆動テスト（specs/003-ingestion B1）。"""

from datetime import UTC, datetime, timedelta

import pytest

from arag.auth.principal import Principal, Role
from arag.db.models import Document, KnowledgeBase
from arag.kb import permissions as perm

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def _kb(kind: str, owner: str | None = None, deleted: bool = False) -> KnowledgeBase:
    return KnowledgeBase(kind=kind, owner_user_id=owner, name="kb", deleted_at=NOW if deleted else None)


def _p(role: Role, uid: str = "me") -> Principal:
    return Principal(user_id=uid, role=role)


# (KB, 利用者, 閲覧, 書込)
CASES = [
    (_kb("personal", "me"), _p("member"), True, True),
    (_kb("personal", "other"), _p("member"), False, False),
    (_kb("personal", "other"), _p("admin"), False, False),
    (_kb("personal", "other"), _p("owner"), False, False),
    (_kb("org"), _p("member"), True, False),
    (_kb("org"), _p("admin"), True, True),
    (_kb("org"), _p("owner"), True, True),
    (_kb("org", deleted=True), _p("admin"), False, False),
    (_kb("personal", "me", deleted=True), _p("member"), False, False),
]


@pytest.mark.parametrize(("kb", "p", "read", "write"), CASES)
def test_read_write(kb: KnowledgeBase, p: Principal, read: bool, write: bool) -> None:
    assert perm.can_read(p, kb) is read
    assert perm.can_write(p, kb) is write


@pytest.mark.parametrize(
    ("kb", "p", "expected"),
    [
        (_kb("org"), _p("admin"), True),
        (_kb("org"), _p("member"), False),
        (_kb("personal", "me"), _p("admin", "me"), False),
    ],
)
def test_manage_org_kb(kb: KnowledgeBase, p: Principal, expected: bool) -> None:
    assert perm.can_manage_org_kb(p, kb) is expected


def _doc(uploaded_by: str, deleted_ago: timedelta | None) -> Document:
    return Document(
        filename="a.pdf",
        uploaded_by=uploaded_by,
        deleted_at=None if deleted_ago is None else NOW - deleted_ago,
    )


@pytest.mark.parametrize(
    ("kb", "p", "doc", "expected"),
    [
        # 本人: 24 時間以内なら可、過ぎたら不可
        (_kb("personal", "me"), _p("member"), _doc("me", timedelta(hours=23)), True),
        (_kb("personal", "me"), _p("member"), _doc("me", timedelta(hours=25)), False),
        # admin はいつでも
        (_kb("org"), _p("admin"), _doc("someone", timedelta(days=10)), True),
        # 書込権の無い全社 KB の本人（member）は不可
        (_kb("org"), _p("member"), _doc("me", timedelta(hours=1)), False),
        # ごみ箱に入っていない文書は完全削除できない
        (_kb("org"), _p("admin"), _doc("me", None), False),
        # admin でも他人の個人 KB は不可
        (_kb("personal", "other"), _p("admin"), _doc("other", timedelta(hours=1)), False),
        # KB ごとごみ箱でも、権限があれば可
        (_kb("org", deleted=True), _p("admin"), _doc("x", timedelta(days=1)), True),
    ],
)
def test_can_purge(kb: KnowledgeBase, p: Principal, doc: Document, expected: bool) -> None:
    assert perm.can_purge(p, kb, doc, NOW) is expected
