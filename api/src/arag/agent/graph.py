"""エージェントの組み立て（specs/005-agent design §3）。"""

from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver

from arag.agent.context import RunContext
from arag.agent.middleware import (
    AgentPolicyMiddleware,
    CitationMiddleware,
    RecordedSummarization,
    StepMiddleware,
)
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
        RecordedSummarization(
            utility or model, trigger=("tokens", summarize_at_tokens), keep=("messages", 12)
        ),
        AgentPolicyMiddleware(),
    ]
    # 代替が無くても入れる（失敗の理由と、いまのモデル名を「考えた過程」に出すため）
    fallbacks = [] if fallback is None else [(fallback_label, fallback)]
    middleware.append(ModelSwitchMiddleware(model_label, fallbacks))
    middleware += [StepMiddleware(), CitationMiddleware()]
    return create_agent(
        model,
        tools=TOOLS,
        middleware=middleware,
        context_schema=RunContext,
        checkpointer=checkpointer,
    )
