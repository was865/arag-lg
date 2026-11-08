"""解析器（specs/003-ingestion D1・D2、R14〜R16・R28）。"""

import base64
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from docling_core.types.doc.base import Size
from docling_core.types.doc.document import DoclingDocument, ImageRef
from pypdf import PdfWriter

from arag.ingest.parser import (
    DoclingServeParser,
    ParseError,
    PlainTextParser,
    page_windows,
    select_parser,
)

from .docling_fixtures import prov, regulation_doc


async def _parse_plain(tmp_path: Path, name: str, content: str | bytes) -> Any:
    p = tmp_path / name
    p.write_bytes(content.encode() if isinstance(content, str) else content)
    return await PlainTextParser().parse(p, name, name.rsplit(".", 1)[1])


async def test_plain_markdown_headings(tmp_path: Path) -> None:
    md = "# 総則\n\n本文1\n\n## 目的\n\n本文2\n\n```\n# コード内は見出しでない\n```\n"
    r = await _parse_plain(tmp_path, "規程.md", md)
    heads = [t.text for t in r.doc.texts if t.label.value == "section_header"]
    assert heads == ["総則", "目的"]
    assert r.markdown == md
    assert r.doc.name == "規程"


async def test_plain_txt_cp932(tmp_path: Path) -> None:
    r = await _parse_plain(tmp_path, "memo.txt", "一段落目\n\n二段落目".encode("cp932"))
    assert [t.text for t in r.doc.texts] == ["一段落目", "二段落目"]


async def test_plain_csv_is_table(tmp_path: Path) -> None:
    r = await _parse_plain(tmp_path, "a.csv", "区分,期間\n機密,10年\n")
    assert len(r.doc.tables) == 1
    assert r.doc.tables[0].data.num_rows == 2


async def test_plain_json_pretty(tmp_path: Path) -> None:
    r = await _parse_plain(tmp_path, "a.json", '{"名前":"x"}')
    assert '"名前": "x"' in r.doc.texts[0].text


def test_page_windows() -> None:
    assert page_windows(45, 20) == [(1, 20), (21, 40), (41, 45)]
    assert page_windows(3, 20) == [(1, 3)]


def test_select_parser_without_docling() -> None:
    plain = PlainTextParser()
    assert select_parser("TXT", plain, None) is plain
    with pytest.raises(ParseError) as e:
        select_parser("pdf", plain, None)
    assert e.value.retryable is False


# ---------------------------------------------------------------- docling-serve（偽サーバ）


def _pdf(tmp_path: Path, pages: int) -> Path:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=600, height=800)
    p = tmp_path / "doc.pdf"
    with p.open("wb") as f:
        w.write(f)
    return p


def _window_doc(start: int, end: int) -> dict[str, Any]:
    doc = DoclingDocument(name="x")
    for p in range(start, end + 1):
        doc.add_page(page_no=p, size=Size(width=600, height=800))
        doc.add_text(label=regulation_doc().texts[2].label, text=f"p{p}", prov=prov(p))
    if start == 1:
        png = base64.b64encode(b"\x89PNG fake").decode()
        doc.add_picture(
            image=ImageRef(
                mimetype="image/png",
                dpi=72,
                size=Size(width=10, height=10),
                uri=f"data:image/png;base64,{png}",
            ),
            prov=prov(1),
        )
    return doc.export_to_dict()


class FakeDocling:
    def __init__(self, *, fail: str | None = None, pending_polls: int = 1) -> None:
        self.fail = fail
        self.pending_polls = pending_polls
        self.requests: list[dict[str, Any]] = []
        self._tasks: dict[str, tuple[int, int]] = {}
        self._polls: dict[str, int] = {}

    def handler(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/v1/convert/file/async":
            body = req.content.decode("latin-1")
            pr = [int(x) for x in _form_values(body, "page_range")]
            self.requests.append({"page_range": pr, "ocr_lang": _form_values(body, "ocr_lang"), "body": body})
            tid = f"t{len(self._tasks)}"
            self._tasks[tid] = (pr[0], pr[1]) if pr else (1, 1)
            return httpx.Response(200, json={"task_id": tid, "task_status": "pending"})
        if path.startswith("/v1/status/poll/"):
            tid = path.rsplit("/", 1)[1]
            self._polls[tid] = self._polls.get(tid, 0) + 1
            if self.fail == "task":
                return httpx.Response(200, json={"task_id": tid, "task_status": "failure"})
            done = self._polls[tid] > self.pending_polls
            return httpx.Response(200, json={"task_id": tid, "task_status": "success" if done else "started"})
        if path.startswith("/v1/result/"):
            s, e = self._tasks[path.rsplit("/", 1)[1]]
            return httpx.Response(
                200, json={"document": {"json_content": _window_doc(s, e)}, "status": "success", "errors": []}
            )
        return httpx.Response(404)


def _form_values(body: str, name: str) -> list[str]:
    out = []
    for part in body.split("--"):
        marker = f'name="{name}"\r\n\r\n'
        if marker in part:
            out.append(part.split(marker, 1)[1].split("\r\n", 1)[0])
    return out


def _parser(fake: FakeDocling, **kw: Any) -> DoclingServeParser:
    return DoclingServeParser(
        "http://docling", transport=httpx.MockTransport(fake.handler), poll_interval_sec=0, **kw
    )


async def test_docling_windows_and_merge(tmp_path: Path) -> None:
    fake = FakeDocling()
    progress: list[tuple[int, int]] = []

    async def on_progress(done: int, total: int) -> None:
        progress.append((done, total))

    r = await _parser(fake, page_window=2).parse(_pdf(tmp_path, 5), "規程.pdf", "pdf", on_progress)
    assert [q["page_range"] for q in fake.requests] == [[1, 2], [3, 4], [5, 5]]
    assert fake.requests[0]["ocr_lang"] == ["ja", "en"]
    assert r.page_count == 5
    assert sorted(r.doc.pages) == [1, 2, 3, 4, 5]
    assert [t.text for t in r.doc.texts] == ["p1", "p2", "p3", "p4", "p5"]
    assert progress[:3] == [(2, 5), (4, 5), (5, 5)]
    assert r.parser.startswith("docling-serve@")
    # 埋め込み画像は assets へ取り出し、JSON には相対参照だけ残す
    assert r.assets == {"fig-1.png": b"\x89PNG fake"}
    assert str(r.doc.pictures[0].image.uri) == "assets/fig-1.png"  # type: ignore[union-attr]
    json.dumps(r.doc.export_to_dict())


async def test_docling_non_pdf_single_request(tmp_path: Path) -> None:
    fake = FakeDocling()
    p = tmp_path / "a.docx"
    p.write_bytes(b"PK fake")
    await _parser(fake).parse(p, "a.docx", "docx")
    assert len(fake.requests) == 1 and fake.requests[0]["page_range"] == []


async def test_docling_task_failure(tmp_path: Path) -> None:
    with pytest.raises(ParseError) as e:
        await _parser(FakeDocling(fail="task")).parse(_pdf(tmp_path, 1), "a.pdf", "pdf")
    assert e.value.retryable


async def test_docling_timeout(tmp_path: Path) -> None:
    fake = FakeDocling(pending_polls=10_000)
    with pytest.raises(ParseError, match="task t0 timed out"):
        await _parser(fake, timeout_sec=0.05).parse(_pdf(tmp_path, 1), "a.pdf", "pdf")


async def test_docling_connection_error(tmp_path: Path) -> None:
    def boom(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    parser = DoclingServeParser("http://docling", transport=httpx.MockTransport(boom))
    with pytest.raises(ParseError) as e:
        await parser.parse(_pdf(tmp_path, 1), "a.pdf", "pdf")
    assert e.value.user_message == "解析サービスに接続できません"
