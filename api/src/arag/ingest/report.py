"""解析の記録と体検（specs/030-parse-inspection R1・R5〜R7）。

DoclingDocument とチャンクから `ParseReport` を作る純関数。Docling も DB も呼ばない。
"""

import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from docling_core.types.doc.document import DoclingDocument

from arag.storage import Storage

REPORT_VERSION = 1
Severity = Literal["info", "warn"]

IMAGE_ONLY_MAX_CHARS = 20
GARBLED_RATIO = 0.02
GARBLED_MIN = 3
TABLE_SPARSE_MIN_ROWS = 3
TABLE_SPARSE_EMPTY_RATIO = 0.5
BBOX_MARGIN = 0.10


class ChunkLike(Protocol):
    page_start: int | None
    page_end: int | None
    boxes: list[dict[str, Any]]


@dataclass(slots=True)
class Warning_:
    code: str
    severity: Severity
    message: str
    page: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "severity": self.severity, "page": self.page, "message": self.message}


@dataclass(slots=True)
class _Page:
    items: int = 0
    chars: int = 0
    tables: int = 0
    pictures: int = 0
    chunks: int = 0
    garbled: int = 0
    size: tuple[float, float] | None = None

    def as_dict(self, page: int) -> dict[str, Any]:
        return {
            "page": page,
            "items": self.items,
            "chars": self.chars,
            "tables": self.tables,
            "pictures": self.pictures,
            "chunks": self.chunks,
            "size": list(self.size) if self.size else None,
        }


@dataclass(slots=True)
class ParseReport:
    parser: str
    docling: dict[str, Any] | None
    totals: dict[str, int]
    pages: list[dict[str, Any]]
    warnings: list[Warning_] = field(default_factory=list)

    @property
    def warn_count(self) -> int:
        return sum(1 for w in self.warnings if w.severity == "warn")

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": REPORT_VERSION,
            "parser": self.parser,
            "docling": self.docling,
            "totals": self.totals,
            "pages": self.pages,
            "warnings": [w.as_dict() for w in self.warnings],
        }


def _is_garbled_char(ch: str) -> bool:
    return ch == "�" or (ord(ch) < 32 and ch not in "\n\r\t")


def _page_of(item: Any) -> int | None:
    prov = getattr(item, "prov", None)
    return prov[0].page_no if prov else None


def _table_empty_ratio(table: Any) -> tuple[int, float]:
    data = table.data
    rows, cols = data.num_rows, data.num_cols
    if rows <= 0 or cols <= 0:
        return rows, 0.0
    filled = {
        (r, c)
        for cell in data.table_cells
        if cell.text.strip()
        for r in range(cell.start_row_offset_idx, cell.end_row_offset_idx)
        for c in range(cell.start_col_offset_idx, cell.end_col_offset_idx)
    }
    return rows, 1 - len(filled) / (rows * cols)


def _bbox_out(box: dict[str, Any], size: tuple[float, float]) -> bool:
    left, top, right, bottom = (float(v) for v in box["bbox"])
    w, h = size
    mx, my = w * BBOX_MARGIN, h * BBOX_MARGIN
    xs, ys = (left, right), (top, bottom)
    return min(xs) < -mx or max(xs) > w + mx or min(ys) < -my or max(ys) > h + my


def build_report(
    doc: DoclingDocument,
    chunks: Sequence[ChunkLike],
    *,
    parser: str,
    docling: dict[str, Any] | None = None,
    asset_names: Iterable[str] | None = None,
    page_count: int | None = None,
    check_bbox: bool = False,
) -> ParseReport:
    """`asset_names` が None のときは図の参照先を検査しない。`check_bbox` は PDF だけ true にする
    （xlsx の bbox はセル番地で、頁の座標ではない）。"""
    pages: dict[int, _Page] = defaultdict(_Page)
    for no, p in doc.pages.items():
        pages[no].size = (float(p.size.width), float(p.size.height)) if p.size else None
    for no in range(1, (page_count or 0) + 1):
        pages[no]

    warnings: list[Warning_] = []
    unplaced_chars = 0
    for t in doc.texts:
        n = _page_of(t)
        chars = len(t.text)
        if n is None:
            unplaced_chars += chars
            continue
        pg = pages[n]
        pg.items += 1
        pg.chars += chars
        pg.garbled += sum(1 for ch in t.text if _is_garbled_char(ch))
    for tb in doc.tables:
        n = _page_of(tb)
        rows, empty = _table_empty_ratio(tb)
        cell_chars = sum(len(c.text) for c in tb.data.table_cells)
        if n is None:
            unplaced_chars += cell_chars
        else:
            pg = pages[n]
            pg.items += 1
            pg.tables += 1
            pg.chars += cell_chars
            pg.garbled += sum(1 for c in tb.data.table_cells for ch in c.text if _is_garbled_char(ch))
        if rows >= TABLE_SPARSE_MIN_ROWS and empty > TABLE_SPARSE_EMPTY_RATIO:
            warnings.append(
                Warning_(
                    "table_sparse",
                    "warn",
                    f"表の {empty:.0%} が空のセルです（{rows} 行）。表が崩れている可能性があります",
                    n,
                )
            )
    names = set(asset_names) if asset_names is not None else None
    for pic in doc.pictures:
        n = _page_of(pic)
        if n is not None:
            pages[n].items += 1
            pages[n].pictures += 1
        if names is not None and pic.image is not None:
            uri = str(pic.image.uri)
            if uri.startswith("assets/") and uri.removeprefix("assets/") not in names:
                warnings.append(Warning_("missing_asset", "warn", f"図の画像 {uri} が保存されていません", n))

    for ch in chunks:
        if ch.page_start is not None:
            for no in range(ch.page_start, (ch.page_end or ch.page_start) + 1):
                pages[no].chunks += 1
        if check_bbox:
            for box in ch.boxes:
                size = pages[box["page"]].size
                if size and _bbox_out(box, size):
                    warnings.append(
                        Warning_("bbox_out_of_page", "warn", "チャンクの枠が頁の外にあります", box["page"])
                    )
                    break

    total_chars = unplaced_chars + sum(p.chars for p in pages.values())
    if total_chars == 0:
        warnings.append(Warning_("no_text", "warn", "文書から文字を取り出せませんでした"))
    for no in sorted(pages):
        pg = pages[no]
        if pg.items == 0:
            warnings.append(Warning_("empty_page", "info", "文・表・図がありません（空白の頁の可能性）", no))
        elif pg.chars < IMAGE_ONLY_MAX_CHARS and pg.pictures > 0:
            warnings.append(
                Warning_(
                    "image_only_page", "warn", "図があるのに文字がほとんどありません（OCR の失敗の疑い）", no
                )
            )
        if pg.garbled >= GARBLED_MIN and pg.garbled / max(pg.chars, 1) > GARBLED_RATIO:
            warnings.append(Warning_("garbled_text", "warn", "文字化けの疑いがあります", no))
        if pg.chars >= IMAGE_ONLY_MAX_CHARS and pg.chunks == 0 and chunks:
            warnings.append(Warning_("chunk_page_gap", "info", "文があるのにチャンクがありません", no))

    meta = docling or {}
    statuses = meta.get("statuses") or []
    if any(s == "partial_success" for s in statuses):
        warnings.append(
            Warning_("docling_partial", "warn", "docling-serve が一部の成功（partial_success）を返しました")
        )
    if meta.get("errors"):
        warnings.append(
            Warning_("docling_errors", "warn", f"docling-serve がエラーを返しました: {meta['errors']}")
        )

    totals = {
        "pages": len(pages),
        "texts": len(doc.texts),
        "tables": len(doc.tables),
        "pictures": len(doc.pictures),
        "chars": total_chars,
        "chunks": len(chunks),
    }
    return ParseReport(
        parser=parser,
        docling=docling,
        totals=totals,
        pages=[pages[n].as_dict(n) for n in sorted(pages)],
        warnings=warnings,
    )


REPORT_FILE = "parse_report.json"


async def save_report(storage: Storage, prefix: str, report: ParseReport) -> None:
    await storage.put(f"{prefix}/{REPORT_FILE}", json.dumps(report.as_dict(), ensure_ascii=False).encode())


async def load_report_dict(storage: Storage, prefix: str) -> dict[str, Any] | None:
    key = f"{prefix}/{REPORT_FILE}"
    if not await storage.exists(key):
        return None
    data: dict[str, Any] = json.loads(await storage.read(key))
    return data
