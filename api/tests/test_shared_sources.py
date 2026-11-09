"""共有ページの出典（同じ文書の別の箇所を見分けられるよう、見出しとページを添える）。"""

from arag.agent.router import shared_sources

SOURCES = [
    {
        "id": "d1",
        "title": "規程.pdf",
        "sections": [
            {"id": "s1", "n": 1, "heading": "第3条", "page": 4, "body": "本文"},
            {"id": "s2", "n": 2, "heading": "  ", "page": 9, "body": "本文"},
        ],
    },
    {"id": "d2", "title": "台帳.md", "sections": [{"id": "s3", "n": 3, "body": "本文"}]},
]


def test_same_document_cited_twice_is_distinguishable() -> None:
    cmap = {
        "2": {"source_id": "d1", "section_id": "s2"},
        "1": {"source_id": "d1", "section_id": "s1"},
        "3": {"source_id": "d2", "section_id": "s3"},
        "4": {"source_id": "gone", "section_id": "x"},
        "note": "x",
    }
    out = [x.model_dump() for x in shared_sources(cmap, SOURCES)]
    assert out == [
        {"n": 1, "title": "規程.pdf", "heading": "第3条", "page": 4},
        {"n": 2, "title": "規程.pdf", "heading": None, "page": 9},
        {"n": 3, "title": "台帳.md", "heading": None, "page": None},
    ]
