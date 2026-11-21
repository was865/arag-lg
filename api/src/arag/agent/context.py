"""run の実行文脈（create_agent の context_schema。ツール・middleware が使う）。"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models import BaseChatModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.agent.citations import CitationRegistry, FinalCitations
from arag.agent.config import AgentCfg
from arag.agent.documents import DocumentStore, SqlDocumentStore
from arag.agent.tool_output import ToolOutput
from arag.auth.principal import Principal
from arag.mcp.client import Caller
from arag.mcp.registry import ToolSpec
from arag.search.schemas import SearchRequest, SearchResult
from arag.secrets import SecretBox

SearchFn = Callable[[AsyncSession, Principal, SearchRequest], Awaitable[SearchResult]]
Emit = Callable[[dict[str, Any]], None]


@dataclass
class RunStats:
    model_calls: int = 0
    # 記録したモデルの応答の数（ステップの ID を run の中で一意にする。specs/029 T35）
    model_records: int = 0
    tool_calls: int = 0
    tool_errors: int = 0
    # 社内システム（MCP）を呼んだ回数（specs/032 R17）
    mcp_calls: int = 0
    # 下書きを差し戻した回数（確認の種類 → 回数。種類ごとにターンに 1 回まで。specs/026 ④・037 R10）
    review_counts: dict[str, int] = field(default_factory=dict)
    # システムが最初に行った検索の回数（specs/026 ②）
    primer_searches: int = 0
    # 空の生成（ツール呼び出しも本文も無い応答。specs/026 R25）: やり直した回数（run に 1 度）・記録した回数・
    # 下書きも無く空のまま終えたか（runner が empty_generation に分類する）
    empty_retries: int = 0
    rewrites_discarded: int = 0  # 差し戻しへの返事・引用の消えた書き直しを捨てた回数（026 T29）
    empty_events: int = 0
    # 見張りが何もせず通した回数（ステップの ID を周回ごとに分ける。specs/029 T41）
    guard_passes: int = 0
    empty_failed: bool = False

    @property
    def reviews(self) -> int:
        return sum(self.review_counts.values())

    def reviewed(self, kind: str) -> int:
        return self.review_counts.get(kind, 0)

    def count_review(self, kind: str) -> None:
        self.review_counts[kind] = self.reviewed(kind) + 1


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
    # 質問の種類ごとの注意（検索結果の外、締めの行の後ろに添える指示。specs/031 T16）
    note: str = ""
    # 検索結果に省略した部分がある（章立ての中略など。省略の読み残しの確認に使う。specs/037 R7）
    omitted: bool = False


@dataclass
class Completion:
    """確定した回答（specs/029 finalize）。runner はこれを保存して完了を送る。"""

    answer: str  # 引用を振り直した回答（回答が無ければ利用者に見せる断りの文）
    reason: str | None  # no_answer_reason
    citations: FinalCitations
    followups: bool  # 続けて聞く候補をこの後に作るか
    # 確定の節点で記録したステップ。ストリームが runner に届く前に保存するので、ここで渡す
    steps: list[dict[str, Any]] = field(default_factory=list)
    # 聞き返し（ask_user）の選択肢。続けて聞く候補の代わりに出す（specs/031 R7）
    suggestions: list[str] = field(default_factory=list)


@dataclass
class RunHooks:
    """グラフの節点から呼ぶ、runner の入出力（DB・Redis・画像の保存先）。テストでは空のまま。"""

    # 添付画像を文章にする（質問文を受け取る）。読めなければ例外。画像が無ければ None
    read_image: Callable[[str], Awaitable[str]] | None = None
    image_id: str = ""
    # 回答を保存し、完了を送る（finalize の終わり）
    completed: Callable[[Completion], Awaitable[None]] | None = None
    # 続けて聞く候補を作って届ける（完了の後）。作った候補を返す。None なら作らない
    followups: Callable[[], Awaitable[list[str]]] | None = None


@dataclass
class McpRun:
    """1 回の run の社内システムの状態（RunContext.mcp）。"""

    caller: Caller
    identity_key: str
    box: SecretBox | None
    timeout_sec: float
    max_calls: int
    max_rows: int
    max_chars: int
    # このターンで使えるツール（エージェントのツール名 → 仕様）
    usable: dict[str, ToolSpec] = field(default_factory=dict)
    # 外したサーバ（名前 → (種類, 表示名, 理由)）。最初のモデル呼び出しで記録する
    removed: dict[str, tuple[str, str, str]] = field(default_factory=dict)
    calls: int = 0
    recorded: bool = False
    # 呼び出しで分かった死活を知らせる（サーバ名・理由（None なら応答あり）・ミリ秒）。
    # MCP サーバは生きていてもその先（Odoo）が止まっていることがあるので、ping だけに頼らない（specs/033 R19）
    on_health: Callable[[str, str | None, int], Awaitable[None]] | None = None

    @property
    def systems(self) -> list[str]:
        """使える社内システムの表示名（プロンプトに出す）。"""
        return list(dict.fromkeys(t.server.label for t in self.usable.values()))

    @property
    def catalog(self) -> str:
        """使える社内システムと説明の箇条書き（プロンプト・差し戻しに出す）。"""
        seen = {t.server.label: t.server.description for t in self.usable.values()}
        return "\n".join(f"- {k}: {v}" if v else f"- {k}" for k, v in seen.items())

    @property
    def down(self) -> list[str]:
        """応答しない社内システムの表示名（確かめられなかったと答えさせる。R17）。"""
        return [label for kind, label, _ in self.removed.values() if kind == "mcp_unavailable"]


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
    # 最初の検索の結果の文（understand と primer_search の間で渡す。会話の状態には入れない）
    primer_texts: list[ToolOutput] = field(default_factory=list)
    hooks: RunHooks = field(default_factory=RunHooks)
    # このターンで呼んだツールと引数（同じ呼び出しの繰り返しを省く。specs/031 R4）
    tool_seen: set[str] = field(default_factory=set)
    # 値を書いていない資料の番号を文から外す（ARAG_CITATION_PRUNE、specs/026 T31）
    citation_prune: bool = True
    # 社内システム（MCP）の状態（使えるツール・外したサーバ・呼んだ回数。specs/032）。無ければ文書だけ
    mcp: McpRun | None = None
    # 文書の読み出しの口（specs/037 R11）。省略時は sessionmaker と検索範囲から SQL の実装を作る
    document_store: DocumentStore | None = None

    @property
    def docs(self) -> DocumentStore:
        if self.document_store is None:
            self.document_store = SqlDocumentStore(
                self.sessionmaker,
                self.principal,
                kb_ids=self.kb_ids,
                document_ids=self.document_ids,
                include_archived=self.include_archived,
            )
        return self.document_store
