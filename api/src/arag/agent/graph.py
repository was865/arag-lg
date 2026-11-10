"""エージェントの組み立て（specs/005-agent design §3）。"""

from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver

from arag.agent.context import RunContext
from arag.agent.middleware import AgentPolicyMiddleware, CitationMiddleware, StepMiddleware
from arag.agent.model_switch import ModelSwitchMiddleware
from arag.agent.tools import TOOLS


def build_agent(
    model: BaseChatModel,
    *,
    utility: BaseChatModel | None = None,
    fallback: BaseChatModel | None = None,
    model_label: str = "会話モデル",
    fallback_label: str = "代替モデル",
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    summarize_at_tokens: int = 12_000,
) -> Any:
    middleware: list[Any] = [
        SummarizationMiddleware(
            utility or model, trigger=("tokens", summarize_at_tokens), keep=("messages", 12)
        ),
        AgentPolicyMiddleware(),
    ]
    if fallback is not None:
        middleware.append(ModelSwitchMiddleware(model_label, [(fallback_label, fallback)]))
    middleware += [StepMiddleware(), CitationMiddleware()]
    return create_agent(
        model,
        tools=TOOLS,
        middleware=middleware,
        context_schema=RunContext,
        checkpointer=checkpointer,
    )
