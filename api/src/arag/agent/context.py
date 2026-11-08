"""run の実行文脈（create_agent の context_schema。ツール・middleware が使う）。"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models import BaseChatModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.agent.citations import CitationRegistry
from arag.agent.config import AgentCfg
from arag.auth.principal import Principal
from arag.search.schemas import SearchRequest, SearchResult

SearchFn = Callable[[AsyncSession, Principal, SearchRequest], Awaitable[SearchResult]]
Emit = Callable[[dict[str, Any]], None]


@dataclass
class RunStats:
    model_calls: int = 0
    tool_calls: int = 0
    tool_errors: int = 0


@dataclass
class RunContext:
    principal: Principal
    sessionmaker: async_sessionmaker[AsyncSession]
    search: SearchFn
    question: str = ""
    kb_ids: list[uuid.UUID] | None = None
    document_ids: list[uuid.UUID] | None = None
    include_archived: bool = False
    cfg: AgentCfg = field(default_factory=AgentCfg)
    registry: CitationRegistry = field(default_factory=CitationRegistry)
    utility_model: BaseChatModel | None = None
    stats: RunStats = field(default_factory=RunStats)
