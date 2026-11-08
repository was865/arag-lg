"""検索の調整値（Settings から作り、評価の variant で上書きする）。"""

from dataclasses import dataclass, replace
from typing import Any, Literal

from arag.settings import Settings

Fusion = Literal["rrf", "dbsf"]
RerankInput = Literal["context+text", "text"]


@dataclass(frozen=True, slots=True)
class SearchConfig:
    fusion: Fusion = "rrf"
    rrf_k: int = 60
    weights: tuple[float, float] = (1.0, 1.0)  # dense, sparse
    rerank_enabled: bool = True
    rerank_input: RerankInput = "context+text"
    rerank_max_chars: int = 0  # rerank 入力の文字数上限（0 は上限なし）

    @classmethod
    def from_settings(cls, s: Settings) -> "SearchConfig":
        w = tuple(float(x) for x in s.search_weights.split(","))
        if len(w) != 2:
            raise ValueError("ARAG_SEARCH_WEIGHTS は「dense,sparse」の 2 値にしてください")
        return cls(
            fusion=s.search_fusion,
            rrf_k=s.search_rrf_k,
            weights=(w[0], w[1]),
            rerank_enabled=s.rerank_enabled,
            rerank_input=s.rerank_input,
            rerank_max_chars=s.rerank_max_chars,
        )

    def with_(self, **kw: Any) -> "SearchConfig":
        return replace(self, **kw)
