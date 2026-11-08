from docling_bench.client import build_form


def test_build_form_repeats_list_values_as_separate_fields():
    form = build_form({"to_formats": ["json", "md"], "do_ocr": True, "page_range": [1, 20]})
    assert ("to_formats", "json") in form and ("to_formats", "md") in form
    assert ("do_ocr", "true") in form
    assert [v for k, v in form if k == "page_range"] == ["1", "20"]


def test_build_form_skips_none():
    assert build_form({"ocr_engine": None, "do_ocr": False}) == [("do_ocr", "false")]
