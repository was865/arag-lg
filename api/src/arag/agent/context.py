"""run の実行文脈（create_agent の context_schema。ツール・middleware が使う）。"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
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
    # 空の生成（ツール呼び出しも本文も無い応答。specs/026 R25）: やり直した回数（run に 1 度）・記録した回数・
    # 下書きも無く空のまま終えたか（runner が empty_generation に分類する）
    empty_retries: int = 0
    rewrites_discarded: int = 0  # 差し戻しへの返事・引用の消えた書き直しを捨てた回数（026 T29）
    empty_events: int = 0
    empty_failed: bool = False

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
    # どの検索も 0 件か関連度の低い資料だけだった（資料に無い質問らしい。specs/026 T17）
    weak: bool = False


@dataclass
class RunContext:
    principal: Principal
    sessionmaker: async_sessionmaker[AsyncSession]
    search: SearchFn
    question: str = ""
    # 利用者が書いた質問の文そのまま（画像の説明を足す前）。
    # 引用の刈り込みで質問の値を除くのに使う（specs/026 T34）
    user_question: str = ""
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
    # このターンで失敗した table_query の指定（source・where・compute・table）→ 返した誤り（specs/026 T12）
    table_failures: dict[tuple[str, str, str, int], str] = field(default_factory=dict)
    # table_query の結果の構造（ツールの呼び出し ID → table.summarize）。記録にだけ出す（specs/028 T8）
    table_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    # 最後に差し戻した下書きとその確認の種類。書き直しが空のままなら、これを回答にする（specs/026 R25）
    review_draft: tuple[AIMessage, str] | None = None
    # 値を書いていない資料の番号を文から外す（ARAG_CITATION_PRUNE、specs/026 T31）
    citation_prune: bool = True
