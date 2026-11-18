"""解析の記録と体検（specs/030-parse-inspection R1・R5〜R7）。"""

from docling_core.types.doc import DocItemLabel, DoclingDocument, Size

from arag.ingest.chunking import ChunkDraft
from arag.ingest.report import build_report

from .docling_fixtures import prov, regulation_doc, table


def _chunk(page: int, boxes: list[dict] | None = None) -> ChunkDraft:
    return ChunkDraft(0, 0, "text", "", page, page, "x", 1, boxes or [])


def _codes(r: object) -> list[tuple[str, int | None]]:
    return [(w.code, w.page) for w in r.warnings]  # type: ignore[attr-defined]


def _doc(pages: int = 1) -> DoclingDocument:
    d = DoclingDocument(name="t")
    for p in range(1, pages + 1):
        d.add_page(page_no=p, size=Size(width=600, height=800))
    return d


def test_regulation_has_clean_totals() -> None:
    doc = regulation_doc()
    r = build_report(doc, [_chunk(1), _chunk(2), _chunk(3)], parser="p")
    assert r.totals["pages"] == 3 and r.totals["tables"] == 1 and r.totals["chunks"] == 3
    assert r.pages[1]["tables"] == 1
    assert r.warn_count == 0
    assert r.as_dict()["version"] == 1


def test_empty_page_is_info() -> None:
    d = _doc(2)
    d.add_text(DocItemLabel.TEXT, "本文" * 20, prov=prov(1))
    r = build_report(d, [_chunk(1)], parser="p")
    assert ("empty_page", 2) in _codes(r)
    assert r.warn_count == 0


def test_missing_page_in_doc_counts_as_empty() -> None:
    d = _doc(1)
    d.add_text(DocItemLabel.TEXT, "本文" * 20, prov=prov(1))
    r = build_report(d, [_chunk(1)], parser="p", page_count=3)
    assert ("empty_page", 2) in _codes(r) and ("empty_page", 3) in _codes(r)


def test_image_only_page() -> None:
    d = _doc(1)
    d.add_picture(prov=prov(1))
    r = build_report(d, [], parser="p")
    assert ("image_only_page", 1) in _codes(r)
    assert ("no_text", None) in _codes(r)


def test_garbled_text() -> None:
    d = _doc(1)
    d.add_text(DocItemLabel.TEXT, "���正常な文" * 5, prov=prov(1))
    r = build_report(d, [_chunk(1)], parser="p")
    assert ("garbled_text", 1) in _codes(r)


def test_normal_japanese_not_garbled() -> None:
    d = _doc(1)
    d.add_text(DocItemLabel.TEXT, "改行を含む\n普通の文\tです。" * 5, prov=prov(1))
    assert "garbled_text" not in [c for c, _ in _codes(build_report(d, [_chunk(1)], parser="p"))]


def test_table_sparse() -> None:
    d = _doc(1)
    data, pv = table([["a", ""], ["", ""], ["", ""], ["", ""]], 1)
    d.add_table(data=data, prov=pv)
    d.add_text(DocItemLabel.TEXT, "本文" * 20, prov=prov(1))
    r = build_report(d, [_chunk(1)], parser="p")
    assert ("table_sparse", 1) in _codes(r)


def test_missing_asset() -> None:
    d = _doc(1)
    d.add_text(DocItemLabel.TEXT, "本文" * 20, prov=prov(1))
    from docling_core.types.doc.document import ImageRef

    d.add_picture(
        prov=prov(1),
        image=ImageRef(mimetype="image/png", dpi=72, size=Size(width=1, height=1), uri="assets/fig-1.png"),
    )
    assert ("missing_asset", 1) in _codes(build_report(d, [_chunk(1)], parser="p", asset_names=[]))
    assert "missing_asset" not in [
        c for c, _ in _codes(build_report(d, [_chunk(1)], parser="p", asset_names=["fig-1.png"]))
    ]
    # 渡さなければ検査しない
    assert "missing_asset" not in [c for c, _ in _codes(build_report(d, [_chunk(1)], parser="p"))]


def test_bbox_out_of_page_only_when_checked() -> None:
    d = _doc(1)
    d.add_text(DocItemLabel.TEXT, "本文" * 20, prov=prov(1))
    far = {"page": 1, "bbox": [0, 700, 5000, 680], "origin": "BOTTOMLEFT"}
    assert ("bbox_out_of_page", 1) in _codes(build_report(d, [_chunk(1, [far])], parser="p", check_bbox=True))
    assert "bbox_out_of_page" not in [c for c, _ in _codes(build_report(d, [_chunk(1, [far])], parser="p"))]
    ok = {"page": 1, "bbox": [10, 700, 300, 680], "origin": "BOTTOMLEFT"}
    assert "bbox_out_of_page" not in [
        c for c, _ in _codes(build_report(d, [_chunk(1, [ok])], parser="p", check_bbox=True))
    ]


def test_chunk_page_gap() -> None:
    d = _doc(2)
    d.add_text(DocItemLabel.TEXT, "本文" * 20, prov=prov(1))
    d.add_text(DocItemLabel.TEXT, "本文" * 20, prov=prov(2))
    r = build_report(d, [_chunk(1)], parser="p")
    assert ("chunk_page_gap", 2) in _codes(r)


def test_no_text() -> None:
    r = build_report(_doc(1), [], parser="p")
    assert ("no_text", None) in _codes(r)


def test_docling_partial_and_errors() -> None:
    d = _doc(1)
    d.add_text(DocItemLabel.TEXT, "本文" * 20, prov=prov(1))
    meta = {"statuses": ["success", "partial_success"], "errors": [{"message": "boom"}]}
    r = build_report(d, [_chunk(1)], parser="p", docling=meta)
    codes = [c for c, _ in _codes(r)]
    assert "docling_partial" in codes and "docling_errors" in codes
    assert r.warn_count == 2
    assert r.as_dict()["docling"] == meta


def test_unplaced_text_counts_in_totals() -> None:
    d = DoclingDocument(name="plain")
    d.add_text(DocItemLabel.TEXT, "頁の無い本文")
    r = build_report(d, [], parser="plain")
    assert r.totals["chars"] == 6 and "no_text" not in [c for c, _ in _codes(r)]
