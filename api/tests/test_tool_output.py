"""ツールの結果の構造（specs/037 R5〜R7）。"""

from arag.agent.ops import (
    OUTLINE_HEAD,
    OUTLINE_MAX,
    OUTLINE_OMITTED,
    OUTLINE_TAIL,
    format_outline,
    outline_omits,
)
from arag.agent.tool_output import ToolOutput


def test_artifact_round_trip() -> None:
    out = ToolOutput("本文", materials=3, weak=True, omitted=True, fallback="codes", rows=(8, 2))
    art = out.artifact()
    assert "text" not in art and art["rows"] == [8, 2]
    assert ToolOutput.from_artifact("本文", art) == out


def test_missing_or_broken_artifact_means_plain_text() -> None:
    # 037 より前の checkpoint・社内システムの結果には構造が無い
    assert ToolOutput.from_artifact("文", None) == ToolOutput("文")
    assert ToolOutput.from_artifact("文", {"rows": [1], "fallback": "x"}) == ToolOutput("文")


def test_prefixed_keeps_structure() -> None:
    out = ToolOutput("資料", materials=2).prefixed("注意: x")
    assert out.text == "注意: x\n\n資料" and out.materials == 2


class _Sec:
    def __init__(self, i: int) -> None:
        self.id, self.level, self.page_start, self.token_len = f"id{i}", 1, i, 10
        self.heading_path = f"節 {i}"


def test_outline_omits_matches_format_outline() -> None:
    """構造の「省略あり」は、章立ての文に中略の案内を入れるときと一致する。"""
    for total in (3, OUTLINE_HEAD + OUTLINE_TAIL, OUTLINE_HEAD + OUTLINE_TAIL + 1, 643):
        secs = [_Sec(i) for i in range(1, total + 1)]
        for start in (None, 1, 121, max(1, total - OUTLINE_MAX + 1), total):
            text = format_outline("a.pdf", secs, start)
            assert outline_omits(total, start) == (OUTLINE_OMITTED in text), (total, start)
