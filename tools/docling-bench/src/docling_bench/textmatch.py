"""OCR 結果と元テキストの文字一致率（1 − CER）。"""

from __future__ import annotations

import re
import unicodedata

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_TABLE_RULE = re.compile(r"^\s*\|?(\s*:?-{3,}:?\s*\|)+\s*:?-*:?\s*$", re.MULTILINE)
_LIST_MARK = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+", re.MULTILINE)
_MD_SYMBOLS = re.compile(r"[#|*`>]")
_SPACE = re.compile(r"\s+")


def normalize(markdown: str) -> str:
    """Markdown 記号・空白を除き、NFKC で全角英数字と記号の幅を揃える。句読点は残す。"""
    s = _COMMENT.sub("", markdown)
    s = _IMAGE.sub("", s)
    s = _TABLE_RULE.sub("", s)
    s = _LIST_MARK.sub("", s)
    s = unicodedata.normalize("NFKC", s)
    s = _MD_SYMBOLS.sub("", s)
    return _SPACE.sub("", s)


def edit_distance(a: str, b: str) -> int:
    """Levenshtein 距離（2 行 DP）。"""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def char_accuracy(reference: str, hypothesis: str) -> float:
    """1 − CER（文字誤り率）。両者を正規化してから比べ、0 未満は 0 に丸める。"""
    ref, hyp = normalize(reference), normalize(hypothesis)
    if not ref:
        return 1.0 if not hyp else 0.0
    return max(0.0, 1.0 - edit_distance(ref, hyp) / len(ref))
