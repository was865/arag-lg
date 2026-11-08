from pathlib import Path

import pytest

from arag.eval.variants import load_variants

REPO_VARIANTS = Path(__file__).resolve().parents[3] / "eval" / "variants.yaml"


def test_repo_variants_load_and_inherit() -> None:
    v, models = load_variants(REPO_VARIANTS)
    assert v["dbsf"].fusion == "dbsf" and v["dbsf"].rerank is True  # default を継承
    assert v["rrf_dense2"].weights == (2.0, 1.0)
    # 本番の索引で足りるもの / 別コレクションが要るもの
    assert not v["default"].own_collection and v["default"].collection("chunks") == "chunks"
    assert v["no_context"].collection("chunks") == "eval__no_context"
    assert models["ruri-v3-310m"].query_prefix == "検索クエリ: "


def test_unknown_field_and_model_are_rejected(tmp_path: Path) -> None:
    p = tmp_path / "v.yaml"
    p.write_text("models: {m: {url_env: X, model: m}}\nvariants:\n  a: {mode: hybrid, bogus: 1}\n")
    with pytest.raises(ValueError, match="bogus"):
        load_variants(p)
    p.write_text("models: {m: {url_env: X, model: m}}\nvariants:\n  a: {embed: nope}\n")
    with pytest.raises(ValueError, match="nope"):
        load_variants(p)
