import pytest

from docling_bench.textmatch import char_accuracy, edit_distance, normalize


def test_normalize_removes_markdown_and_whitespace_and_unifies_width():
    md = "## 第１２条（持出し）\n\n| 項目 | 値 |\n|---|---|\n| 電圧 | AC100V |\n<!-- image -->\n"
    assert normalize(md) == "第12条(持出し)項目値電圧AC100V"


def test_normalize_keeps_japanese_punctuation():
    assert normalize("承認を得る。ただし、") == "承認を得る。ただし、"


def test_edit_distance_basic():
    assert edit_distance("abc", "abc") == 0
    assert edit_distance("abc", "abd") == 1
    assert edit_distance("", "abc") == 3
    assert edit_distance("規程第12条", "規定第12条") == 1


def test_char_accuracy_is_one_minus_cer_and_clamped():
    assert char_accuracy("ABCD", "ABCD") == pytest.approx(1.0)
    assert char_accuracy("ABCD", "ABCE") == pytest.approx(0.75)
    # 余計な文字が大量にあっても 0 未満にはしない
    assert char_accuracy("AB", "ABXXXXXXXX") == pytest.approx(0.0)


def test_char_accuracy_normalizes_both_sides():
    assert char_accuracy("# 見出し\n本文", "見出し 本文") == pytest.approx(1.0)
