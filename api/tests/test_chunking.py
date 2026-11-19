"""チャンク化（specs/003-ingestion D3・R17・R18）。"""

from docling_core.types.doc import ContentLayer, DocItemLabel, DoclingDocument, Size

from arag.ingest.chunking import chunk_document, merge_continued_tables, merge_sheet_fragments

from .docling_fixtures import (
    CharTokenizer,
    cross_page_table_doc,
    headingless_doc,
    prov,
    regulation_doc,
    sheet_with_total_row_doc,
)


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


def _letter_doc() -> DoclingDocument:
    """走査した通知文。1 枚目の上部（日付・宛先）を docling がページヘッダとして本文から外す形。"""
    doc = DoclingDocument(name="通知")
    for p in (1, 2):
        doc.add_page(page_no=p, size=Size(width=600, height=800))
    fur = ContentLayer.FURNITURE
    doc.add_text(DocItemLabel.PAGE_HEADER, "2026年10月1日", prov=prov(1), content_layer=fur)
    doc.add_text(DocItemLabel.PAGE_HEADER, "協力会社各位", prov=prov(1), content_layer=fur)
    doc.add_text(DocItemLabel.PAGE_HEADER, "社外秘", prov=prov(1), content_layer=fur)
    doc.add_text(DocItemLabel.PAGE_HEADER, "1 / 2", prov=prov(1), content_layer=fur)
    doc.add_heading("支払条件変更のお知らせ", level=1, prov=prov(1))
    doc.add_text(DocItemLabel.TEXT, "支払サイトを 45 日に短縮します。", prov=prov(1))
    doc.add_text(DocItemLabel.PAGE_HEADER, "社外秘", prov=prov(2), content_layer=fur)
    doc.add_text(DocItemLabel.PAGE_HEADER, "2 / 2", prov=prov(2), content_layer=fur)
    doc.add_text(DocItemLabel.TEXT, "手形での支払いは廃止します。", prov=prov(2))
    return doc


def test_single_page_headers_are_kept_as_text() -> None:
    # 1 か所にしか出ないページヘッダ（日付・宛先）は本文として残す。
    # どのページにも出るもの（社外秘）とページ番号は今までどおり外す
    res = chunk_document(_letter_doc(), CharTokenizer(max_tokens=200))
    body = "\n".join(c.text for c in res.chunks)
    assert "2026年10月1日" in body and "協力会社各位" in body
    assert "社外秘" not in body
    assert "1 / 2" not in body and "2 / 2" not in body
    # 元の順序（見出しより前）を保つ
    assert body.index("協力会社各位") < body.index("支払サイト")


def test_stacked_headings_keep_the_first_as_title() -> None:
    # 同じ深さの見出しが本文を挟まず続くとき（走査した帳票の表題と部署名、PDF の小見出しと表題など）、
    # 後の見出しで前の見出しが消えないよう、後のものを 1 段深くして両方を見出しパスに残す
    doc = DoclingDocument(name="点検票")
    doc.add_page(page_no=1, size=Size(width=600, height=800))
    doc.add_heading("月次点検票（様式 MR-7）", level=1, prov=prov(1))
    doc.add_heading("浜松第二工場 保全課", level=1, prov=prov(1))
    doc.add_text(DocItemLabel.TEXT, "点検者: 小野寺 健", prov=prov(1))
    res = chunk_document(doc, CharTokenizer(max_tokens=200))
    assert [c.heading_path for c in res.chunks] == ["月次点検票（様式 MR-7） > 浜松第二工場 保全課"]
    # 本文を挟んだ後の同じ深さの見出しは、今までどおり前の見出しを置き換える
    doc.add_heading("判定", level=1, prov=prov(1))
    doc.add_text(DocItemLabel.TEXT, "軸受温度は要注意。", prov=prov(1))
    res = chunk_document(doc, CharTokenizer(max_tokens=200))
    assert res.chunks[-1].heading_path == "判定"


def test_sheet_total_row_fragments_join_the_table() -> None:
    """合計行の断片（「合計」と「150」）を、列の位置を保って上の表の最後の行に戻す（harukaze_mix hm22）。"""
    doc = sheet_with_total_row_doc()
    merged = merge_sheet_fragments(doc)
    assert len(doc.tables) == 5  # 元の文書は変えない
    # 注記（値が 1 つだけの行）と別のシートの表はそのまま
    assert [t.data.num_rows for t in merged.tables] == [4, 1, 2]
    rows = [[c.text for c in r] for r in merged.tables[0].data.grid]
    # 結合セルがあっても、元の行は崩れない
    assert rows == [
        ["日付", "設備ID", "停止時間（分）"],
        ["09-02", "PM-04", "30"],
        ["09-05", "PM-04", "120"],
        ["合計", "", "150"],
    ]
    r = chunk_document(doc, CharTokenizer(max_tokens=400), page_unit="sheet")
    t = next(c for c in r.chunks if "PM-04" in c.text and "09-02" in c.text)
    total = next(line for line in t.text.splitlines() if line.startswith("| 合計"))
    assert total.split("|")[3].strip() == "150"  # 停止時間の列に入る


def _handbook_doc() -> DoclingDocument:
    """章の扉の「第 N 章」が本文になり、章は各ページのヘッダ（柱）にだけ出る PDF（学習ハンドブック）。

    p1 目次・p2 第1章の扉（「第 1 章」は見出し）・p3〜4 第1章（柱あり）・p5 第1章のまとめ（柱なし）・
    p6 第2章の扉（「第 2 章」は本文）・p7〜8 第2章（柱あり）。偶数ページの柱は本の題名。
    """
    doc = DoclingDocument(name="ハンドブック")
    for p in range(1, 9):
        doc.add_page(page_no=p, size=Size(width=600, height=800))
    fur = ContentLayer.FURNITURE

    def head(text: str, p: int) -> None:
        doc.add_text(DocItemLabel.PAGE_HEADER, text, prov=prov(p), content_layer=fur)

    doc.add_heading("目 次", level=1, prov=prov(1))
    doc.add_text(DocItemLabel.TEXT, "第1章 設計の基本 / 第2章 本番運用", prov=prov(1))
    doc.add_heading("第 1 章", level=1, prov=prov(2))
    doc.add_heading("設計の 基本", level=1, prov=prov(2))
    doc.add_text(DocItemLabel.TEXT, "この章では設計を学ぶ。", prov=prov(2))
    for p in (3, 4):
        head("第1章 設計の基本" if p % 2 else "学習ハンドブック", p)
        doc.add_heading(f"1.{p - 2} 節 {p}", level=1, prov=prov(p))
        doc.add_text(DocItemLabel.TEXT, f"第1章の本文 {p}。", prov=prov(p))
    head("第1章 設計の基本", 5)
    doc.add_heading("まとめの カード。 2", level=1, prov=prov(5))
    doc.add_text(DocItemLabel.TEXT, "第1章のまとめ。", prov=prov(5))
    doc.add_text(DocItemLabel.TEXT, "第 2 章", prov=prov(6))
    doc.add_heading("本番運用", level=1, prov=prov(6))
    doc.add_text(DocItemLabel.TEXT, "この章では運用を学ぶ。", prov=prov(6))
    for p in (6, 7, 8):
        head("学習ハンドブック", p)
    for p in (7, 8):
        if p % 2:
            head("第2章 本番運用", p)
        doc.add_heading(f"2.{p - 6} 節 {p}", level=1, prov=prov(p))
        doc.add_text(DocItemLabel.TEXT, f"第2章の本文 {p}。", prov=prov(p))
    head("図", 8)  # 図の中の文字を柱と取り違えたもの（1 ページだけ）は使わない
    head("第2章 本番運用", 8)
    head("層", 3)  # 2 ページに出ても、章をまたぐもの（3〜7）は使わない
    head("層", 7)
    return doc


def test_running_headers_become_chapters() -> None:
    """各ページの柱（ページヘッダ）から章を決め、見出しパスの頭に章を置く（specs/031 T19）。"""
    from arag.ingest.chunking import running_chapters

    doc = _handbook_doc()
    # 本の題名（全体にわたる柱）は章にしない。章の始まりは扉（章の名前と同じ見出しのページ）
    assert running_chapters(doc) == [(2, "第1章 設計の基本"), (6, "第2章 本番運用")]
    res = chunk_document(doc, CharTokenizer(max_tokens=200))
    by_text = {c.text: c.heading_path for c in res.chunks}
    assert by_text["第1章の本文 3。"] == "第1章 設計の基本 > 1.1 節 3"
    # 柱の無い章末のまとめも、次の章の扉より前なので第1章。カードの番号（「。 2」）は外す
    # 扉の「第 2 章」（本文になったもの）は前の節の本文に混ぜない
    assert by_text["第1章のまとめ。"] == "第1章 設計の基本 > まとめの カード。"
    # 扉の「第 2 章」「本番運用」は章と重なるので重ねない
    assert by_text["この章では運用を学ぶ。"] == "第2章 本番運用"
    assert by_text["第2章の本文 7。"] == "第2章 本番運用 > 2.1 節 7"
    # 章より前（目次）はそのまま
    assert any(h == "目 次" for h in by_text.values())
    heads = [s.heading_path for s in res.sections]
    assert "第2章 本番運用 > 2.2 節 8" in heads


def test_no_chapters_without_running_headers() -> None:
    from arag.ingest.chunking import running_chapters

    assert running_chapters(regulation_doc()) == []
    assert running_chapters(_letter_doc()) == []
