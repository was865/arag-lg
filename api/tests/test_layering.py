"""層と依存の向き（specs/037 R1〜R4）。import を走査して、禁止の組が無いことを確かめる。"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"

# 規則の層（R3）: 枠組み・DB・HTTP を import しない
PURE = [
    "arag.agent.answer_text",
    "arag.agent.calc",
    "arag.agent.citations",
    "arag.agent.numbers",
    "arag.agent.prune",
    "arag.agent.review_rules",
    "arag.agent.table",
    "arag.agent.tool_output",
]
FRAMEWORKS = ("langchain", "langchain_core", "langgraph", "sqlalchemy", "fastapi", "redis", "qdrant_client")

# 社内システムの中核（R1）と検索（R2）はエージェントに依存しない
NO_AGENT = [
    "arag.mcp.client",
    "arag.mcp.registry",
    "arag.mcp.service",
    "arag.mcp.live",
    "arag.search.config",
    "arag.search.hooks",
    "arag.search.query",
    "arag.search.rerank",
    "arag.search.schemas",
    "arag.search.scope",
    "arag.search.service",
]

# エージェントが検索の実装に依存しない（R2）。使ってよいのは型・範囲・計測の口
AGENT_SEARCH_ALLOWED = {"arag.search.schemas", "arag.search.scope", "arag.search.hooks"}
# 組み立ての入口（実装を選んで渡す側）は除く
COMPOSITION_ROOTS = {"arag.agent.runner"}


def _path(module: str) -> Path:
    return SRC / (module.replace(".", "/") + ".py")


def imports(module: str) -> set[str]:
    tree = ast.parse(_path(module).read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.add(node.module)
    return out


def _agent_modules() -> list[str]:
    return sorted(
        f"arag.agent.{p.stem}" for p in (SRC / "arag" / "agent").glob("*.py") if p.stem != "__init__"
    )


@pytest.mark.parametrize("module", PURE)
def test_rules_do_not_import_frameworks(module: str) -> None:
    bad = sorted(m for m in imports(module) if m.split(".")[0] in FRAMEWORKS)
    assert not bad, f"{module} は規則の層なので {bad} を import しない"


@pytest.mark.parametrize("module", NO_AGENT)
def test_core_does_not_import_agent(module: str) -> None:
    bad = sorted(m for m in imports(module) if m == "arag.agent" or m.startswith("arag.agent."))
    assert not bad, f"{module} は arag.agent に依存しない: {bad}"


@pytest.mark.parametrize("module", [m for m in _agent_modules() if m not in COMPOSITION_ROOTS])
def test_agent_uses_search_ports_only(module: str) -> None:
    bad = sorted(
        m
        for m in imports(module)
        if (m == "arag.search" or m.startswith("arag.search.")) and m not in AGENT_SEARCH_ALLOWED
    )
    assert not bad, f"{module} は検索の実装でなく型・範囲・計測の口だけを使う: {bad}"
