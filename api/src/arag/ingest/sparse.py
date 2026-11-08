"""BM25 sparse ベクトル（Sudachi 分かち書き。specs/003-ingestion/design.md §3.4、R22）。

英字の語は Sudachi の normalized_form を使わない（"Running" → ランニング のようにカタカナ化される）。
表層を小文字化し、英語の機能語を除く（specs/004-retrieval/design.md §4）。

IDF は Qdrant の `modifier: idf` に任せ、ここでは文書側の tf 飽和だけを計算する。
"""

import hashlib
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from sudachipy import Dictionary, SplitMode

SPARSE_VERSION = "sudachi-bm25-v2"  # v2: 英字語は表層の小文字・英語の機能語を除く

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
_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9'\-]*")
# 英語の機能語（冠詞・前置詞・代名詞・be/have/do・接続詞など）。内容語は残す
EN_STOPWORDS = frozenset(
    """a about above after again against all am an and any are as at be because been before being
    below between both but by can could did do does doing down during each few for from further had
    has have having he her here hers herself him himself his how i if in into is it its itself just
    me more most my myself no nor not of off on once only or other our ours ourselves out over own
    same she should so some such than that the their theirs them themselves then there these they
    this those through to too under until up very was we were what when where which while who whom
    why will with would you your yours yourself yourselves""".split()
)
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
        self,
        mode: Literal["A", "B", "C"] = "B",
        *,
        k1: float = 1.2,
        b: float = 0.75,
        avgdl: float = 200.0,
        en_stem: bool = False,
    ) -> None:
        self._tokenizer = Dictionary(dict="core").tokenizer(mode=_MODES[mode])
        self._stemmer = None
        if en_stem:
            import snowballstemmer

            self._stemmer = snowballstemmer.stemmer("english")
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
            surface = m.surface().strip()
            if _LATIN_WORD.fullmatch(surface):
                word = surface.casefold()
                if word not in EN_STOPWORDS:
                    out.append(self._stemmer.stemWord(word) if self._stemmer else word)
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
