"""チャンク化（specs/003-ingestion D3・R17・R18）。"""

from arag.ingest.chunking import chunk_document, merge_continued_tables

from .docling_fixtures import CharTokenizer, cross_page_table_doc, headingless_doc, regulation_doc


def test_sections_follow_heading_level_2() -> None:
    res = chunk_document(regulation_doc(), CharTokenizer(max_tokens=200), section_level=2)
    heads = [s.heading_path for s in res.sections]
    assert heads == ["第1章 総則 > 第1条 目的", "第1章 総則 > 第2条 定義", "第2章 管理"]
    assert [s.level for s in res.sections] == [2, 2, 1]
    # 各子チャンクは所属セクションを持ち、見出しパスが記録される
    assert all(c.section_ordinal >= 0 for c in res.chunks)
    assert res.chunks[0].heading_path == "第1章 総則 > 第1条 目的"
    assert res.sections[1].page_start == 2


def test_chunk_limit_and_table_header_repeated() -> None:
    res = chunk_document(regulation_doc(), CharTokenizer(max_tokens=60))
    assert all(c.token_len <= 60 for c in res.chunks)
    tables = [c for c in res.chunks if c.block_type == "table"]
    assert len(tables) >= 2
    # 分割された表の各片に表ヘッダが入る
    assert all("| 区分" in c.text and "保管期間" in c.text for c in tables)


def test_block_types_and_boxes() -> None:
    res = chunk_document(regulation_doc(), CharTokenizer(max_tokens=200))
    types = {c.block_type for c in res.chunks}
    assert {"text", "table", "list"} <= types
    first = res.chunks[0]
    assert first.boxes and first.boxes[0]["page"] == 1
    assert len(first.boxes[0]["bbox"]) == 4
    assert first.page_start == 1 and first.page_end == 1


def test_section_split_when_over_budget() -> None:
    res = chunk_document(regulation_doc(), CharTokenizer(max_tokens=60), section_max_tokens=80)
    split = [s.heading_path for s in res.sections if "第2条" in s.heading_path]
    assert len(split) >= 2
    assert split[0].endswith(f"（1/{len(split)}）")
    assert all(s.token_len <= 80 + 60 for s in res.sections)


def test_headingless_document_packs_pages() -> None:
    res = chunk_document(headingless_doc(4), CharTokenizer(max_tokens=60), section_max_tokens=100)
    assert len(res.sections) >= 2
    assert all(s.heading_path == "" and s.level == 0 for s in res.sections)
    assert res.sections[0].page_start == 1


def test_slides_become_one_section_each() -> None:
    res = chunk_document(headingless_doc(3), CharTokenizer(max_tokens=200), page_unit="slide")
    assert [s.heading_path for s in res.sections] == ["スライド 1", "スライド 2", "スライド 3"]


def test_ordinals_are_sequential() -> None:
    res = chunk_document(regulation_doc(), CharTokenizer(max_tokens=60))
    assert [c.ordinal for c in res.chunks] == list(range(len(res.chunks)))
    assert [s.ordinal for s in res.sections] == list(range(len(res.sections)))


def test_cross_page_table_continuation_is_merged() -> None:
    doc = cross_page_table_doc()
    merged = merge_continued_tables(doc)
    assert len(doc.tables) == 2  # 元の文書は変えない
    assert len(merged.tables) == 1
    t = merged.tables[0]
    assert [row[0].text for row in t.data.grid] == ["設備ID", "MX-11", "MX-14", "MX-17", "MX-21"]
    assert [p.page_no for p in t.prov] == [1, 2]
    r = chunk_document(doc, CharTokenizer(max_tokens=400))
    tables = [c for c in r.chunks if c.block_type == "table"]
    assert len(tables) == 1
    assert tables[0].text.splitlines()[0].startswith("| 設備ID")
    assert "MX-21" in tables[0].text
    assert (tables[0].page_start, tables[0].page_end) == (1, 2)


def test_cross_page_split_repeats_header() -> None:
    r = chunk_document(cross_page_table_doc(), CharTokenizer(max_tokens=90))
    tables = [c for c in r.chunks if c.block_type == "table"]
    assert len(tables) > 1
    assert all(c.text.startswith("| 設備ID") for c in tables)
    assert any("MX-21" in c.text for c in tables)


def test_tables_not_merged_when_shape_or_caption_differs() -> None:
    assert len(merge_continued_tables(cross_page_table_doc(cols_b=2)).tables) == 2
    assert len(merge_continued_tables(cross_page_table_doc(caption_b=True)).tables) == 2


def test_real_docling_output_cross_page_table() -> None:
    """評価 PDF 04 を docling-serve v1.38.2 で変換した実出力（tests/fixtures）。"""
    from pathlib import Path

    from docling_core.types.doc.document import DoclingDocument

    path = Path(__file__).parent / "fixtures" / "04-cross-page-table.docling.json"
    doc = DoclingDocument.load_from_json(path)
    assert len(doc.tables) == 2  # docling は改ページで表を分ける
    r = chunk_document(doc, CharTokenizer(max_tokens=2000))
    tables = [c for c in r.chunks if c.block_type == "table"]
    assert len(tables) == 1
    lines = [ln for ln in tables[0].text.splitlines() if ln.startswith("|")]
    assert lines[0].split("|")[1].strip() == "設備ID"
    assert [ln.split("|")[1].strip() for ln in lines[2:]] == ["MX-11", "MX-14", "MX-17", "MX-21", "MX-25"]
    headings = [s.heading_path for s in r.sections][1:]
    assert headings == ["月次設備点検台帳", "1. 判定ルール", "2. 点検表 A", "最終判断の補足"]
