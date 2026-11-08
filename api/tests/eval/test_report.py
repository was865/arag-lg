from arag.eval.dataset import Thresholds
from arag.eval.report import diff_baseline, gate_failures, to_markdown


def _result():
    return {
        "suite": "t",
        "cases": [
            {
                "id": "c1",
                "n_retrieved": 2,
                "recall_at_5": 1.0,
                "recall_at_k": 1.0,
                "precision_at_k": 0.5,
                "mrr": 1.0,
                "ndcg_at_k": 1.0,
                "fact_coverage": 0.5,
            }
        ],
        "aggregate": {
            "recall_at_5": 1.0,
            "recall_at_k": 1.0,
            "precision_at_k": 0.5,
            "mrr": 1.0,
            "ndcg_at_k": 1.0,
            "fact_coverage": 0.5,
        },
    }


def test_gate_failures_reports_below_threshold():
    th = Thresholds(recall_at_5=0.8, fact_coverage=0.75)
    failures = gate_failures(_result(), th)
    assert len(failures) == 1
    assert "fact_coverage" in failures[0]


def test_gate_failures_empty_when_passing():
    th = Thresholds(recall_at_5=0.8, fact_coverage=0.4)
    assert gate_failures(_result(), th) == []


def test_diff_baseline_computes_deltas():
    baseline = {"aggregate": {"recall_at_5": 0.8, "fact_coverage": 0.6}}
    deltas = diff_baseline(_result(), baseline)
    assert abs(deltas["recall_at_5"] - 0.2) < 1e-9
    assert abs(deltas["fact_coverage"] - (-0.1)) < 1e-9


def test_to_markdown_contains_case_and_aggregate():
    md = to_markdown(_result())
    assert "c1" in md
    assert "recall_at_5" in md


def test_compare_table_lists_variants_and_marks_best():
    from arag.eval.report import compare_table

    a = {**_result(), "variant": "default"}
    b = {**_result(), "variant": "dbsf", "aggregate": {**_result()["aggregate"], "mrr": 0.5}}
    md = compare_table([a, b])
    lines = md.splitlines()
    assert lines[0].startswith("| variant |")
    assert any(ln.startswith("| default |") and "**1.000**" in ln for ln in lines)
    assert any(ln.startswith("| dbsf |") and "0.500" in ln for ln in lines)
