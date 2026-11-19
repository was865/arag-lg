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
        {"n": 1, "title": "規程.pdf", "heading": "第3条", "page": 4, "restricted": False},
        {"n": 2, "title": "規程.pdf", "heading": None, "page": 9, "restricted": False},
        {"n": 3, "title": "台帳.md", "heading": None, "page": None, "restricted": False},
    ]


def test_system_sources_show_name_and_time_but_never_rows() -> None:
    # 社内システムの出典（specs/032 R22）: 文書の権限では伏せず、名前と見出し（取得の時点）だけ
    sources = [
        *SOURCES,
        {
            "id": "sys-erp",
            "title": "ERP（資材・購買）",
            "kind": "system",
            "sections": [
                {
                    "id": "r1",
                    "n": 5,
                    "heading": "在庫（get_stock part=SK-300）・ERP の現在の値（2026-11-18 10:32 取得）",
                    "body": "| 15 |",
                    "record": {"rows": [["P-1042", 15]]},
                }
            ],
        },
    ]
    cmap = {"1": {"source_id": "d1", "section_id": "s1"}, "5": {"source_id": "sys-erp", "section_id": "r1"}}
    out = [x.model_dump() for x in shared_sources(cmap, sources, readable=set())]
    assert out[0]["restricted"] is True
    assert out[1]["title"] == "ERP（資材・購買）" and "2026-11-18 10:32 取得" in out[1]["heading"]
    assert "15" not in str(out[1]["heading"]).replace("2026-11-18", "") and "P-1042" not in str(out)
