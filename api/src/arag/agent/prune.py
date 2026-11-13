"""引用の刈り込み（specs/026 T31・R31）。

小さいモデルは 1 つの文に [1][2][3] と重ね、同じ検索に出ただけの資料まで引用にする
（プロンプトでは直らなかった）。文の「値」（数字・英数字の型番）を、引用した各資料の本文で探し、
少なくとも 1 つの引用が値を含むとき、値を 1 つも含まない引用の番号をその文から外す。
値の無い文・引用が 1 つの文・どの引用も値を含まない文は触らない。
"""

import re
import unicodedata
from collections.abc import Callable
from typing import Any

from arag.agent.numbers import numbers_in

# 文の終わり: 句点・感嘆符・疑問符（直後の引用記号まで同じ文）と改行。表の行・箇条書きは 1 行が 1 文
_END = re.compile(r"[。．！？!?]+(?:[ \t]*\[\d+\](?!\())*|\n")
_MARK = re.compile(r"\[(\d+)\](?!\()")
# 英数字の型番（英字と数字の両方を含む 3 字以上の連なり。P-1042・KG-5・HP-300）
_CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]*[A-Za-z0-9]")
_ONE_DIGIT = re.compile(r"\d")
_GAP = re.compile(r"(\])[ \t]+(?=[。．！？!?]|\n|$)")


def _spans(text: str) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    start = 0
    for m in _END.finditer(text):
        out.append((start, m.end()))
        start = m.end()
    if start < len(text):
        out.append((start, len(text)))
    return out


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def _codes(text: str) -> set[str]:
    return {
        w
        for w in _CODE.findall(_norm(text))
        if len(w) >= 3 and any(c.isdigit() for c in w) and any(c.isalpha() for c in w)
    }


def _values(sentence: str) -> tuple[set[str], set[str]]:
    """文の値: 数字（1 桁の整数は除く）と英数字の型番。"""
    body = _MARK.sub("", sentence)
    return {v for v in numbers_in(body) if not _ONE_DIGIT.fullmatch(v)}, _codes(body)


def _holds(material: str, nums: set[str], codes: set[str]) -> bool:
    """資料の本文に、文の値のどれか 1 つでも在るか（数字は正規化した数で、型番は NFKC の部分文字列で）。"""
    if nums & numbers_in(material, kanji=True):
        return True
    norm = _norm(material)
    return any(c in norm for c in codes)


def _dropper(drop: set[int]) -> Callable[[re.Match[str]], str]:
    def sub(m: re.Match[str]) -> str:
        return "" if int(m.group(1)) in drop else m.group(0)

    return sub


def prune_citations(text: str, materials: dict[int, str]) -> tuple[str, list[dict[str, Any]]]:
    """値を書いていない資料の番号を、その文から外す。戻り値は直した本文と、外した文ごとの記録。"""
    out: list[str] = []
    pruned: list[dict[str, Any]] = []
    for start, end in _spans(text):
        sentence = text[start:end]
        cited = list(dict.fromkeys(int(n) for n in _MARK.findall(sentence)))
        nums, codes = _values(sentence) if len(cited) >= 2 else (set(), set())
        if not nums and not codes:
            out.append(sentence)
            continue
        holds = {n: _holds(materials.get(n, ""), nums, codes) for n in cited}
        removed = [n for n in cited if not holds[n]]
        if not removed or len(removed) == len(cited):
            out.append(sentence)
            continue
        fixed = _MARK.sub(_dropper(set(removed)), sentence)
        # 外した記号の跡に残った、句点の前の空白を詰める（「です [1]。」の空白は残す）
        fixed = _GAP.sub(r"\1", fixed)
        out.append(fixed)
        pruned.append(
            {
                "sentence": sentence.strip()[:40],
                "removed": removed,
                "kept": [n for n in cited if holds[n]],
                "values": sorted(nums | codes),
            }
        )
    return "".join(out), pruned
