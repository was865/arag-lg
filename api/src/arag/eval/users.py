"""評価用の利用者（specs/032 R27）。題の as_user から、部門に属する利用者として尋ねる。

users.yaml:
    users:
      seizo: {id: eval-seizo, name: 製造課の人, departments: [製造課]}

`arag.cli eval-users` が部門・所属・評価の KB の共有を作る。
"""

import uuid
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from arag.db.models import Department, DepartmentMember, KbShare


class EvalUser(BaseModel):
    id: str = Field(max_length=64)
    name: str = ""
    departments: list[str] = Field(default_factory=list)


def load_users(path: str | Path) -> dict[str, EvalUser]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return {k: EvalUser.model_validate(v) for k, v in (data.get("users") or {}).items()}


def user_headers(user: EvalUser) -> dict[str, str]:
    """開発用の認証で、この利用者として尋ねるヘッダ（一般のメンバー）。"""
    return {"X-Dev-User-Id": user.id, "X-Dev-Role": "member"}


async def ensure_users(session: AsyncSession, users: dict[str, EvalUser], kb_id: uuid.UUID) -> list[str]:
    """部門・所属・評価の KB の閲覧の共有を作る（何度流しても同じ）。作ったものを返す。"""
    made: list[str] = []
    depts = {d.name: d for d in (await session.execute(select(Department))).scalars()}
    for u in users.values():
        for name in u.departments:
            if name not in depts:
                depts[name] = Department(name=name)
                session.add(depts[name])
                await session.flush()
                made.append(f"部門 {name}")
            member = await session.get(DepartmentMember, (depts[name].id, u.id))
            if member is None:
                session.add(DepartmentMember(department_id=depts[name].id, user_id=u.id, role="member"))
                made.append(f"{u.id} → {name}")
        share = await session.scalar(
            select(KbShare).where(
                KbShare.kb_id == kb_id, KbShare.subject_type == "user", KbShare.subject_id == u.id
            )
        )
        if share is None:
            session.add(
                KbShare(kb_id=kb_id, subject_type="user", subject_id=u.id, role="viewer", created_by="eval")
            )
            made.append(f"{u.id} に評価の KB の閲覧")
    await session.commit()
    return made
