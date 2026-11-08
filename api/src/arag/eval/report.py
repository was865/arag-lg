"""レポート・ゲート・基準値との差分・variant 比較表（specs/004-retrieval R20・R21・R24）。"""

from typing import Any

from arag.eval.dataset import Thresholds

QUALITY = ["recall_at_5", "recall_at_k", "precision_at_k", "mrr", "ndcg_at_k", "fact_coverage"]
LATENCY = ["p50_ms", "p95_ms"]


def gate_failures(result: dict[str, Any], thresholds: Thresholds) -> list[str]:
    agg = result["aggregate"]
    failures: list[str] = []
    for key, minimum in thresholds.model_dump().items():
        if minimum is None or key not in agg:
            continue
        if agg[key] < minimum:
            failures.append(f"{key}: {agg[key]:.3f} < 閾値 {minimum:.3f}")
    return failures


def diff_baseline(result: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    cur = result["aggregate"]
    base = baseline.get("aggregate", {})
    return {k: cur[k] - base[k] for k in cur if k in base}


def to_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# 評価レポート: {result['suite']}" + (f"（{result['variant']}）" if result.get("variant") else ""),
        "",
        "## ケース別",
        "",
        "| id | recall@5 | recall@k | prec@k | mrr | ndcg@k | facts | n |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for c in result["cases"]:
        fc = c["fact_coverage"]
        fc_str = f"{fc:.2f}" if fc is not None else "—"
        lines.append(
            f"| {c['id']} | {c['recall_at_5']:.2f} | {c['recall_at_k']:.2f} | "
            f"{c['precision_at_k']:.2f} | {c['mrr']:.2f} | {c['ndcg_at_k']:.2f} | "
            f"{fc_str} | {c['n_retrieved']} |"
        )
    lines += ["", "## 集計（平均）", ""]
    for k, v in result["aggregate"].items():
        lines.append(f"- {k}: {v:.3f}")
    return "\n".join(lines)


def compare_table(results: list[dict[str, Any]]) -> str:
    """variant ごとの集計を 1 表に。品質指標は列ごとの最良値を太字にする。"""
    keys = [k for k in QUALITY + LATENCY if any(k in r["aggregate"] for r in results)]
    best = {k: max(r["aggregate"][k] for r in results if k in r["aggregate"]) for k in keys if k in QUALITY}
    lines = [
        "| variant | " + " | ".join(keys) + " |",
        "| --- | " + " | ".join("---" for _ in keys) + " |",
    ]
    for r in results:
        cells = []
        for k in keys:
            v = r["aggregate"].get(k)
            if v is None:
                cells.append("—")
            elif k in LATENCY:
                cells.append(f"{v:.0f}")
            else:
                s = f"{v:.3f}"
                cells.append(f"**{s}**" if abs(v - best[k]) < 1e-9 else s)
        lines.append(f"| {r.get('variant', '?')} | " + " | ".join(cells) + " |")
    return "\n".join(lines)
