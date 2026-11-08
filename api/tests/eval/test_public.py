from arag.eval.public import build_beir, build_jqara, read_qrels


def test_read_qrels_skips_header_and_zero() -> None:
    q = read_qrels("query-id\tcorpus-id\tscore\n1\td1\t1\n1\td2\t0\n2\td3\t2\n")
    assert q == {"1": {"d1"}, "2": {"d3"}}


def test_build_beir_keeps_relevant_and_limits_corpus() -> None:
    corpus = {f"d{i}": {"title": f"T{i}", "text": f"text {i}"} for i in range(10)}
    queries = {"1": {"text": "q one"}, "2": {"text": "q two"}}
    files, cases = build_beir(
        corpus, queries, {"1": {"d7"}, "2": {"d9"}}, {"dataset": "x", "query_limit": 1, "corpus_limit": 3}
    )
    assert len(files) == 3 and "d7.md" in files
    assert files["d7.md"] == "# T7\n\ntext 7\n"
    assert [c["relevant_documents"] for c in cases] == [["d7.md"]]
    assert cases[0]["tags"][0] == "en"


def test_build_jqara_groups_by_question_and_uses_answers() -> None:
    rows = [
        {
            "q_id": "Q1",
            "passage_row_id": "10",
            "label": "1",
            "title": "絶対零度",
            "text": "本文 A",
            "question": "最も低い温度は?",
            "answers": "['絶対零度']",
        },
        {
            "q_id": "Q1",
            "passage_row_id": "11",
            "label": "0",
            "title": "温度",
            "text": "本文 B",
            "question": "最も低い温度は?",
            "answers": "['絶対零度']",
        },
        {
            "q_id": "Q2",
            "passage_row_id": "12",
            "label": "0",
            "title": "x",
            "text": "y",
            "question": "正解なし",
            "answers": "['z']",
        },
    ]
    files, cases = build_jqara(rows, {})
    assert set(files) == {"jqara-10.md", "jqara-11.md", "jqara-12.md"}
    assert len(cases) == 1  # 正解の無い質問は除く
    assert cases[0]["relevant_documents"] == ["jqara-10.md"]
    assert cases[0]["key_facts"] == [{"any": ["絶対零度"]}]
