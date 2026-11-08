from tei_verify.data import load_corpus
from tei_verify.presets import PRESETS


def test_bundled_corpus_has_expected_size_and_unique_ids():
    corpus = load_corpus()
    assert 15 <= len(corpus.documents) <= 30
    assert len(corpus.queries) == 5
    ids = [d.id for d in corpus.documents]
    assert len(ids) == len(set(ids))


def test_relevant_ids_point_to_existing_documents():
    corpus = load_corpus()
    ids = {d.id for d in corpus.documents}
    for q in corpus.queries:
        assert set(q.relevant) <= ids


def test_ruri_preset_adds_prefixes_and_bge_does_not():
    ruri, bge = PRESETS["ruri"], PRESETS["bge"]
    assert ruri.query_prefix == "検索クエリ: "
    assert ruri.document_prefix == "検索文書: "
    assert bge.query_prefix == "" and bge.document_prefix == ""
    assert ruri.embed_texts(["本文"], kind="document") == ["検索文書: 本文"]
    assert bge.embed_texts(["本文"], kind="query") == ["本文"]
