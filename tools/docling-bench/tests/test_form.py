from docling_bench.client import build_form


def test_build_form_repeats_list_values_as_separate_fields():
    form = build_form({"to_formats": ["json", "md"], "do_ocr": True, "page_range": [1, 20]})
    assert ("to_formats", "json") in form and ("to_formats", "md") in form
    assert ("do_ocr", "true") in form
    assert [v for k, v in form if k == "page_range"] == ["1", "20"]


def test_build_form_skips_none():
    assert build_form({"ocr_engine": None, "do_ocr": False}) == [("do_ocr", "false")]


def test_page_windows_split_like_the_app():
    from docling_bench.cli import page_windows

    assert page_windows(70, 20) == [(1, 20), (21, 40), (41, 60), (61, 70)]
    assert page_windows(4, 20) == [(1, 4)]
    assert page_windows(20, 20) == [(1, 20)]
