"""文書の読み出しの口（specs/037 R11）。

ツールの中身（ops.py）は DB を直接読まず、この口を通す。どの読み出しも、利用者の閲覧範囲と run の検索範囲
（ナレッジベース・文書の指定・アーカイブを含むか）の中だけを見る。
本番の実装は adapters/sql_documents.py（SqlDocumentStore）。
返す行は ORM の行（Document・Section）を読み取りだけに使う。
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from arag.db.models import Document, Section


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
