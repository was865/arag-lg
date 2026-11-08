"""題集を検索関数で実行して指標を出す（specs/004-retrieval R20）。"""

import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol

from arag.eval.dataset import Case, GoldenSuite
from arag.eval.metrics import fact_coverage, mrr, ndcg_at_k, normalize_text, precision_at_k, recall_at_k


class Hit(Protocol):
    document_name: str
    text: str
    section_text: str | None


SearchFn = Callable[[Case], Awaitable[Sequence[Hit]]]
METRICS = ["recall_at_5", "recall_at_k", "precision_at_k", "mrr", "ndcg_at_k"]


def ranked_documents(hits: Sequence[Hit]) -> list[str]:
    """チャンク列を文書の順位列にたたむ（初出の順位を保つ）。"""
    seen: set[str] = set()
    out: list[str] = []
    for h in hits:
        if h.document_name not in seen:
            seen.add(h.document_name)
            out.append(h.document_name)
    return out


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    i = min(len(s) - 1, max(0, round(q * (len(s) - 1))))
    return s[i]


async def run_suite(suite: GoldenSuite, search_fn: SearchFn) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    latencies: list[float] = []
    for case in suite.cases:
        t0 = time.perf_counter()
        hits = list(await search_fn(case))
        latencies.append((time.perf_counter() - t0) * 1000)
        ranked = ranked_documents(hits)
        relevant = set(case.relevant_documents)
        # 結果本文 + 親セクション本文（旧版の前後 1 塊の展開に相当）
        corpus = normalize_text("\n".join(f"{h.text}\n{h.section_text or ''}" for h in hits))
        facts = [kf.any for kf in case.key_facts]
        cases.append(
            {
                "id": case.id,
                "tags": case.tags,
                "n_retrieved": len(hits),
                "recall_at_5": recall_at_k(ranked, relevant, 5),
                "recall_at_k": recall_at_k(ranked, relevant, case.top_k),
                "precision_at_k": precision_at_k(ranked, relevant, case.top_k),
                "mrr": mrr(ranked, relevant),
                "ndcg_at_k": ndcg_at_k(ranked, relevant, case.top_k),
                "fact_coverage": fact_coverage(corpus, facts) if facts else None,
                "ranked": ranked[: case.top_k],
                "ms": round(latencies[-1], 1),
            }
        )
    aggregate: dict[str, float] = {k: _mean([c[k] for c in cases]) for k in METRICS}
    fc = [c["fact_coverage"] for c in cases if c["fact_coverage"] is not None]
    if fc:
        aggregate["fact_coverage"] = _mean(fc)
    # 初回は接続確立などで遅いので p50/p95 から除く（E3）
    warm = latencies[1:] if len(latencies) > 1 else latencies
    aggregate["p50_ms"] = _percentile(warm, 0.5)
    aggregate["p95_ms"] = _percentile(warm, 0.95)
    return {"suite": suite.suite, "cases": cases, "aggregate": aggregate}
