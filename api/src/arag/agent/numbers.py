"""回答の数字の照合（specs/026 R15）。回答に出た数字が、資料・計算結果・質問のどれかにあるかを確かめる。

小さいモデルは、もっともらしい数字を出典番号付きで書くことがある（価格表に無い単価など）。
数字そのものを突き合わせるだけなので、意味の正しさ（どの行の値か）までは見ない。
"""

import re
import unicodedata
from decimal import Decimal, InvalidOperation

_MARK = re.compile(r"\[\d+\]")
_LIST_HEAD = re.compile(r"^\s*\d{1,2}[.)]\s", re.MULTILINE)
_NUM = re.compile(r"(?<![\w.])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
# 1万8,400 / 2.5万 / 3千 / 1億2000万
_UNIT = re.compile(r"(\d[\d,]*(?:\.\d+)?)(億|万|千)(\d[\d,]*)?")
_UNITS = {"億": Decimal(100_000_000), "万": Decimal(10_000), "千": Decimal(1_000)}
_KANJI = re.compile(r"[〇一二三四五六七八九十百千]+")
_DIGIT = {c: i for i, c in enumerate("〇一二三四五六七八九")}


def _canon(token: str) -> str | None:
    try:
        v = Decimal(token.replace(",", ""))
    except InvalidOperation:
        return None
    out = format(v.normalize(), "f")
    return "0" if out in {"-0", ""} else out


def _expand_units(text: str) -> str:
    """「1万8,400」「2.5万」を 18400・25000 と読めるよう、展開した数を後ろに足す。"""

    def repl(m: re.Match[str]) -> str:
        try:
            v = Decimal(m.group(1).replace(",", "")) * _UNITS[m.group(2)]
            if m.group(3):
                v += Decimal(m.group(3).replace(",", ""))
        except InvalidOperation:
            return m.group(0)
        return f"{m.group(0)} {format(v.normalize(), 'f')} "

    return _UNIT.sub(repl, text)


def _kanji_value(s: str) -> int | None:
    """千の位までの漢数字（十四 → 14、二百五十 → 250、三〇 → 30）。"""
    if all(c in _DIGIT for c in s):
        return int("".join(str(_DIGIT[c]) for c in s))
    total, cur = 0, 0
    for c in s:
        if c in _DIGIT:
            cur = _DIGIT[c]
        else:
            total += (cur or 1) * {"十": 10, "百": 100, "千": 1000}[c]
            cur = 0
    return total + cur


def numbers_in(text: str, *, kanji: bool = False) -> set[str]:
    """文章に出る数（正規化した文字列）。kanji=True なら漢数字も数として拾う（照合先用）。"""
    s = _expand_units(unicodedata.normalize("NFKC", text))
    out = {c for m in _NUM.finditer(s) if (c := _canon(m.group(0))) is not None}
    if kanji:
        for m in _KANJI.finditer(s):
            v = _kanji_value(m.group(0))
            if v is not None:
                out.add(str(v))
    return out


def ungrounded(answer: str, sources: list[str]) -> list[str]:
    """回答の数字のうち、照合先のどこにも無いもの（回答に出た順、元の書き方で）。

    引用記号と行頭の箇条書き番号は数えない。1 桁の整数は、個数など文章上の数が多いので数えない。
    """
    known: set[str] = set()
    for src in sources:
        known |= numbers_in(src, kanji=True)
    body = _LIST_HEAD.sub("", _MARK.sub("", unicodedata.normalize("NFKC", answer)))
    expanded = _expand_units(body)
    # 「1万8,400」は展開した数（18400）が照合先にあれば、部分（1・8,400）も確かめられたとみなす
    covered: set[str] = set()
    for m in _UNIT.finditer(body):
        whole = _expand_units(m.group(0)).split()[-1]
        if _canon(whole) in known:
            covered |= {c for t in _NUM.finditer(m.group(0)) if (c := _canon(t.group(0)))}
    missing: list[str] = []
    seen: set[str] = set()
    for m in _NUM.finditer(expanded):
        c = _canon(m.group(0))
        if c is None or c in seen:
            continue
        seen.add(c)
        if re.fullmatch(r"\d", c) or c in known or c in covered:
            continue
        missing.append(m.group(0))
    return missing
