"""BM25 sparse（specs/003-ingestion D4・R22）。"""

import pytest

from arag.ingest.sparse import SparseEncoder, term_id


@pytest.fixture(scope="module")
def enc() -> SparseEncoder:
    return SparseEncoder("B")


def test_model_numbers_and_clauses_stay_whole(enc: SparseEncoder) -> None:
    terms = enc.terms("ＭＸ－17 型番の機器は第12条の2と第三章に従う。ver1.2.3 も対象")
    assert "mx-17" in terms
    assert "第12条の2" in terms
    assert "第三章" in terms
    assert "ver1.2.3" in terms
    # 部分一致用の構成要素
    assert {"mx", "17"} <= set(terms)


def test_particles_and_symbols_are_dropped(enc: SparseEncoder) -> None:
    terms = enc.terms("情報資産とは、機器を含む。")
    assert "と" not in terms and "は" not in terms and "を" not in terms
    assert "、" not in terms and "。" not in terms
    assert {"情報", "資産", "機器", "含む"} <= set(terms)


def test_normalized_form(enc: SparseEncoder) -> None:
    # 活用形は正規化形へ（使っ → 使う）
    assert "使う" in enc.terms("サーバーを使った")


def test_stable_ids(enc: SparseEncoder) -> None:
    a = enc.encode_document("規程の目的を定める")
    b = enc.encode_document("規程の目的を定める")
    assert a == b
    assert term_id("規程") == term_id("規程")
    assert a.indices == sorted(a.indices)


def test_tf_saturation_value() -> None:
    enc = SparseEncoder("B", k1=1.2, b=0.75, avgdl=4.0)
    # 「規程」×2・「目的」×2 → dl=4 = avgdl のとき w = tf*(k1+1)/(tf+k1) = 2*2.2/3.2
    v = enc.encode_document("規程 規程 目的 目的")
    w = dict(zip(v.indices, v.values, strict=True))
    assert w[term_id("規程")] == pytest.approx(2 * 2.2 / 3.2)
    # tf が増えても k1+1 を超えない
    many = enc.encode_document(" ".join(["規程"] * 100))
    assert max(many.values) < 2.2


def test_query_weights_are_one(enc: SparseEncoder) -> None:
    q = enc.encode_query("規程 規程 目的")
    assert q.values == [1.0, 1.0]


# ---- v2: 英語（specs/004-retrieval R6a）


def test_english_words_stay_latin_and_lowercase(enc: SparseEncoder) -> None:
    terms = enc.terms("Running Kafka consumers RUN fast")
    assert "running" in terms and "kafka" in terms and "consumers" in terms and "run" in terms
    # カタカナに変えない（Sudachi の normalized_form は "Running" → ランニング）
    assert not any(t in terms for t in ("ランニング", "ラン"))
    # 大文字小文字で別の語にならない
    assert enc.terms("RUN") == enc.terms("run") == ["run"]


def test_english_function_words_are_dropped(enc: SparseEncoder) -> None:
    terms = enc.terms("The idempotency keys were changed to the order ID")
    assert "the" not in terms and "were" not in terms and "to" not in terms
    assert "ザ" not in terms and "ワー" not in terms
    assert {"idempotency", "keys", "changed", "order", "id"} <= set(terms)


def test_mixed_japanese_and_english(enc: SparseEncoder) -> None:
    terms = enc.terms("dedupe windowを60秒から180秒へ変更する")
    assert {"dedupe", "window", "変更"} <= set(terms)


def test_english_stemming_is_optional() -> None:
    plain = SparseEncoder("B")
    stem = SparseEncoder("B", en_stem=True)
    assert "consumers" in plain.terms("consumers")
    assert stem.terms("consumers running") == ["consum", "run"]
    # 日本語と型番は変わらない
    assert stem.terms("MX-17 の機器") == plain.terms("MX-17 の機器")
