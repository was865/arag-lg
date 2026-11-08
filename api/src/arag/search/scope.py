"""検索範囲の解決（specs/004-retrieval R1〜R3）。"""

from dataclasses import dataclass

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from arag.auth.principal import Principal
from arag.db.models import Document, KnowledgeBase
from arag.kb.permissions import can_read
from arag.search.schemas import SearchRequest


@dataclass(frozen=True, slots=True)
class Scope:
    kb_ids: list[str]
    # None = 文書の指定なし。[] = 指定はあったが見える文書が無い（0 件を返す）
    document_ids: list[str] | None

    @property
    def empty(self) -> bool:
        return not self.kb_ids or self.document_ids == []


async def resolve_scope(session: AsyncSession, p: Principal, req: SearchRequest) -> Scope:
    rows = await session.scalars(
        select(KnowledgeBase).where(
            KnowledgeBase.deleted_at.is_(None),
            or_(
                KnowledgeBase.kind == "org",
                and_(KnowledgeBase.kind == "personal", KnowledgeBase.owner_user_id == p.user_id),
            ),
        )
    )
    readable = [kb for kb in rows if can_read(p, kb)]
    if req.kb_ids is not None:
        # 明示した KB はアーカイブ済みでも対象（旧版と同じ）。見えない ID は黙って除く
        wanted = {str(k) for k in req.kb_ids}
        kbs = [kb for kb in readable if str(kb.id) in wanted]
    else:
        kbs = [kb for kb in readable if kb.status == "active" or req.include_archived]
    kb_ids = sorted(str(kb.id) for kb in kbs)
    doc_ids: list[str] | None = None
    if req.document_ids is not None and kb_ids:
        found = await session.scalars(
            select(Document.id).where(
                Document.id.in_(req.document_ids),
                Document.deleted_at.is_(None),
                Document.kb_id.in_([kb.id for kb in kbs]),
            )
        )
        doc_ids = sorted(str(d) for d in found)
    elif req.document_ids is not None:
        doc_ids = []
    return Scope(kb_ids=kb_ids, document_ids=doc_ids)
