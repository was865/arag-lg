# 037 エージェントの層の整理 — 設計

## 0. 層

| 層 | 中身 | 依存してよいもの |
|---|---|---|
| 規則（domain） | `citations`・`numbers`・`table`・`calc`・`answer_text`・`prune`・`tool_output`・`review_rules` | 標準ライブラリ・pydantic・`search.schemas` |
| 処理（application） | `ops`（ツールの中身）・`primer`・`understand`・`flow` の節点 | 規則・口（`DocumentStore`・`SearchFn`・`search.hooks`） |
| つなぎ（adapters） | `tools`・`middleware`・`model_switch`（LangChain）、`documents.SqlDocumentStore`（SQLAlchemy）、`stream`（Redis）、`router`（FastAPI）、`runner` | すべて |

物理的なフォルダ分け（R14）は後で行う。今回は `test_layering.py` の一覧で層を決め、import を検査する。

## 1. 依存の向き（R1〜R4）

- `agent.catalog.secret_box` → `arag.secrets.secret_box`（`catalog` は名前を残して再 export しない。呼び元を直す）。
- `agent.mcp_tools.user_departments` → `arag.mcp.registry.user_departments`（部門の表はすでに registry が読む）。
- `search.service` の `stage_hook`・`candidates_hook`（ContextVar）→ `search/hooks.py`。`search.service` はそこから import する。
- `test_layering.py`: `ast` で各モジュールの import を集め、禁止の組を見つけたら落とす（外部の道具は足さない）。

## 2. ツールの結果（R5〜R7）

`agent/tool_output.py`（規則の層）:

```python
@dataclass(frozen=True)
class ToolOutput:
    text: str                 # モデルに渡す文
    materials: int = 0        # 添えた資料（<資料 n=…>）の数
    weak: bool = False        # 0 件か、関連度の低い資料だけ
    omitted: bool = False     # 章立ての中略・文書の打ち切り
    fallback: str | None = None   # keyword_search が広げた先: "codes" | "semantic"
    rows: tuple[int, int] | None = None  # table_query: (表の行数, 当てはまった行数)

    def artifact(self) -> dict[str, Any]: ...
    @classmethod
    def from_artifact(cls, text: str, artifact: Any) -> "ToolOutput": ...
```

- `ops.op_*` は `ToolOutput` を返す。`tools.py` の各ツールは `response_format="content_and_artifact"` で `(out.text, out.artifact())` を返す。
- `StepMiddleware` は `ToolMessage.artifact` から `ToolOutput` を作り、要約（資料 n 件・完全一致 0 件 → …・n 行中 m 行）を決める。
- `primer` は `ToolOutput.weak` で空振りを判断する（`weak_result(text)` を廃止）。`Primer` に `omitted` を持たせ、省略の確認に使う。
- 失敗の文（見つからない・範囲が空）は `ToolOutput(text)`（資料 0）。

## 3. 確認の規則（R8〜R10）

`agent/review_rules.py`（規則の層。LangChain を import しない）:

```python
@dataclass(frozen=True)
class ToolResult:   # このターンのツールの結果 1 件
    name: str; text: str; ok: bool; out: ToolOutput

@dataclass
class Draft:        # 確認に渡す値（middleware がメッセージから作る）
    ctx: RunContext; answer: str; asked: str; results: list[ToolResult]
    # 派生: materials()・searches()・own_searches()・called_mcp()・omitted()・current・checked
    
@dataclass(frozen=True)
class ReviewRule:
    kind: str; label: str
    check: Callable[[Draft], Review | None]

RULES: tuple[ReviewRule, ...] = (omitted, current, system_missed, system_gap, gap, table, structure, numbers)
```

- `pick_review(ctx, turn, …)` は `Draft` を作って `RULES` を順に回す（`done` にある種類は飛ばす）。
- `reason`（補助モデルを呼ぶ非同期の確認）は並びの外のまま。表示名だけ `REVIEW_LABELS` に入れる。
- `RunStats.review_counts: dict[str, int]`。`reviews` はその合計。`open_send_back` は `review_counts[kind] += 1` だけにする。
- 差し戻しの note の文（`GAP_NOTE` など）は規則と同じファイルに移す。

## 4. 文書の読み出しの口（R11）

`agent/documents.py`:

```python
class DocumentStore(Protocol):
    async def scope(self) -> Scope
    async def list(self, query: str | None, limit: int) -> list[DocRow]
    async def get(self, document_id: UUID) -> Document | None        # 範囲の中だけ
    async def by_name(self, name: str, limit: int) -> list[Document]
    async def sections(self, content_hash: str) -> list[Section]
    async def section(self, section_id: UUID, prefer: UUID | None) -> tuple[Section, Document] | None
    async def sheet_parts(self, content_hash: str, headings: list[str]) -> list[Section]
    async def recent(self, user_id: str, limit: int) -> list[str]
    async def named(self, question_flat: str, refs: list[str]) -> ...
```

- `SqlDocumentStore(sessionmaker, principal, kb_ids, document_ids, include_archived)` が今の SQL をそのまま持つ。
- `RunContext.docs` は省略時に `SqlDocumentStore` を作って返す（呼び元・テストの組み立ては変えない）。
- 返す ORM の行（`Document`・`Section`）はそのまま使う（読み取りだけ。値の型を新しく作らない）。

## 5. runner（R12）

- `build_context(deps, req) -> RunContext` を `execute_run` から分ける。
