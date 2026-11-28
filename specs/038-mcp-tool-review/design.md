# 038 — 設計

## 表（移行 0011、`mcp_tools` に列を足す）

| 列 | 意味 |
|---|---|
| `def_hash` | 今の定義の指紋（R1。`registry.definition_hash`） |
| `side_effect` | 管理者の決めた副作用 `read` / `write`。未審査は NULL（R7） |
| `approved_hash`・`approved_description`・`approved_input_schema`・`approved_read_only` | 審査した定義（R2） |
| `approved_by`・`approved_at` | 審査した人と時刻 |
| `model_description` | モデルに渡す説明の書き換え（R11。NULL ならサーバの説明） |

- 既存の `description`・`input_schema`・`read_only`（サーバの印）は「今の定義」のまま。
- 状態は列に持たず計算する: `approved_hash` が NULL → `unreviewed`、`approved_hash == def_hash` → `approved`、違えば `changed`。
- 既存の行は移行で審査済みにする（審査した定義 = 今の定義、副作用は印があれば `read`、無ければ NULL）。指紋は移行の中で同じ式で計算する。

## 指紋

```python
definition_hash(name, description, input_schema, read_only) =
  sha256(json.dumps({"name", "description", "input_schema", "read_only"}, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
```

## API（admin）

- `McpToolOut` に `status`・`def_hash`・`side_effect`・`read_only_hint`（032 の `read_only` を改名）・`model_description`・
  `approved_hash`・`approved_description`・`approved_input_schema`・`approved_read_only`・`approved_by`・`approved_at`・`fetched_at`・`usable` を足す。
- `McpServerOut.pending_review`: 未審査と変わったツールの数。
- `POST /v1/admin/mcp-servers/{id}/tools/review` `{tool, def_hash, side_effect, model_description, enabled}`。
  指紋が違えば 409 `definition_moved`。`enabled` で副作用が `write` なら 422 `not_read`。
- `PUT /v1/admin/mcp-servers/{id}/tools`（使うの一括）: 審査済みでないものは 422 `not_reviewed`、副作用が読み取りでないものは 422 `not_read`。
- 取り直し（`refresh_server`）は check_error に変更を書かない（接続の誤りだけ）。変わったツールは `mcp.tool.changed` で監査に残す。

## エージェント

- `load_tools` は `enabled AND side_effect='read' AND approved_hash = def_hash` のツールを返し、説明は `model_description or description`。
- `load_held` は `enabled AND approved_hash IS NOT NULL AND approved_hash <> def_hash` を返す。`prepare(..., held=...)` が `McpRun.held` に入れ、
  `record_removed` が `mcp_held` を記録する。

## 画面（`web/src/components/admin/`）

- `/admin/systems`（`systems-view.tsx`）: 上に `Segmented` で「システム / ツール」。行に「審査待ち N」。「ツール」の操作は一覧（`?server=`）へ移る。
- `/admin/systems/tools`（`mcp-tools-view.tsx`）: 表と絞り込み。
- `/admin/systems/tools/[server]/[tool]`（`mcp-tool-detail.tsx`）: 詳細・差分・審査。
- 差分は `web/src/lib/admin/line-diff.ts`（LCS の行の差分。純関数・テスト）。入力の項目は `web/src/lib/admin/schema-params.ts`。
