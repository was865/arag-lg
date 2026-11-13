"""回答の数字の照合（specs/026 R15）。回答に出た数字が、資料・計算結果・質問のどれかにあるかを確かめる。

小さいモデルは、もっともらしい数字を出典番号付きで書くことがある（価格表に無い単価など）。
数字そのものを突き合わせるだけなので、意味の正しさ（どの行の値か）までは見ない。
"""

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from itertools import combinations
from typing import Any

_MARK = re.compile(r"\[\d+\]")
_LIST_HEAD = re.compile(r"^\s*\d{1,2}[.)]\s", re.MULTILINE)
# 前が英数字・小数点のときだけ数として拾わない（型番の中の数字）。\w は日本語を含むので使わない
_NUM = re.compile(r"(?<![A-Za-z0-9.])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
# 1万8,400 / 2.5万 / 3千 / 1億2000万
_UNIT = re.compile(r"(\d[\d,]*(?:\.\d+)?)(億|万|千)(\d[\d,]*)?")
_UNITS = {"億": Decimal(100_000_000), "万": Decimal(10_000), "千": Decimal(1_000)}
_KANJI = re.compile(r"[〇一二三四五六七八九十百千]+")
_DIGIT = {c: i for i, c in enumerate("〇一二三四五六七八九")}
# 内訳からの導出（R24）: 材料は回答に出て資料に裏付けのある数字だけ。
# 多すぎると偶然の一致が増えるので救済しない
DERIVE_MAX_MATERIALS = 12
DERIVE_SUM_TERMS = (2, 6)


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


@dataclass(frozen=True, slots=True)
class NumberCheck:
    """数字の照合の結果。missing は未確認の数字（回答に出た順、元の書き方）、
    derived は回答の中の内訳から和・差で確かめた数字（記録に残す）。"""

    missing: list[str] = field(default_factory=list)
    derived: list[dict[str, Any]] = field(default_factory=list)


def _derive(value: str, materials: list[str]) -> dict[str, Any] | None:
    """value が材料の 2〜6 個の和か、2 個の差としてちょうど出せるなら、その導き方。積・割合・平均は見ない。"""
    if len(materials) > DERIVE_MAX_MATERIALS:
        return None
    target = Decimal(value)
    nums = [(m, Decimal(m)) for m in materials]
    lo, hi = DERIVE_SUM_TERMS
    for k in range(lo, min(hi, len(nums)) + 1):
        for combo in combinations(nums, k):
            if sum(v for _, v in combo) == target:
                return {"value": value, "op": "sum", "from": [m for m, _ in combo]}
    for (a, va), (b, vb) in combinations(nums, 2):
        if abs(va - vb) == target:
            big, small = (a, b) if va >= vb else (b, a)
            return {"value": value, "op": "diff", "from": [big, small]}
    return None


def check_numbers(answer: str, sources: list[str]) -> NumberCheck:
    """回答の数字を照合先と突き合わせる。

    引用記号と行頭の箇条書き番号は数えない。1 桁の整数は、個数など文章上の数が多いので数えない。
    照合先に無い数字でも、回答に出て照合先にある数字（1 桁の整数は除く）の和・差でちょうど出せれば
    未確認にせず、derived に記録する（R24。「30・25・80 分で合計 135 分」）。
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
    unknown: list[tuple[str, str]] = []
    materials: list[str] = []
    seen: set[str] = set()
    for m in _NUM.finditer(expanded):
        c = _canon(m.group(0))
        if c is None or c in seen:
            continue
        seen.add(c)
        if re.fullmatch(r"\d", c):
            continue
        if c in known or c in covered:
            materials.append(c)
            continue
        unknown.append((m.group(0), c))
    out = NumberCheck()
    for raw, c in unknown:
        if (d := _derive(c, materials)) is not None:
            out.derived.append(d)
        else:
            out.missing.append(raw)
    return out


def ungrounded(answer: str, sources: list[str]) -> list[str]:
    """回答の数字のうち、照合先にも回答の内訳からの和・差にも無いもの（回答に出た順、元の書き方で）。"""
    return check_numbers(answer, sources).missing
