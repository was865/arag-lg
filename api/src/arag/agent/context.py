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
    # 下書きを差し戻した回数（種類ごとにターンに 1 回まで。specs/026 ④）
    gap_reviews: int = 0
    table_reviews: int = 0
    number_reviews: int = 0
    # システムが最初に行った検索の回数（specs/026 ②）
    primer_searches: int = 0

    @property
    def reviews(self) -> int:
        return self.gap_reviews + self.table_reviews + self.number_reviews


@dataclass
class Primer:
    """ターンの最初にシステムが行った整理と検索の結果（会話の状態には保存しない）。"""

    kind: str = "docs"
    table: bool = False
    queries: tuple[str, ...] = ()
    # モデルに添える検索結果（雑談・検索なしのときは空）
    text: str = ""


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
    # 会話モデルの切り替え（0 = 主モデル。切り替えたら実行の残りはそのモデルで続ける）
    model_index: int = 0
    model_switches: int = 0
    primer: Primer | None = None
    # いま呼んでいるモデルの表示名（「考えた過程」のステップに出す）
    model_label: str = ""
