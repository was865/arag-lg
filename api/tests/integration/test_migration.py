"""Alembic 0001 の往復と制約（specs/003-ingestion A2）。"""

import os
import subprocess

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.audit import AuditEvent, write_audit
from arag.auth.principal import Principal
from arag.db.models import AuditLog, Folder, KnowledgeBase

from .conftest import API_DIR

pytestmark = pytest.mark.integration


def test_downgrade_and_upgrade_roundtrip(database_url: str) -> None:
    env = {**os.environ, "ARAG_DATABASE_URL": database_url}
    for args in (["downgrade", "base"], ["upgrade", "head"], ["check"]):
        subprocess.run(["uv", "run", "alembic", *args], cwd=API_DIR, env=env, check=True, capture_output=True)


async def test_personal_kb_unique_per_owner(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as s:
        s.add(KnowledgeBase(kind="personal", owner_user_id="u1", name="個人"))
        await s.commit()
    async with sessionmaker() as s:
        s.add(KnowledgeBase(kind="personal", owner_user_id="u1", name="個人2"))
        with pytest.raises(IntegrityError):
            await s.commit()


async def test_folder_sibling_name_unique_among_live_rows(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as s:
        kb = KnowledgeBase(kind="org", name="全社")
        s.add(kb)
        await s.flush()
        s.add(Folder(kb_id=kb.id, name="規程"))
        await s.commit()
        kb_id = kb.id
    # ルート直下（parent_id NULL）でも重複は拒否
    async with sessionmaker() as s:
        s.add(Folder(kb_id=kb_id, name="規程"))
        with pytest.raises(IntegrityError):
            await s.commit()
    # 削除済みなら同名を作れる
    async with sessionmaker() as s:
        await s.execute(text("UPDATE app.folders SET deleted_at = now()"))
        s.add(Folder(kb_id=kb_id, name="規程"))
        await s.commit()


async def test_write_audit(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as s:
        await write_audit(
            s, AuditEvent(action="document.delete", resource_id="d1"), principal=Principal(user_id="u1")
        )
        await s.commit()
        row = (await s.execute(text("SELECT actor_id, action, result FROM app.audit_logs"))).one()
    assert tuple(row) == ("u1", "document.delete", "ok")
    assert AuditLog.__tablename__ == "audit_logs"
