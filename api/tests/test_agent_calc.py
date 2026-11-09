"""計算ツール（specs/020 R4）。"""

import pytest

from arag.agent.calc import CalcError, evaluate


@pytest.mark.parametrize(
    ("expr", "want"),
    [
        ("30 + 25 + 80", "135"),
        ("(1200 - 950) / 950 * 100", "26.31578947368421052631578947"),
        ("0.1 + 0.2", "0.3"),
        ("1,200 + 300", "1500"),  # 桁区切りのカンマ
        ("１２０＋３０", "150"),  # 全角
        ("10 × 3 ÷ 4", "7.5"),
        ("-5 + 2", "-3"),
        ("round(2 / 3, 2)", "0.67"),
        ("sum(30, 25, 80) / 3", "45"),
        ("max(240, 120, 80)", "240"),
        ("2 ** 10", "1024"),
        ("17 % 5", "2"),
    ],
)
def test_evaluate(expr: str, want: str) -> None:
    assert evaluate(expr) == want


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os').system('ls')",
        "open('x')",
        "a + 1",
        "[1, 2]",
        "1 / 0",
        "10 ** 1000",
        "x" * 600,
        "",
    ],
)
def test_evaluate_rejects(expr: str) -> None:
    with pytest.raises(CalcError):
        evaluate(expr)


def test_calculate_is_an_agent_tool() -> None:
    from arag.agent.tools import LABELS, TOOLS

    assert "calculate" in {t.name for t in TOOLS}
    assert "calculate" in LABELS
