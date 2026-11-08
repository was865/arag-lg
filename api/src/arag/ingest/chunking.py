"""DoclingDocument → 親セクションと子チャンク（specs/003-ingestion/design.md §3.2、R17・R18）。

ORM に依存しない純関数。トークナイザは引数で受け取る（テストは文字数で数える偽物）。
"""

from dataclasses import dataclass, field
from itertools import groupby
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
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.items.table.table import TableItem

CHUNKER_VERSION = "hybrid-md-v2"  # v2: ページをまたぐ表の続きを結合
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
                prev.data.add_row([c.text for c in row])
            prev.prov.extend(item.prov)
            absorbed.append(item)
            continue
        prev = item if isinstance(item, TableItem) else None
    if absorbed:
        out.delete_items(node_items=list(absorbed))
    return out


def _continues(a: TableItem, b: TableItem) -> bool:
    if not a.prov or not b.prov or b.captions:
        return False
    if b.prov[0].page_no != a.prov[-1].page_no + 1 or a.data.num_cols != b.data.num_cols:
        return False
    return not any(c.column_header for c in b.data.table_cells)


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
    if page_unit == "page":
        doc = merge_continued_tables(doc)
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
