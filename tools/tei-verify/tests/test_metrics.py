import math

import numpy as np
import pytest

from tei_verify.metrics import (
    compare_embeddings,
    compare_rerank,
    sigmoid,
)


def test_compare_embeddings_identical_vectors_have_cosine_one():
    a = np.array([[1.0, 0.0], [0.6, 0.8]])
    result = compare_embeddings(a, a.copy(), threshold=0.999)
    assert result.min_cosine == pytest.approx(1.0)
    assert result.passed


def test_compare_embeddings_fails_below_threshold_and_reports_worst_index():
    tei = np.array([[1.0, 0.0], [1.0, 0.0]])
    ref = np.array([[1.0, 0.0], [0.0, 1.0]])
    result = compare_embeddings(tei, ref, threshold=0.999)
    assert not result.passed
    assert result.min_cosine == pytest.approx(0.0)
    assert result.worst_index == 1


def test_compare_embeddings_does_not_assume_normalized_input():
    tei = np.array([[2.0, 0.0]])
    ref = np.array([[5.0, 0.0]])
    assert compare_embeddings(tei, ref, threshold=0.999).min_cosine == pytest.approx(1.0)


def test_compare_embeddings_rejects_shape_mismatch():
    with pytest.raises(ValueError):
        compare_embeddings(np.zeros((2, 3)), np.zeros((2, 4)), threshold=0.999)


def test_sigmoid_matches_definition():
    assert sigmoid(np.array([0.0]))[0] == pytest.approx(0.5)
    assert sigmoid(np.array([2.0]))[0] == pytest.approx(1 / (1 + math.exp(-2.0)))


def test_compare_rerank_passes_when_diff_small_and_order_same():
    tei = {"q1": [3.0, 1.0, -2.0]}
    ref = {"q1": [3.004, 0.998, -2.001]}
    result = compare_rerank(tei, ref, tolerance=1e-2)
    assert result.passed
    assert result.max_abs_diff == pytest.approx(0.004)
    assert result.rank_mismatch_queries == []


def test_compare_rerank_fails_on_rank_swap_even_if_diff_small():
    tei = {"q1": [1.000, 1.004]}
    ref = {"q1": [1.004, 1.000]}
    result = compare_rerank(tei, ref, tolerance=1e-2)
    assert result.max_abs_diff <= 1e-2
    assert result.rank_mismatch_queries == ["q1"]
    assert not result.passed


def test_compare_rerank_fails_on_large_diff():
    result = compare_rerank({"q1": [0.0, 1.0]}, {"q1": [0.0, 1.5]}, tolerance=1e-2)
    assert not result.passed
    assert result.max_abs_diff == pytest.approx(0.5)


def test_compare_rerank_rejects_missing_query():
    with pytest.raises(ValueError):
        compare_rerank({"q1": [0.0]}, {"q2": [0.0]}, tolerance=1e-2)


def test_compare_rerank_reports_topk_mismatch_separately_from_full_order():
    # 4 位と 5 位だけが入れ替わる → 全順位は不一致、上位 3 件は一致
    tei = {"q1": [5.0, 4.0, 3.0, -11.0, -11.001]}
    ref = {"q1": [5.0, 4.0, 3.0, -11.001, -11.0]}
    result = compare_rerank(tei, ref, tolerance=1e-2, top_k=3)
    assert result.rank_mismatch_queries == ["q1"]
    assert result.topk_mismatch_queries == []
    assert result.top_k == 3


def test_compare_rerank_topk_detects_swap_inside_top_k():
    result = compare_rerank({"q1": [2.0, 1.0, 0.0]}, {"q1": [1.0, 2.0, 0.0]}, tolerance=10.0, top_k=3)
    assert result.topk_mismatch_queries == ["q1"]
