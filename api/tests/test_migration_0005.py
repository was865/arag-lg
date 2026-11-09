"""0005: 保存済みの回答の引用番号を「回答に出た順」に振り直す（データの移行）。"""

import importlib.util
from pathlib import Path
from typing import Any

_PATH = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0005_renumber_citations.py"
_spec = importlib.util.spec_from_file_location("m0005", _PATH)
assert _spec and _spec.loader
m0005: Any = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m0005)


def sec(sid: str, n: int) -> dict[str, Any]:
    return {"id": sid, "n": n, "heading": f"見出し{sid}", "body": "本文", "block_type": "text", "page": 1}


CMAP = {
    "1": {"source_id": "d1", "section_id": "a"},
    "2": {"source_id": "d2", "section_id": "b"},
    "3": {"source_id": "d1", "section_id": "c"},
}
SOURCES = [
    {"id": "d1", "title": "規程.pdf", "score": 0.9, "sections": [sec("a", 1), sec("c", 3)]},
    {"id": "d2", "title": "手順書.pdf", "score": 0.5, "sections": [sec("b", 2)]},
]


def test_renumbers_by_first_appearance_and_keeps_only_cited() -> None:
    answer, cmap, sources, mapping = m0005.renumber("停止[3]。点検は[2][3][3]。", CMAP, SOURCES)
    assert answer == "停止[1]。点検は[2][1]。"
    assert cmap == {"1": CMAP["3"], "2": CMAP["2"]}
    assert mapping == {3: 1, 2: 2}
    assert [s["id"] for s in sources] == ["d1", "d2"]
    assert [(x["id"], x["n"]) for x in sources[0]["sections"]] == [("c", 1)]
    assert sources[0]["title"] == "規程.pdf" and sources[0]["score"] == 0.9


def test_uncited_answer_has_no_sources() -> None:
    answer, cmap, sources, mapping = m0005.renumber("見つかりませんでした。", CMAP, SOURCES)
    assert (answer, cmap, sources, mapping) == ("見つかりませんでした。", {}, [], {})


def test_idempotent() -> None:
    once = m0005.renumber("A[3]B[1]", CMAP, SOURCES)
    twice = m0005.renumber(once[0], once[1], once[2])
    assert twice[:3] == once[:3]
    assert twice[3] == {1: 1, 2: 2}
