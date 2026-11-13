"""回答の流れの図を、グラフの定義から作る（specs/029 R5）。

`make graph`（= `uv run python -m arag.agent.diagram`）で次の 2 つを書き出す。手で直さない。
- `docs/agent-graph.md`: Mermaid の図と、節点ごとの 1 行の説明
- `web/src/lib/chat/flow-graph.json`: 画面の「流れ」の表示が読む、節点の並びと辺

モデルや DB には触れない（偽のモデルで組み立てて、形だけを読む）。`--check` は書き出さずに一致を確かめる。
"""

import json
import sys
from pathlib import Path
from typing import Any

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.runnables.graph import Edge, Graph

from arag.agent.flow import EDGE_LABELS, NODES
from arag.agent.graph import build_agent

ROOT = Path(__file__).resolve().parents[4]
MARKDOWN = ROOT / "docs" / "agent-graph.md"
FLOW_JSON = ROOT / "web" / "src" / "lib" / "chat" / "flow-graph.json"

# 調査の部分グラフの中の節点（create_agent と middleware が作る）
SUB_LABELS = {
    "model": "モデル",
    "tools": "ツール",
    "RecordedSummarization.before_model": "会話の要約",
}


def graph(xray: int) -> Graph:
    return build_agent(GenericFakeChatModel(messages=iter([]))).get_graph(xray=xray)  # type: ignore[no-any-return]


def _edge_key(e: Edge) -> str | None:
    """条件つきの辺の値（辺の関数が返すもの）。値と行き先が同じ名前なら Graph は data を空にする。"""
    if not e.conditional:
        return None
    return e.data if isinstance(e.data, str) else e.target.split(":", 1)[0]


def mermaid() -> str:
    g = graph(xray=1)
    labels = {n.id: n.label for n in NODES}
    nodes = {}
    for key, node in g.nodes.items():
        base = key.split(":", 1)[-1]
        name = labels.get(key) or SUB_LABELS.get(base) or node.name
        nodes[key] = node._replace(name=name)
    edges = []
    for e in g.edges:
        k = _edge_key(e)
        label = EDGE_LABELS.get(k, k) if k and not e.source.startswith("investigate:") else None
        edges.append(e._replace(data=label))
    return Graph(nodes=nodes, edges=edges).draw_mermaid()


def flow_graph() -> dict[str, Any]:
    """画面用: 外側の節点の並び（左から右）と辺。戻る辺（back）・飛ばす辺（skip）を見分ける。"""
    g = graph(xray=0)
    order = [n.id for n in NODES]
    edges = []
    for e in g.edges:
        if e.source not in order or e.target not in order:
            continue
        k = _edge_key(e)
        step = order.index(e.target) - order.index(e.source)
        kind = "back" if step < 0 else "skip" if step > 1 else "next"
        edge: dict[str, Any] = {"source": e.source, "target": e.target, "kind": kind}
        if k:
            edge |= {"key": k, "label": EDGE_LABELS.get(k, k)}
        edges.append(edge)
    edges.sort(key=lambda x: (order.index(x["source"]), order.index(x["target"])))
    return {
        "nodes": [{"id": n.id, "label": n.label, "description": n.description} for n in NODES],
        "edges": edges,
    }


def markdown() -> str:
    rows = "\n".join(f"| `{n.id}` | {n.label} | {n.description} |" for n in NODES)
    return f"""# 回答の流れ（生成物）

`make graph` が `api/src/arag/agent/flow.py` のグラフの定義から書き出す。手で直さない
（CI の `graph-check` が一致を確かめる）。仕様は `specs/029-explicit-graph/`。
「調査」の中は create_agent（モデル ⇄ ツールの輪）。

```mermaid
{mermaid().strip()}
```

| 節点 | 表示名 | 役目 |
|---|---|---|
{rows}

辺の札: {"・".join(f"`{k}` = {v}" for k, v in EDGE_LABELS.items())}
"""


def outputs() -> dict[Path, str]:
    return {
        MARKDOWN: markdown(),
        FLOW_JSON: json.dumps(flow_graph(), ensure_ascii=False, indent=2) + "\n",
    }


def main(argv: list[str]) -> int:
    stale = []
    for path, text in outputs().items():
        if "--check" in argv:
            if not path.exists() or path.read_text() != text:
                stale.append(path)
        else:
            path.write_text(text)
    for path in stale:
        print(f"{path.relative_to(ROOT)} がグラフの定義と一致しません（make graph）", file=sys.stderr)
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
