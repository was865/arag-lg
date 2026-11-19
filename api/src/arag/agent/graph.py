"""エージェントの組み立て（specs/005-agent design §3、specs/029）。

外側の回答の流れ（`flow.build_graph`）に、調査の部分グラフ（create_agent）を入れて返す。
ストリームは `subgraphs=True` で受ける（部分グラフの中のステップと本文の断片を受けるため）。
"""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver

from arag.agent.flow import build_graph, build_investigate


def build_agent(
    model: BaseChatModel,
    *,
    utility: BaseChatModel | None = None,
    fallback: BaseChatModel | None = None,
    model_label: str = "会話モデル",
    fallback_label: str = "代替モデル",
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    summarize_at_tokens: int = 12_000,
    extra_tools: list[BaseTool] | None = None,
) -> Any:
    """extra_tools は社内システム（MCP）のツール（specs/032）。利用者ごとの絞り込みは middleware が行う。"""
    investigate = build_investigate(
        model,
        utility=utility,
        fallback=fallback,
        model_label=model_label,
        fallback_label=fallback_label,
        summarize_at_tokens=summarize_at_tokens,
        extra_tools=extra_tools,
    )
    return build_graph(investigate, checkpointer=checkpointer)
