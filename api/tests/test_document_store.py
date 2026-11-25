"""文書の読み出しの口（specs/037 R11）: ツールの中身を DB なしで確かめる。"""

import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from arag.agent import ops
from arag.agent.context import RunContext
from arag.agent.documents import DocumentStore, Listing
from arag.agent.domain.tool_output import ToolOutput
from arag.auth.principal import Principal
from tests.agent_fakes import FakeSearch, null_sessionmaker

DOC = SimpleNamespace(id=uuid.uuid4(), filename="規程.pdf", content_hash="h1")


def _sec(i: int, text: str) -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        heading_path=f"第{i}章",
        page_start=i,
        text=text,
        level=1,
        token_len=10,
        content_hash="h1",
    )


class FakeStore:
    def __init__(self, *, empty: bool = False, sections: list[Any] | None = None) -> None:
        self.empty = empty
        self.secs = sections or []

    async def list_documents(self, query: str | None, limit: int) -> list[Listing] | None:
        if self.empty:
            return None
        rows = [Listing(DOC.id, DOC.filename, datetime(2026, 11, 1), 3, "ready")]
        return [r for r in rows if not query or query in r.filename][:limit]

    async def document(self, document_id: uuid.UUID) -> Any:
        return DOC if document_id == DOC.id and not self.empty else None

    async def documents_named(self, fragment: str, limit: int) -> list[Any] | None:
        return None if self.empty else [DOC] if fragment in DOC.filename else []

    async def sections(self, content_hash: str) -> list[Any]:
        return self.secs

    async def section(self, section_id: uuid.UUID) -> tuple[Any, list[Any]] | None:
        sec = next((s for s in self.secs if s.id == section_id), None)
        return None if sec is None else (sec, [] if self.empty else [DOC])

    async def sheet_sections(self, content_hash: str, headings: list[str]) -> list[Any]:
        return [s for s in self.secs if s.heading_path in headings]

    async def recent(self, user_id: str, limit: int) -> list[str]:
        return [] if self.empty else [DOC.filename]

    async def named_in(self, question_flat: str, stem_min: int, limit: int) -> list[tuple[str, str]] | None:
        return None if self.empty else [(str(DOC.id), DOC.filename)]


def ctx(store: FakeStore) -> RunContext:
    return RunContext(
        principal=Principal(user_id="u"),
        sessionmaker=null_sessionmaker,
        search=FakeSearch("x"),
        document_store=store,
    )


def test_fake_satisfies_the_protocol() -> None:
    assert isinstance(FakeStore(), DocumentStore)


async def test_list_documents_distinguishes_empty_scope_and_no_match() -> None:
    assert (
        await ops.op_list_documents(ctx(FakeStore(empty=True)), "x")
    ).text == "検索範囲に文書がありません。"
    assert "search を使って" in (await ops.op_list_documents(ctx(FakeStore()), "海外")).text
    assert "規程.pdf" in (await ops.op_list_documents(ctx(FakeStore()))).text


async def test_read_document_marks_truncation_as_omitted() -> None:
    secs = [_sec(i, "あ" * 5000) for i in range(1, 5)]
    out = await ops.op_read_document(ctx(FakeStore(sections=secs)), "規程")
    assert isinstance(out, ToolOutput) and out.omitted and out.materials == 2
    short = await ops.op_read_document(ctx(FakeStore(sections=secs[:1])), str(DOC.id))
    assert not short.omitted and short.materials == 1


async def test_read_section_outside_scope_is_not_found() -> None:
    sec = _sec(1, "本文")
    assert (
        "見つかりません"
        in (await ops.op_read_section(ctx(FakeStore(empty=True, sections=[sec])), str(sec.id))).text
    )
    got = await ops.op_read_section(ctx(FakeStore(sections=[sec])), str(sec.id))
    assert got.materials == 1 and "本文" in got.text


async def test_named_documents_through_the_store() -> None:
    assert await ops.find_named_documents(ctx(FakeStore()), "規程.pdf を要約して") == [
        (str(DOC.id), "規程.pdf")
    ]
    assert await ops.find_named_documents(ctx(FakeStore(empty=True)), "規程.pdf を要約して") == []
