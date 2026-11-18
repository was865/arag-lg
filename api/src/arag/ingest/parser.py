"""解析器（specs/003-ingestion/design.md §3.1 parsing、R14〜R16・R28）。

- `PlainTextParser`: TXT / JSON / Markdown / CSV を Docling を通さず DoclingDocument にする。
- `DoclingServeParser`: docling-serve の非同期 API。PDF はページ窓ごとに変換して結合する。
"""

import asyncio
import base64
import csv
import io
import json
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.items.table.table_data import TableCell, TableData
from docling_core.types.doc.labels import DocItemLabel

ProgressFn = Callable[[int, int], Awaitable[None]]
"""(処理済みページ数, 総ページ数) を受け取る。"""

PLAIN_EXTS = frozenset({"txt", "json", "md", "markdown", "csv"})


class ParseError(Exception):
    """解析の失敗。user_message は利用者向けの日本語。"""

    def __init__(self, user_message: str, detail: str = "", *, retryable: bool = True) -> None:
        super().__init__(detail or user_message)
        self.user_message = user_message
        self.retryable = retryable


@dataclass(slots=True)
class ParseResult:
    doc: DoclingDocument
    markdown: str
    page_count: int | None
    parser: str
    assets: dict[str, bytes] = field(default_factory=dict)
    meta: dict[str, Any] | None = None
    """docling-serve の応答の記録（status・errors・窓・所要時間・オプション。specs/030 R1）"""


class Parser(Protocol):
    async def parse(self, path: Path, filename: str, ext: str, on_progress: ProgressFn) -> ParseResult: ...


async def _noop_progress(done: int, total: int) -> None:
    return None


# ---------------------------------------------------------------- テキスト系


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp932", "euc-jp"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _plain_doc(name: str, ext: str, text: str) -> DoclingDocument:
    doc = DoclingDocument(name=name)
    if ext == "json":
        try:
            text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            pass
        doc.add_code(text=text)
    elif ext == "csv":
        rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
        if rows:
            width = max(len(r) for r in rows)
            cells = [
                TableCell(
                    text=(r[j] if j < len(r) else ""),
                    start_row_offset_idx=i,
                    end_row_offset_idx=i + 1,
                    start_col_offset_idx=j,
                    end_col_offset_idx=j + 1,
                    column_header=(i == 0),
                )
                for i, r in enumerate(rows)
                for j in range(width)
            ]
            doc.add_table(data=TableData(num_rows=len(rows), num_cols=width, table_cells=cells))
    elif ext in ("md", "markdown"):
        buf: list[str] = []

        def flush() -> None:
            for p in _paragraphs("\n".join(buf)):
                doc.add_text(DocItemLabel.TEXT, p)
            buf.clear()

        in_fence = False
        for line in text.splitlines():
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
            m = None if in_fence else _MD_HEADING.match(line)
            if m:
                flush()
                doc.add_heading(m.group(2), level=len(m.group(1)))
            else:
                buf.append(line)
        flush()
    else:
        for p in _paragraphs(text):
            doc.add_text(DocItemLabel.TEXT, p)
    return doc


class PlainTextParser:
    name = "plain@1"

    async def parse(
        self, path: Path, filename: str, ext: str, on_progress: ProgressFn = _noop_progress
    ) -> ParseResult:
        text = _decode(await asyncio.to_thread(path.read_bytes))
        doc = _plain_doc(Path(filename).stem, ext.lower(), text)
        md = text if ext.lower() in ("md", "markdown") else doc.export_to_markdown()
        await on_progress(1, 1)
        return ParseResult(doc=doc, markdown=md, page_count=None, parser=self.name)


# ---------------------------------------------------------------- docling-serve


def pdf_page_count(path: Path) -> int | None:
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(path)).pages)
    except Exception:
        return None


def page_windows(total: int, window: int) -> list[tuple[int, int]]:
    """1 始まり・両端含むページ窓。"""
    return [(s, min(s + window - 1, total)) for s in range(1, total + 1, window)]


_DATA_URI = re.compile(r"^data:image/(?P<fmt>[a-z+]+);base64,(?P<data>.+)$", re.DOTALL)


def extract_images(doc: DoclingDocument) -> dict[str, bytes]:
    """埋め込み画像（data URI）を取り出して assets/ に置き、JSON には相対参照だけを残す。"""
    assets: dict[str, bytes] = {}
    for n, pic in enumerate(doc.pictures, start=1):
        if pic.image is None:
            continue
        m = _DATA_URI.match(str(pic.image.uri))
        if not m:
            continue
        ext = "jpg" if m.group("fmt") == "jpeg" else m.group("fmt").split("+")[0]
        name = f"fig-{n}.{ext}"
        assets[name] = base64.b64decode(m.group("data"))
        pic.image.uri = f"assets/{name}"  # type: ignore[assignment]
    return assets


class DoclingServeParser:
    def __init__(
        self,
        base_url: str,
        *,
        page_window: int = 20,
        ocr_lang: list[str] | None = None,
        timeout_sec: float = 900.0,
        http_timeout_sec: float = 60.0,
        poll_interval_sec: float = 2.0,
        version: str = "1.38.2",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.page_window = page_window
        self.ocr_lang = list(ocr_lang or [])
        self.timeout_sec = timeout_sec
        self.http_timeout_sec = http_timeout_sec
        self.poll_interval_sec = poll_interval_sec
        self.name = f"docling-serve@{version}"
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url, timeout=self.http_timeout_sec, transport=self._transport
        )

    async def parse(
        self, path: Path, filename: str, ext: str, on_progress: ProgressFn = _noop_progress
    ) -> ParseResult:
        ext = ext.lower()
        total = pdf_page_count(path) if ext == "pdf" else None
        windows = page_windows(total, self.page_window) if total else [None]
        data = await asyncio.to_thread(path.read_bytes)
        docs: list[DoclingDocument] = []
        statuses: list[str] = []
        errors: list[Any] = []
        started = time.monotonic()
        async with self._client() as client:
            for w in windows:
                d, status, errs = await self._convert(client, data, filename, w)
                docs.append(d)
                statuses.append(status)
                errors.extend(errs)
                if total and w:
                    await on_progress(w[1], total)
        doc = docs[0] if len(docs) == 1 else DoclingDocument.concatenate(docs)
        doc.name = Path(filename).stem
        assets = extract_images(doc)
        # Markdown は結合後の文書から作る（窓ごとの md を繋ぐと見出しの扱いがずれるため）
        md = doc.export_to_markdown()
        await on_progress(total or 1, total or 1)
        return ParseResult(
            doc=doc,
            markdown=md,
            page_count=total or (len(doc.pages) or None),
            parser=self.name,
            assets=assets,
            meta={
                "statuses": statuses,
                "errors": errors,
                "windows": len(windows),
                "elapsed_sec": round(time.monotonic() - started, 1),
                "options": {"do_ocr": True, "ocr_lang": self.ocr_lang, "page_window": self.page_window},
            },
        )

    async def _convert(
        self, client: httpx.AsyncClient, data: bytes, filename: str, window: tuple[int, int] | None
    ) -> tuple[DoclingDocument, str, list[Any]]:
        # 同じ名前の項目を繰り返す値はリストで渡す（httpx が multipart で展開する）
        form: dict[str, str | list[str]] = {
            "to_formats": "json",
            "image_export_mode": "embedded",
            "do_ocr": "true",
        }
        # 未指定ならサーバ既定のエンジン・言語に任せる（specs/003-ingestion/design.md §11）
        if self.ocr_lang:
            form["ocr_lang"] = list(self.ocr_lang)
        if window:
            form["page_range"] = [str(window[0]), str(window[1])]
        try:
            res = await client.post("/v1/convert/file/async", data=form, files={"files": (filename, data)})
            res.raise_for_status()
            task_id = res.json()["task_id"]
            deadline = time.monotonic() + self.timeout_sec
            while True:
                status = (await client.get(f"/v1/status/poll/{task_id}")).json()
                state = status.get("task_status")
                if state == "success":
                    break
                if state == "failure":
                    raise ParseError("文書の解析に失敗しました", f"docling-serve task failed: {status}")
                if time.monotonic() > deadline:
                    raise ParseError("文書の解析がタイムアウトしました", f"task {task_id} timed out")
                await asyncio.sleep(self.poll_interval_sec)
            result = (await client.get(f"/v1/result/{task_id}")).json()
        except httpx.HTTPError as e:
            raise ParseError("解析サービスに接続できません", f"{type(e).__name__}: {e}") from e
        if result.get("status") not in ("success", "partial_success"):
            raise ParseError(
                "文書の解析に失敗しました", f"status={result.get('status')} errors={result.get('errors')}"
            )
        content: Any = (result.get("document") or {}).get("json_content")
        if not content:
            raise ParseError("文書の解析結果が空でした", "json_content is empty", retryable=False)
        return (
            DoclingDocument.model_validate(content),
            str(result["status"]),
            list(result.get("errors") or []),
        )


def select_parser(ext: str, plain: PlainTextParser, docling: DoclingServeParser | None) -> Parser:
    if ext.lower() in PLAIN_EXTS:
        return plain
    if docling is None:
        raise ParseError(
            "この形式の解析サービスが設定されていません", "ARAG_DOCLING_URL is empty", retryable=False
        )
    return docling
