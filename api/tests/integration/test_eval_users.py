"""評価用の利用者（specs/032 R27）: 部門・所属・評価の KB の閲覧を作る。何度流しても同じ。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.db.models import Department, DepartmentMember, KbShare, KnowledgeBase
from arag.eval.users import EvalUser, ensure_users


async def test_ensure_users_is_idempotent(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    users = {
        "seizo": EvalUser(id="eval-seizo", departments=["製造課"]),
        "kobai": EvalUser(id="eval-kobai", departments=["購買課", "資材係"]),
        "none": EvalUser(id="eval-none"),
    }
    async with sessionmaker() as s:
        kb = KnowledgeBase(name="評価: t", kind="org")
        s.add(kb)
        await s.commit()
        made = await ensure_users(s, users, kb.id)
        assert "部門 製造課" in made and "eval-none に評価の KB の閲覧" in made
        assert await ensure_users(s, users, kb.id) == []
        names = set((await s.execute(select(Department.name))).scalars())
        assert {"製造課", "購買課", "資材係"} <= names
        members = (await s.execute(select(DepartmentMember.user_id))).scalars().all()
        assert sorted(members) == ["eval-kobai", "eval-kobai", "eval-seizo"]
        shares = (await s.execute(select(KbShare).where(KbShare.kb_id == kb.id))).scalars().all()
        assert {(x.subject_id, x.role) for x in shares if x.subject_type == "user"} == {
            ("eval-seizo", "viewer"),
            ("eval-kobai", "viewer"),
            ("eval-none", "viewer"),
        }
