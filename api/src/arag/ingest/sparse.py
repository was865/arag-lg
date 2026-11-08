"""BM25 sparse ベクトル（Sudachi 分かち書き。specs/003-ingestion/design.md §3.4、R22）。

IDF は Qdrant の `modifier: idf` に任せ、ここでは文書側の tf 飽和だけを計算する。
"""

import hashlib
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from sudachipy import Dictionary, SplitMode

SPARSE_VERSION = "sudachi-bm25-v1"

_KANSUJI = "0-9一二三四五六七八九十百千"
# 先に 1 語として抜き出す表現（型番・条項番号）
_PROTECTED = re.compile(
    "|".join(
        [
            r"[A-Za-z0-9]+(?:[-_./][A-Za-z0-9]+)+",
            rf"第[{_KANSUJI}]+(?:条|章|節|項|号)(?:の[{_KANSUJI}]+)?",
        ]
    )
)
_PART_SPLIT = re.compile(r"[-_./]|(?<=[^\d])(?=\d)|(?<=\d)(?=[^\d])")
_DROP_POS = frozenset({"助詞", "助動詞", "補助記号", "空白"})
_MODES = {"A": SplitMode.A, "B": SplitMode.B, "C": SplitMode.C}


@dataclass(frozen=True, slots=True)
class SparseVector:
    indices: list[int]
    values: list[float]


def term_id(term: str) -> int:
    """語 → uint32。辞書を持たないので語彙が増えても再索引が要らない。"""
    return int.from_bytes(hashlib.blake2b(term.encode("utf-8"), digest_size=4).digest(), "big")


class SparseEncoder:
    """Sudachi のトークナイザはスレッド安全でないため、スレッドごとに 1 つ作ること。"""

    def __init__(
        self, mode: Literal["A", "B", "C"] = "B", *, k1: float = 1.2, b: float = 0.75, avgdl: float = 200.0
    ) -> None:
        self._tokenizer = Dictionary(dict="core").tokenizer(mode=_MODES[mode])
        self.k1 = k1
        self.b = b
        self.avgdl = avgdl

    def terms(self, text: str) -> list[str]:
        text = unicodedata.normalize("NFKC", text)
        out: list[str] = []

        def protect(m: re.Match[str]) -> str:
            term = m.group(0)
            out.append(term.casefold())
            # 部分一致用に構成要素も別語として加える（MX-17 → mx, 17）
            parts = [p for p in _PART_SPLIT.split(term) if p and p != term]
            out.extend(p.casefold() for p in parts if not p.startswith("第"))
            return " "

        rest = _PROTECTED.sub(protect, text)
        for m in self._tokenizer.tokenize(rest):
            if m.part_of_speech()[0] in _DROP_POS:
                continue
            norm = m.normalized_form().strip()
            if norm:
                out.append(norm.casefold())
        return out

    def encode_document(self, text: str) -> SparseVector:
        counts = Counter(self.terms(text))
        dl = sum(counts.values())
        weights: dict[int, float] = {}
        norm = self.k1 * (1 - self.b + self.b * dl / self.avgdl)
        for term, tf in counts.items():
            w = tf * (self.k1 + 1) / (tf + norm)
            tid = term_id(term)
            weights[tid] = weights.get(tid, 0.0) + w  # ハッシュ衝突は加算
        return _to_vector(weights)

    def encode_query(self, text: str) -> SparseVector:
        return _to_vector({term_id(t): 1.0 for t in set(self.terms(text))})


def _to_vector(weights: dict[int, float]) -> SparseVector:
    idx = sorted(weights)
    return SparseVector(indices=idx, values=[weights[i] for i in idx])
