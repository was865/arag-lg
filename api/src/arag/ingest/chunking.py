"""DoclingDocument → 親セクションと子チャンク（specs/003-ingestion/design.md §3.2、R17・R18）。

ORM に依存しない純関数。トークナイザは引数で受け取る（テストは文字数で数える偽物）。
"""

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import groupby, pairwise
from typing import Any, Literal

from docling_core.transforms.chunker.base import BaseChunk
from docling_core.transforms.chunker.doc_chunk import DocChunk
from docling_core.transforms.chunker.hierarchical_chunker import (
    ChunkingDocSerializer,
    ChunkingSerializerProvider,
)
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from docling_core.transforms.serializer.base import BaseDocSerializer
from docling_core.transforms.serializer.markdown import MarkdownTableSerializer
from docling_core.types.doc.common.content_layer import ContentLayer
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.items.table.table import TableItem
from docling_core.types.doc.items.table.table_data import TableCell
from docling_core.types.doc.items.text import SectionHeaderItem, TextItem
from docling_core.types.doc.labels import DocItemLabel

# v2: ページをまたぐ表の続きを結合
# v3: 1 か所にしか出ないページヘッダを本文に戻す・続けて並ぶ同じ深さの見出しを 1 段ずつ入れ子にする
# v4: Excel の合計行など、表の下で 1 セルずつに分かれた断片を表の行に戻す
CHUNKER_VERSION = "hybrid-md-v4"
HEADING_SEP = " > "

BlockType = Literal["text", "table", "figure", "code", "formula", "list"]
# 見出しが無いとき、ページ（スライド・シート）単位でセクションを切る形式
PageUnit = Literal["slide", "sheet", "page"]


@dataclass(slots=True)
class ChunkDraft:
    ordinal: int
    section_ordinal: int
    block_type: BlockType
    heading_path: str
    page_start: int | None
    page_end: int | None
    text: str
    token_len: int
    boxes: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class SectionDraft:
    ordinal: int
    heading_path: str
    level: int
    page_start: int | None
    page_end: int | None
    text: str
    token_len: int


@dataclass(slots=True)
class ChunkingResult:
    sections: list[SectionDraft]
    chunks: list[ChunkDraft]


class _MarkdownTableProvider(ChunkingSerializerProvider):
    """表は Markdown で出す（分割時にヘッダ行を繰り返す。既定の triplet より読みやすい）。"""

    def get_serializer(self, doc: DoclingDocument) -> BaseDocSerializer:
        return ChunkingDocSerializer(doc=doc, table_serializer=MarkdownTableSerializer())


def _block_type(labels: list[str]) -> BlockType:
    s = set(labels)
    if "table" in s:
        return "table"
    if "code" in s:
        return "code"
    if "formula" in s:
        return "formula"
    if s and s <= {"list_item"}:
        return "list"
    return "text"


def _boxes(chunk: DocChunk) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in chunk.meta.doc_items:
        for p in item.prov:
            out.append(
                {
                    "page": p.page_no,
                    "bbox": [p.bbox.l, p.bbox.t, p.bbox.r, p.bbox.b],
                    "origin": p.bbox.coord_origin.value,
                }
            )
    return out


@dataclass(slots=True)
class _Piece:
    key: tuple[str, ...]
    chunk: ChunkDraft


def merge_continued_tables(doc: DoclingDocument) -> DoclingDocument:
    """ページをまたぐ表の続きを前の表へ結合した複製を返す（元の文書は変えない）。

    docling は改ページで表を 2 つに分け、続きの表はヘッダ行を持たない（先頭のデータ行が
    ヘッダ扱いになり列の意味が失われる）。次の条件をすべて満たす表を続きとみなす:
    本文順で直前の要素が表・次のページから始まる・列数が同じ・列ヘッダもキャプションも無い。
    """
    out = doc.model_copy(deep=True)
    prev: TableItem | None = None
    absorbed: list[TableItem] = []
    for item, _ in out.iterate_items():
        if getattr(item, "label", None) == "caption":
            continue  # キャプションは表の直後に並ぶので隣接判定から外す
        if isinstance(item, TableItem) and prev is not None and _continues(prev, item):
            for row in item.data.grid:
                _append_row(prev, [c.text for c in row])
            prev.prov.extend(item.prov)
            absorbed.append(item)
            continue
        prev = item if isinstance(item, TableItem) else None
    if absorbed:
        out.delete_items(node_items=list(absorbed))
    return out


def _append_row(table: TableItem, texts: list[str]) -> None:
    """表の最後に 1 行足す。

    TableData.add_row は table_cells が「1 セル 1 要素の行優先の並び」だと仮定して行番号を振り直すため、
    結合セル（1 つの TableCell が複数行にまたがる）がある表では行が崩れる。ここでは既存のセルに触れない。
    """
    data = table.data
    r = data.num_rows
    data.table_cells.extend(
        TableCell(
            text=t,
            start_row_offset_idx=r,
            end_row_offset_idx=r + 1,
            start_col_offset_idx=j,
            end_col_offset_idx=j + 1,
        )
        for j, t in enumerate(texts)
    )
    data.num_rows = r + 1


def _continues(a: TableItem, b: TableItem) -> bool:
    if not a.prov or not b.prov or b.captions:
        return False
    if b.prov[0].page_no != a.prov[-1].page_no + 1 or a.data.num_cols != b.data.num_cols:
        return False
    return not any(c.column_header for c in b.data.table_cells)


def merge_sheet_fragments(doc: DoclingDocument) -> DoclingDocument:
    """Excel のシートで、表の下に分かれた断片を表の行に戻した複製を返す（元の文書は変えない）。

    docling は空のセルを挟んだ行（「合計 | | | | 600」など）を、値のあるセルごとの小さな表に分ける。
    すると値が列から離れ、「合計」と「600」だけが並ぶ。表の bbox はセル番地（l/r が列、t/b が行）なので、
    同じシートで、表の下 1 行以内（空行 1 つまで）に始まり、列が表の範囲に収まる、表より列の少ない表を
    1 行だけの表を断片とみなし、行・列の位置を保って表の行として足す。
    値が 1 つだけの行（表の下の注記など）は足さない。
    """
    out = doc.model_copy(deep=True)
    absorbed: list[TableItem] = []
    by_page: dict[int, list[TableItem]] = defaultdict(list)
    for t in out.tables:
        if len(t.prov) == 1:
            by_page[t.prov[0].page_no].append(t)
    for tables in by_page.values():
        tables.sort(key=lambda t: (t.prov[0].bbox.t, t.prov[0].bbox.l))
        for host in tables:
            if host in absorbed:
                continue
            hb = host.prov[0].bbox
            l0, r0, bottom = int(hb.l), int(hb.r), int(hb.b)
            rows: dict[int, list[str]] = {}
            parts: dict[int, list[TableItem]] = defaultdict(list)
            for frag in tables:
                fb = frag.prov[0].bbox
                last = max([bottom - 1, *rows])
                if (
                    frag is host
                    or frag in absorbed
                    or frag.captions
                    or frag.data.num_rows != 1  # 複数行の表は別の表として残す
                    or frag.data.num_cols >= host.data.num_cols
                    or not (bottom <= fb.t <= last + 2)  # 空行 1 つまで
                    or fb.l < l0
                    or fb.r > r0
                ):
                    continue
                row = rows.setdefault(int(fb.t), [""] * host.data.num_cols)
                for j, cell in enumerate(frag.data.grid[0]):
                    row[int(fb.l) - l0 + j] = cell.text
                parts[int(fb.t)].append(frag)
            for r, row in sorted(rows.items()):
                # 値が 1 つだけの行（表の下の注記など）は入れない。「合計」と値のように 2 つ以上の行だけ戻す
                if sum(1 for v in row if v) < 2:
                    continue
                _append_row(host, row)
                absorbed.extend(parts[r])
    if absorbed:
        out.delete_items(node_items=list(absorbed))
    return out


# ページ番号だけのヘッダ（「1 / 2」「- 3 -」「Page 4」「5 ページ」など）
_PAGE_NO = re.compile(
    r"^[\s\-–—]*(?:p\.?|page|ページ)?\s*\d+\s*(?:(?:/|of)\s*\d+)?\s*(?:ページ|頁)?[\s\-–—]*$", re.I
)


def _norm(text: str) -> str:
    """繰り返しの判定用。数字（ページ番号など）と空白を除いて比べる。"""
    return re.sub(r"[\d\s]+", "", unicodedata.normalize("NFKC", text)).lower()


def keep_unique_page_headers(doc: DoclingDocument) -> DoclingDocument:
    """1 か所にしか出ないページヘッダを本文に戻した複製を返す（元の文書は変えない）。

    docling は 1 枚目の上部（日付・宛先・差出人）をページヘッダとして本文から外すことがある。
    本当のヘッダ（社名・文書番号など）は各ページに繰り返し出るので、数字を除いて同じ文が
    2 ページ以上に出るものとページ番号だけのものは今までどおり外す。
    """
    heads = [
        item
        for item, _ in doc.iterate_items(included_content_layers={ContentLayer.FURNITURE})
        if isinstance(item, TextItem) and item.label == DocItemLabel.PAGE_HEADER and item.text.strip()
    ]
    if not heads:
        return doc
    pages: dict[str, set[int]] = defaultdict(set)
    for h in heads:
        pages[_norm(h.text)].update(p.page_no for p in h.prov)
    keep = {h.self_ref for h in heads if len(pages[_norm(h.text)]) <= 1 and not _PAGE_NO.match(h.text)}
    if not keep:
        return doc
    out = doc.model_copy(deep=True)
    for item, _ in out.iterate_items(included_content_layers={ContentLayer.FURNITURE}):
        if isinstance(item, TextItem) and item.self_ref in keep:
            item.label = DocItemLabel.TEXT
            item.content_layer = ContentLayer.BODY
    return out


def nest_stacked_headings(doc: DoclingDocument) -> DoclingDocument:
    """同じ深さの見出しが本文を挟まずに続くとき、後の見出しを 1 段深くした複製を返す。

    PDF の見出しは docling がすべて同じ深さにするため、表題の上の小見出しと表題、
    帳票の表題と部署名などが続くと、後の見出しが前の見出しを置き換えて消してしまう。
    1 段ずつ深くして、どちらも見出しパスに残す（例: 「月次点検票 > 保全課」）。
    """
    items = [item for item, _ in doc.iterate_items()]
    if not any(
        isinstance(a, SectionHeaderItem) and isinstance(b, SectionHeaderItem) and a.level == b.level
        for a, b in pairwise(items)
    ):
        return doc
    out = doc.model_copy(deep=True)
    prev: SectionHeaderItem | None = None
    prev_orig = 0
    for item, _ in out.iterate_items():
        if not isinstance(item, SectionHeaderItem):
            prev = None
            continue
        orig = item.level
        if prev is not None and orig == prev_orig:
            item.level = min(prev.level + 1, 100)
        prev, prev_orig = item, orig
    return out


def chunk_document(
    doc: DoclingDocument,
    tokenizer: BaseTokenizer,
    *,
    section_max_tokens: int = 2000,
    section_level: int = 2,
    page_unit: PageUnit = "page",
) -> ChunkingResult:
    """子チャンクの上限は tokenizer.get_max_tokens()。"""
    chunker = HybridChunker(
        tokenizer=tokenizer,
        merge_peers=True,
        repeat_table_header=True,
        serializer_provider=_MarkdownTableProvider(),
    )
    pieces: list[_Piece] = []
    doc = nest_stacked_headings(keep_unique_page_headers(doc))
    if page_unit == "page":
        doc = merge_continued_tables(doc)
    elif page_unit == "sheet":
        doc = merge_sheet_fragments(doc)
    # スライド・シートは 1 枚ずつ分けて切る（merge_peers が枚をまたいで結合しないように）
    docs = (
        [doc.filter(page_nrs={p}) for p in sorted(doc.pages)] if page_unit != "page" and doc.pages else [doc]
    )
    raw: BaseChunk
    for raw in (r for d in docs for r in chunker.chunk(d)):
        dc = DocChunk.model_validate(raw)
        text = dc.text.strip()
        if not text:
            continue
        headings = [h.strip() for h in (dc.meta.headings or []) if h.strip()]
        boxes = _boxes(dc)
        pages = sorted({b["page"] for b in boxes})
        draft = ChunkDraft(
            ordinal=len(pieces),
            section_ordinal=-1,
            block_type=_block_type([i.label.value for i in dc.meta.doc_items]),
            heading_path=HEADING_SEP.join(headings),
            page_start=pages[0] if pages else None,
            page_end=pages[-1] if pages else None,
            text=text,
            token_len=tokenizer.count_tokens(text),
            boxes=boxes,
        )
        key = tuple(headings[:section_level])
        if not key and page_unit != "page" and draft.page_start is not None:
            # スライド・シートは 1 枚を 1 セクションに
            key = (f"{'スライド' if page_unit == 'slide' else 'シート'} {draft.page_start}",)
        pieces.append(_Piece(key=key, chunk=draft))

    sections: list[SectionDraft] = []
    for key, group in groupby(pieces, key=lambda p: p.key):
        parts = _split_by_budget([p.chunk for p in group], section_max_tokens)
        for i, part in enumerate(parts, start=1):
            heading = HEADING_SEP.join(key)
            if len(parts) > 1 and key:
                heading = f"{heading}（{i}/{len(parts)}）"
            text = "\n\n".join(c.text for c in part)
            pages = [p for c in part for p in (c.page_start, c.page_end) if p is not None]
            sec = SectionDraft(
                ordinal=len(sections),
                heading_path=heading,
                level=len(key),
                page_start=min(pages) if pages else None,
                page_end=max(pages) if pages else None,
                text=text,
                token_len=tokenizer.count_tokens(text),
            )
            for c in part:
                c.section_ordinal = sec.ordinal
            sections.append(sec)
    return ChunkingResult(sections=sections, chunks=[p.chunk for p in pieces])


def _split_by_budget(chunks: list[ChunkDraft], budget: int) -> list[list[ChunkDraft]]:
    """子チャンク境界でまとめ、合計が budget を超える手前で切る。"""
    parts: list[list[ChunkDraft]] = []
    cur: list[ChunkDraft] = []
    total = 0
    for c in chunks:
        if cur and total + c.token_len > budget:
            parts.append(cur)
            cur, total = [], 0
        cur.append(c)
        total += c.token_len
    if cur:
        parts.append(cur)
    return parts


_PAGE_UNITS: dict[str, PageUnit] = {
    "pptx": "slide",
    "ppt": "slide",
    "odp": "slide",
    "xlsx": "sheet",
    "xls": "sheet",
    "ods": "sheet",
}


def page_unit_for(ext: str) -> PageUnit:
    return _PAGE_UNITS.get(ext.lower(), "page")


def load_tokenizer(model_name: str, max_tokens: int) -> BaseTokenizer:
    """埋め込みモデルのトークナイザ（tokenizer ファイルのみ取得。重みは読まない）。"""
    from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer

    return HuggingFaceTokenizer.from_pretrained(model_name=model_name, max_tokens=max_tokens)
