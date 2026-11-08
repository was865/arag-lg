"""結果の JSON / Markdown 出力。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tei_verify.metrics import EmbedComparison, RerankComparison


@dataclass(frozen=True)
class ModelResult:
    preset: str
    embed_model: str
    rerank_model: str
    embed: EmbedComparison
    rerank_raw: RerankComparison
    rerank_sigmoid: RerankComparison
    info: dict[str, Any]
    bench: dict[str, Any]

    @property
    def passed(self) -> bool:
        return self.embed.passed and self.rerank_raw.passed and self.rerank_sigmoid.passed

    def to_dict(self) -> dict[str, Any]:
        return {
            "preset": self.preset,
            "embed_model": self.embed_model,
            "rerank_model": self.rerank_model,
            "passed": self.passed,
            "embed": self.embed.to_dict(),
            "rerank_raw": self.rerank_raw.to_dict(),
            "rerank_sigmoid": self.rerank_sigmoid.to_dict(),
            "info": self.info,
            "bench": self.bench,
        }


def _verdict(ok: bool) -> str:
    return "合格" if ok else "**不合格**"


def render_markdown(results: list[ModelResult]) -> str:
    lines = [
        "| 系列 | 判定 | embedding（モデル） | 最小 cosine | 平均 cosine | rerank（モデル） "
        "| 最大差 raw | 最大差 sigmoid | 順位不一致（全件） | 上位 3 件の不一致（参考） |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        topk = sorted(set(r.rerank_raw.topk_mismatch_queries) | set(r.rerank_sigmoid.topk_mismatch_queries))
        mismatch = sorted(
            set(r.rerank_raw.rank_mismatch_queries) | set(r.rerank_sigmoid.rank_mismatch_queries)
        )
        lines.append(
            f"| {r.preset} | {_verdict(r.passed)} | {r.embed_model} {_verdict(r.embed.passed)} "
            f"| {r.embed.min_cosine:.5f} | {r.embed.mean_cosine:.5f} "
            f"| {r.rerank_model} {_verdict(r.rerank_raw.passed and r.rerank_sigmoid.passed)} "
            f"| {r.rerank_raw.max_abs_diff:.2e} | {r.rerank_sigmoid.max_abs_diff:.2e} "
            f"| {', '.join(mismatch) or 'なし'} | {', '.join(topk) or 'なし'} |"
        )
    bench_rows = [r for r in results if r.bench]
    if bench_rows:
        lines += [
            "",
            "| 系列 | 処理 | 入力 | 平均 token | 文書/秒 | p50 ms/バッチ | GPU メモリ（全体, MiB） |",
            "|---|---|---|---|---|---|---|",
        ]
        for r in bench_rows:
            for kind in ("embed", "rerank"):
                b = r.bench.get(kind)
                if not b:
                    continue
                lines.append(
                    f"| {r.preset} | {kind} | {b['batch']} 件 × {b['rounds']} 回 | {b['avg_tokens']:.0f} "
                    f"| {b['docs_per_sec']:.1f} | {b['p50_ms']:.0f} "
                    f"| {b.get('gpu_mem_before_mib', '—')} → 最大 {b.get('gpu_mem_peak_mib', '—')} |"
                )
    return "\n".join(lines) + "\n"
