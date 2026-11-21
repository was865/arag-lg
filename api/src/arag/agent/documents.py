"""文書の読み出しの口（specs/037 R11）。

ツールの中身（ops.py）は DB を直接読まず、この口を通す。どの読み出しも、利用者の閲覧範囲と run の検索範囲
（ナレッジベース・文書の指定・アーカイブを含むか）の中だけを見る。本番は SQLAlchemy（SqlDocumentStore）。
返す行は ORM の行（Document・Section）を読み取りだけに使う。
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import String, and_, bindparam, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql import Select

from arag.auth.principal import Principal
from arag.db.models import Content, Document, Section
from arag.search.schemas import SearchRequest
from arag.search.scope import Scope, resolve_scope


@dataclass(frozen=True)
class Listing:
    """文書の一覧の 1 行。"""

    id: uuid.UUID
    filename: str
    created_at: datetime
    page_count: int | None
    status: str


@runtime_checkable
class DocumentStore(Protocol):
    async def list_documents(self, query: str | None, limit: int) -> list[Listing] | None:
        """範囲の文書（名前順、名前の一部で絞る）。範囲が空なら None。"""
        ...

    async def document(self, document_id: uuid.UUID) -> Document | None:
        """範囲の中の文書。"""
        ...

    async def documents_named(self, fragment: str, limit: int) -> list[Document] | None:
        """名前にその語を含む範囲の文書（名前順）。範囲が空なら None。"""
        ...

    async def sections(self, content_hash: str) -> list[Section]:
        """文書の本文の章（順に）。"""
        ...

    async def section(self, section_id: uuid.UUID) -> tuple[Section, list[Document]] | None:
        """章と、その本文を持つ範囲の文書（登録の古い順）。章が無ければ None。"""
        ...

    async def sheet_sections(self, content_hash: str, headings: list[str]) -> list[Section]:
        """同じ本文の、見出しが headings のどれかの章（順に）。"""
        ...

    async def recent(self, user_id: str, limit: int) -> list[str]:
        """範囲の中で、その利用者が最近登録した文書の名前（新しい順）。"""
        ...

    async def named_in(self, question_flat: str, stem_min: int, limit: int) -> list[tuple[str, str]] | None:
        """名前全体（または十分長い拡張子なしの名前）が質問に含まれる文書（ID・名前）。範囲が空なら None。"""
        ...


class SqlDocumentStore:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        principal: Principal,
        *,
        kb_ids: list[uuid.UUID] | None = None,
        document_ids: list[uuid.UUID] | None = None,
        include_archived: bool = False,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.principal = principal
        self.kb_ids = kb_ids
        self.document_ids = document_ids
        self.include_archived = include_archived

    async def _scope(self, s: AsyncSession) -> Scope:
        req = SearchRequest(
            query="範囲",
            kb_ids=self.kb_ids,
            document_ids=self.document_ids,
            include_archived=self.include_archived,
            top_k=1,
            candidate_k=1,
        )
        return await resolve_scope(s, self.principal, req)

    @staticmethod
    def _in_scope[Q: Select[*tuple[Any, ...]]](q: Q, scope: Scope) -> Q:
        q = q.where(Document.deleted_at.is_(None), Document.kb_id.in_([uuid.UUID(k) for k in scope.kb_ids]))
        if scope.document_ids is not None:
            q = q.where(Document.id.in_([uuid.UUID(d) for d in scope.document_ids]))
        return q

    async def list_documents(self, query: str | None, limit: int) -> list[Listing] | None:
        async with self.sessionmaker() as s:
            scope = await self._scope(s)
            if scope.empty:
                return None
            q = self._in_scope(
                select(
                    Document.id, Document.filename, Document.created_at, Content.page_count, Content.status
                )
                .join(Content, Content.content_hash == Document.content_hash)
                .order_by(Document.filename)
                .limit(limit),
                scope,
            )
            if query and query.strip():
                q = q.where(Document.filename.ilike(f"%{query.strip()}%"))
            rows = (await s.execute(q)).all()
        return [Listing(r.id, r.filename, r.created_at, r.page_count, r.status) for r in rows]

    async def document(self, document_id: uuid.UUID) -> Document | None:
        async with self.sessionmaker() as s:
            scope = await self._scope(s)
            if scope.empty:
                return None
            q = self._in_scope(select(Document).where(Document.id == document_id), scope)
            return (await s.scalars(q)).first()

    async def documents_named(self, fragment: str, limit: int) -> list[Document] | None:
        async with self.sessionmaker() as s:
            scope = await self._scope(s)
            if scope.empty:
                return None
            q = self._in_scope(select(Document).where(Document.filename.ilike(f"%{fragment}%")), scope)
            return list((await s.scalars(q.order_by(Document.filename).limit(limit))).all())

    async def sections(self, content_hash: str) -> list[Section]:
        async with self.sessionmaker() as s:
            return list(
                await s.scalars(
                    select(Section).where(Section.content_hash == content_hash).order_by(Section.ordinal)
                )
            )

    async def section(self, section_id: uuid.UUID) -> tuple[Section, list[Document]] | None:
        async with self.sessionmaker() as s:
            sec = await s.get(Section, section_id)
            if sec is None:
                return None
            scope = await self._scope(s)
            if scope.empty:
                return sec, []
            q = self._in_scope(select(Document).where(Document.content_hash == sec.content_hash), scope)
            return sec, list(await s.scalars(q.order_by(Document.created_at)))

    async def sheet_sections(self, content_hash: str, headings: list[str]) -> list[Section]:
        async with self.sessionmaker() as s:
            return list(
                await s.scalars(
                    select(Section)
                    .where(Section.content_hash == content_hash, Section.heading_path.in_(headings))
                    .order_by(Section.ordinal)
                )
            )

    async def recent(self, user_id: str, limit: int) -> list[str]:
        async with self.sessionmaker() as s:
            scope = await self._scope(s)
            if scope.empty:
                return []
            q = self._in_scope(
                select(Document.filename)
                .where(Document.uploaded_by == user_id)
                .order_by(Document.created_at.desc())
                .limit(limit),
                scope,
            )
            return list((await s.scalars(q)).all())

    async def named_in(self, question_flat: str, stem_min: int, limit: int) -> list[tuple[str, str]] | None:
        async with self.sessionmaker() as s:
            scope = await self._scope(s)
            if scope.empty:
                return None
            # 照合は DB の側で行う（文書が多くても漏らさない）。全角・半角・空白・大文字小文字の違いを無くす
            flat = func.lower(
                func.regexp_replace(
                    literal_column("normalize(app.documents.filename, NFKC)"), r"\s+", "", "g"
                )
            )
            stem = func.regexp_replace(flat, r"\.[^.]*$", "")
            qflat = bindparam("qflat", question_flat, type_=String)
            q = self._in_scope(
                select(Document.id, Document.filename).where(
                    or_(
                        func.strpos(qflat, flat) > 0,
                        and_(func.length(stem) >= stem_min, func.strpos(qflat, stem) > 0),
                    ),
                ),
                scope,
            )
            return [(str(r.id), r.filename) for r in (await s.execute(q.limit(limit))).all()]
