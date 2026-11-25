"""層と依存の向き（specs/037 R1〜R4）。import を走査して、禁止の組が無いことを確かめる。"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"

AGENT = SRC / "arag" / "agent"
# 規則の層（R3・R14）: agent/domain の全部。枠組み・DB・HTTP を import しない
PURE = sorted(f"arag.agent.domain.{p.stem}" for p in (AGENT / "domain").glob("*.py") if p.stem != "__init__")
FRAMEWORKS = ("langchain", "langchain_core", "langgraph", "sqlalchemy", "fastapi", "redis", "qdrant_client")

# 処理の層（R11・R14）: DB を直接読まず、口（DocumentStore・SearchFn）を通す。つなぎの層を import しない
APPLICATION = [
    "arag.agent.context",
    "arag.agent.documents",
    "arag.agent.flow",
    "arag.agent.middleware",
    "arag.agent.ops",
    "arag.agent.primer",
    "arag.agent.tools",
]

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


def _is_type_checking(node: ast.stmt) -> bool:
    return isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING"


def imports(module: str) -> set[str]:
    """モジュールの最上位の import（`if TYPE_CHECKING:` の中と、関数の中の遅い import は数えない）。"""
    tree = ast.parse(_path(module).read_text(encoding="utf-8"))
    out: set[str] = set()
    stack: list[ast.AST] = [n for n in tree.body if not _is_type_checking(n)]
    while stack:
        node = stack.pop()
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.add(node.module)
        stack.extend(ast.iter_child_nodes(node))
    return out


def _agent_modules() -> list[str]:
    return sorted(
        "arag." + ".".join(p.relative_to(SRC / "arag").with_suffix("").parts)
        for p in AGENT.rglob("*.py")
        if p.stem != "__init__"
    )


@pytest.mark.parametrize("module", PURE)
def test_rules_do_not_import_frameworks(module: str) -> None:
    bad = sorted(m for m in imports(module) if m.split(".")[0] in FRAMEWORKS)
    assert not bad, f"{module} は規則の層なので {bad} を import しない"


@pytest.mark.parametrize("module", PURE)
def test_rules_depend_only_on_rules(module: str) -> None:
    bad = sorted(
        m
        for m in imports(module)
        if m.startswith("arag.") and not m.startswith("arag.agent.domain") and m != "arag.search.schemas"
    )
    assert not bad, f"{module} は規則の層と検索の型だけに依存する: {bad}"


# 実行文脈は sessionmaker の型を持つ（ツールの引数の型を pydantic が実行時に解くので、型の import が要る）
HOLDS_SESSION_TYPE = {"arag.agent.context"}


@pytest.mark.parametrize("module", APPLICATION)
def test_application_does_not_query_the_database(module: str) -> None:
    bad = sorted(
        m
        for m in imports(module)
        if (m.split(".")[0] == "sqlalchemy" and module not in HOLDS_SESSION_TYPE)
        or m.startswith("arag.agent.adapters")
    )
    assert not bad, f"{module} は DB を直接読まず、つなぎの層に依存しない（口を通す）: {bad}"


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
