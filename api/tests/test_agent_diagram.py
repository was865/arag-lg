"""回答の流れの図の書き出し（specs/029 R5・T12）。"""

import json

from arag.agent.diagram import FLOW_JSON, flow_graph, main, mermaid


def test_committed_outputs_are_up_to_date() -> None:
    assert main(["--check"]) == 0, "docs/agent-graph.md・flow-graph.json が古い。`make graph` で書き出すこと"


def test_mermaid_shows_labels_and_the_investigate_subgraph() -> None:
    text = mermaid()
    assert "understand(理解)" in text and "guard(見張り)" in text
    assert (
        "&nbsp;差し戻し&nbsp;" in text
        and "&nbsp;下書き・聞き返し&nbsp;" in text
        and "&nbsp;やり直し&nbsp;" in text
    )
    assert "subgraph investigate" in text and "(ツール" in text


def test_flow_graph_marks_back_and_skip_edges() -> None:
    g = flow_graph()
    assert [n["id"] for n in g["nodes"]][:3] == ["read_image", "understand", "primer_search"]
    kinds = {(e["source"], e["target"]): (e["kind"], e.get("key")) for e in g["edges"]}
    assert kinds[("review", "investigate")] == ("back", "send_back")
    assert kinds[("guard", "investigate")] == ("back", "retry")
    assert kinds[("guard", "finalize")] == ("skip", "use_draft")
    assert kinds[("understand", "investigate")] == ("skip", "chat")
    assert json.loads(FLOW_JSON.read_text()) == g
