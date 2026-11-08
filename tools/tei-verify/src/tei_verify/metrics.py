"""一致判定の計算（純粋関数。テスト対象）。"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from numpy.typing import NDArray

Array = NDArray[np.float64]


@dataclass(frozen=True)
class EmbedComparison:
    min_cosine: float
    mean_cosine: float
    worst_index: int
    passed: bool
    threshold: float
    count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RerankComparison:
    max_abs_diff: float
    rank_mismatch_queries: list[str]
    passed: bool
    tolerance: float
    # 参考指標（合否には使わない）: 上位 top_k 件の並びが一致しないクエリ
    topk_mismatch_queries: list[str]
    top_k: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def sigmoid(x: Array) -> Array:
    return 1.0 / (1.0 + np.exp(-x))


def compare_embeddings(tei: Array, ref: Array, *, threshold: float) -> EmbedComparison:
    """行ごとの cosine 類似度。入力が正規化済みかどうかに依存しない。"""
    tei = np.asarray(tei, dtype=np.float64)
    ref = np.asarray(ref, dtype=np.float64)
    if tei.shape != ref.shape:
        raise ValueError(f"shape が一致しない: tei={tei.shape} ref={ref.shape}")
    cos = np.sum(tei * ref, axis=1) / (np.linalg.norm(tei, axis=1) * np.linalg.norm(ref, axis=1))
    worst = int(np.argmin(cos))
    return EmbedComparison(
        min_cosine=float(cos[worst]),
        mean_cosine=float(cos.mean()),
        worst_index=worst,
        passed=bool(np.all(cos >= threshold)),
        threshold=threshold,
        count=int(cos.size),
    )


def compare_rerank(
    tei: dict[str, list[float]], ref: dict[str, list[float]], *, tolerance: float, top_k: int = 3
) -> RerankComparison:
    """クエリごとのスコア（文書順）を比べる。合格 = 絶対差が許容内 かつ 降順の順位が完全一致。"""
    if tei.keys() != ref.keys():
        raise ValueError(f"クエリ集合が一致しない: {sorted(tei)} vs {sorted(ref)}")
    max_diff = 0.0
    mismatched: list[str] = []
    topk_mismatched: list[str] = []
    for qid in tei:
        t = np.asarray(tei[qid], dtype=np.float64)
        r = np.asarray(ref[qid], dtype=np.float64)
        max_diff = max(max_diff, float(np.max(np.abs(t - r))))
        # stable ソートで同点時の並びを固定する
        order_t, order_r = np.argsort(-t, kind="stable"), np.argsort(-r, kind="stable")
        if not np.array_equal(order_t, order_r):
            mismatched.append(qid)
        if not np.array_equal(order_t[:top_k], order_r[:top_k]):
            topk_mismatched.append(qid)
    return RerankComparison(
        max_abs_diff=max_diff,
        rank_mismatch_queries=mismatched,
        passed=max_diff <= tolerance and not mismatched,
        tolerance=tolerance,
        topk_mismatch_queries=topk_mismatched,
        top_k=top_k,
    )
