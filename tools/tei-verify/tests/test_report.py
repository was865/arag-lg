from tei_verify.metrics import EmbedComparison, RerankComparison
from tei_verify.report import ModelResult, render_markdown


def test_render_markdown_contains_verdicts_and_numbers():
    results = [
        ModelResult(
            preset="bge",
            embed_model="BAAI/bge-m3",
            rerank_model="BAAI/bge-reranker-v2-m3",
            embed=EmbedComparison(
                min_cosine=0.99995, mean_cosine=0.99999, worst_index=3, passed=True, threshold=0.999, count=25
            ),
            rerank_raw=RerankComparison(
                max_abs_diff=0.003,
                rank_mismatch_queries=[],
                passed=True,
                tolerance=1e-2,
                topk_mismatch_queries=[],
                top_k=3,
            ),
            rerank_sigmoid=RerankComparison(
                max_abs_diff=0.0005,
                rank_mismatch_queries=[],
                passed=True,
                tolerance=1e-2,
                topk_mismatch_queries=[],
                top_k=3,
            ),
            info={},
            bench={},
        )
    ]
    md = render_markdown(results)
    assert "BAAI/bge-m3" in md
    assert "0.99995" in md
    assert "合格" in md
