# 000 API 一覧

## 1. 全体の流れ

```
ブラウザ ──(同一オリジン Cookie)──▶ Next.js 16
   │                                 ├ /api/auth/*        Better Auth（Next が直接処理）
   │                                 └ /api/v1/*          Python へのプロキシ（Route Handler）
   │                                        │  Authorization: Bearer <Better Auth 発行 JWT>
   │                                        │  X-Request-Id 付与・SSE はそのまま流す
   │                                        ▼
   │                                 FastAPI（/v1/*）── Postgres / Qdrant / Redis / TEI
```

- ブラウザが Python を直接叩くことはない（Cookie・CORS・CSRF を Next に集約）。Next の `/api/v1/[...path]` は**認証付きの透過プロキシ**で、リクエスト・レスポンスともに中身を解釈しない（multipart と SSE をストリームのまま通す）。
- Python は JWT（EdDSA）を Better Auth の JWKS で検証し、`sub`（ユーザー ID）・`role`（owner/admin/member）・`email_verified` を使う。
- 型: FastAPI の OpenAPI → `openapi-typescript` で `web/src/lib/api/schema.d.ts` を生成、`openapi-fetch` で呼ぶ。手書き `rag-client.ts` は作らない。
- SSE のイベント payload（custom ストリーム）は JSON Schema を正とし、pydantic と zod の両方を生成して**契約テスト**で一致を保証する。
- 表記: パスは Python 側（`/v1/...`）。ブラウザからは `/api/v1/...`。権限は `user`（ログイン済み）/ `verified`（メール検証済み）/ `kb:read|write`（KB 権限）/ `admin`（owner または admin）。

## 2. Next.js が持つ API（Better Auth）

Better Auth の標準エンドポイントを `/api/auth/*` にそのまま公開する（自前ルートは作らない）。

| 用途 | エンドポイント（Better Auth 標準） | 旧版 |
|---|---|---|
| 登録 / ログイン / ログアウト | `POST /sign-up/email`, `POST /sign-in/email`, `POST /sign-out` | `auth/{register,login,logout}` |
| 現在のセッション | `GET /get-session` | `auth/me` |
| メール検証・再送 | `GET /verify-email`, `POST /send-verification-email` | `auth/email/{verify,resend}` |
| パスワード忘れ・再設定・変更 | `POST /request-password-reset`, `POST /reset-password`, `POST /change-password` | `auth/password/*` |
| セッション一覧・個別失効・他端末失効・全失効 | `GET /list-sessions`, `POST /revoke-session`, `POST /revoke-other-sessions`, `POST /revoke-sessions` | `auth/sessions*`, `auth/revoke-all` |
| 表示名変更 | `POST /update-user` | `account/name` |
| Python 用 JWT・公開鍵 | `GET /token`, `GET /jwks` | （旧版は自前 JWT） |
| 管理: ユーザー一覧・ロール・パスワード設定・強制サインアウト・BAN（P5） | admin プラグイン `/admin/*` | `admin/members/*` |

メール送信は Better Auth の hook から SMTP（開発時は Mailpit）。ログイン失敗ロック等の不足分は Better Auth の hooks で補う。

## 3. Python（FastAPI）が持つ API

### 3.1 健康状態

| メソッド・パス | 説明 | 権限 |
|---|---|---|
| `GET /healthz` | liveness | なし |
| `GET /readyz` | Postgres / Qdrant / Redis / TEI の疎通（詳細はログのみ） | なし |
| `GET /v1/system` | 解析エンジン・推論サービスの状態（旧 `api/system`） | admin |

### 3.2 チャット（スレッド・run）

| メソッド・パス | 説明 | 権限 | 旧版 |
|---|---|---|---|
| `GET /v1/threads` | 自分のスレッド一覧（ピン → 更新順、カーソルページング） | user | `api/threads` GET |
| `POST /v1/threads` | スレッド作成（タイトルは最初の質問から自動） | verified | `api/threads` POST |
| `GET /v1/threads/{id}` | スレッドと全ターン（メッセージ・ツールステップ・引用・フィードバック） | 所有者 | `api/threads/[id]` GET |
| `PATCH /v1/threads/{id}` | 名前変更・ピン | 所有者 | 同 PATCH |
| `DELETE /v1/threads/{id}` | 削除（checkpoint も削除） | 所有者 | 同 DELETE |
| `POST /v1/threads/{id}/runs` | 質問を送って run 開始 → `{run_id, message_id}` を即返す。本文: `query`, `model_id?`, `kb_ids?`, `include_archived?`, `attachment_document_ids?`, `agent_cfg?`, `from_message_id?`（そのターン以降を捨てて分岐 = 再生成・質問編集） | verified + レート制限・月次上限 | `api/chat` POST |
| `GET /v1/runs/{run_id}/stream` | SSE。`Last-Event-ID`（= Redis Stream の entry id）から再開。終了後 1 時間は再読可 | run の所有者 | `chat/runs/[runId]/stream` |
| `POST /v1/runs/{run_id}/cancel` | 取消要求 | run の所有者 | `chat/runs/[runId]/cancel` |
| `GET /v1/threads/{id}/active-run` | 実行中の run があれば返す（リロード後の再接続用） | 所有者 | 無し（新規） |
| `PUT /v1/messages/{id}/feedback` | 👍👎・理由タグ・コメント（upsert） | スレッド所有者 | `threads/[id]/messages/[mid]/feedback` PUT |
| `DELETE /v1/messages/{id}/feedback` | 評価取消 | 同上 | 同 DELETE |
| `GET /v1/models` | 選択可能なモデル一覧（キー有無で `available`） | user | `api/models` |

**SSE イベント（`/v1/runs/{id}/stream`）**: LangGraph の `messages` と `custom` を薄く包んで送る。

| event | 中身 | 由来 | 旧 `AgentEvent` との対応 |
|---|---|---|---|
| `run.started` | `run_id`, `thread_id`, `message_id` | FastAPI | （新規） |
| `messages` | AI メッセージチャンク（本文トークン・ツール呼び出し引数・`usage_metadata`）とメタ（`langgraph_node`） | LangGraph `messages` | `answer-start` / `answer-delta`、`step`（ツール開始） |
| `custom` | 型付きアプリイベント（下表） | `get_stream_writer()` | `step`（サブ段階）・`done` の引用部分 |
| `run.completed` | `tokens`, `duration_ms`, `no_answer_reason`, `suggestions`（specs/028） | FastAPI | `done` + `saved` |
| `run.failed` / `run.cancelled` | `message` | FastAPI | `error` |

custom イベントの種類（JSON Schema で定義し pydantic / zod を生成）:

| `type` | payload の要点 |
|---|---|
| `step` | `id`, `parent_id?`, `name`（rewrite_query / search / keyword_search / rerank / grade / read_section / verify / revise …）, `status`, `duration_ms`, `input`, `output`, `summary` — 旧 `ToolCall` に 1:1 で写せる形 |
| `citation.registered` | `n`, `document_id`, `document_title`, `chunk_id`, `section_id`, `heading_path`, `snippet`, `block_type`, `page`, `score?` |
| `citation.validated` | 本文中の `[n]` のうち未登録だったものと、その処理（削除 / 置換） |
| `answer.revised` | 根拠検証で書き直した場合の確定本文（ストリーム済み本文を置換） |
| `no_answer` | `reason`（no_sources / step_budget_exhausted / tool_failed / generation_failed） |

> 旧版は検証のため回答をサーバ側でバッファし、最後に 1 回で流していた。新版は本文をトークン単位で流し、検証で書き直した場合だけ `answer.revised` で置き換える（体感速度の改善）。検証 ON 時の表示ちらつきは UI で吸収する（P3 の design で確定）。

### 3.3 知識ベース

| メソッド・パス | 説明 | 権限 | 旧版 |
|---|---|---|---|
| `GET /v1/kbs` | アクセス可能な KB（書込可否・文書数付き） | user | `api/kbs` GET |
| `POST /v1/kbs` | 全社 KB を作成 | admin | `api/kbs` POST |
| `PATCH /v1/kbs/{id}` | 名前変更 | admin（全社）/ 本人（個人） | `kbs/[id]` PATCH |
| `POST /v1/kbs/{id}/archive` ・ `/unarchive` | アーカイブ切替 | admin | `kbs/[id]/{archive,unarchive}` |
| `DELETE /v1/kbs/{id}` ・ `POST /v1/kbs/{id}/restore` | KB ごとごみ箱へ / 復元 | admin | `kbs/[id]` DELETE, `restore` |

### 3.4 フォルダ

| メソッド・パス | 説明 | 権限 | 旧版 |
|---|---|---|---|
| `GET /v1/kbs/{kb_id}/folders` | フォルダツリー | kb:read | `api/folders` GET |
| `POST /v1/kbs/{kb_id}/folders` | 作成 | kb:write | 同 POST |
| `PATCH /v1/folders/{id}` | 名前変更・親の付け替え（移動） | kb:write | `folders/[id]` PATCH, `move` |
| `DELETE /v1/folders/{id}` ・ `POST /v1/folders/{id}/restore` | ごみ箱へ（配下も）/ 復元 | kb:write | `folders/[id]` DELETE, `restore` |

### 3.5 文書・アップロード

| メソッド・パス | 説明 | 権限 | 旧版 |
|---|---|---|---|
| `POST /v1/kbs/{kb_id}/uploads` | multipart で 1〜N ファイル（相対パス付き可）。内容ハッシュで重複判定 → `{document_id, job_id, status: queued｜skipped}` | kb:write + verified | `api/upload` |
| `GET /v1/jobs/events?ids=` | 複数ジョブの進捗を 1 本の SSE で（段階 parsing → chunking → contextualizing → embedding → indexing → ready） | user | `uploads/stream` |
| `GET /v1/jobs/{id}` | ジョブ状態 | user | `uploads/[id]` |
| `POST /v1/jobs/{id}/retry` ・ `/cancel` | 再試行・取消 | kb:write | `uploads/[id]/{retry,cancel}` |
| `GET /v1/documents` | 一覧（`kb_id`, `folder_id`, 状態, カーソル） | kb:read | `api/documents` GET |
| `GET /v1/documents/stats` | 件数・容量など | user | `documents/stats` |
| `GET /v1/documents/{id}` | メタデータ | kb:read | — |
| `PATCH /v1/documents/{id}` | 名前変更・フォルダ移動 | kb:write | `documents/[id]/move` |
| `POST /v1/documents/bulk-move` ・ `/bulk-delete` | 一括移動・一括ごみ箱 | kb:write | 同名 |
| `DELETE /v1/documents/{id}` | ごみ箱へ | kb:write | `documents/[id]` DELETE |
| `POST /v1/documents/{id}/restore` | 復元 | kb:write | `restore` |
| `DELETE /v1/documents/{id}/purge` | 完全削除（本人 24h 以内 / admin はいつでも） | 規則による | `purge` |
| `GET /v1/documents/{id}/original` | 原本ファイル（Range 対応） | kb:read | `raw`（旧は存在確認のみ）+ プレビュー |
| `GET /v1/documents/{id}/rendered` | 解析済み Markdown（表・数式・Mermaid 含む） | kb:read | `rendered` |
| `GET /v1/documents/{id}/outline` | 見出しツリー（親セクション単位） | kb:read | 無し（新規。`get_outline` ツールと共用） |
| `GET /v1/documents/{id}/sections/{section_id}` | セクション本文 | kb:read | 無し（新規。`read_section` と共用） |
| `GET /v1/documents/{id}/chunks` | チャンク一覧（プレビュー） | kb:read | `preview` |
| `GET /v1/documents/{id}/layout` ・ `/span?chunk_id=` | ページ座標・引用箇所の位置（PDF ハイライト） | kb:read | `layout`, `span` |
| `GET /v1/documents/{id}/assets/{path}` | 抽出画像 | kb:read | `assets/[...path]` |
| `GET /v1/trash` | 自分が見られるごみ箱（文書・フォルダ・KB、期限付き） | user | `api/trash` |

### 3.6 検索（内部・評価用）

| メソッド・パス | 説明 | 権限 |
|---|---|---|
| `POST /v1/search` | ハイブリッド検索 + rerank の結果を直接返す（エージェントのツールと同じ関数）。eval ランナーと管理画面の診断が使う | admin |

### 3.7 管理（P5）

| メソッド・パス | 説明 | 旧版 |
|---|---|---|
| `GET /v1/admin/overview` | 件数・稼働状況 | `admin/page` |
| `GET/PUT/DELETE /v1/admin/llm-keys` ・ `POST /v1/admin/llm-keys/test` | プロバイダキー（暗号化保存・末尾 4 桁のみ返す）・接続テスト | `admin/llm-keys*` |
| `GET/PUT/DELETE /v1/admin/models` ・ `GET /v1/admin/models/health` | モデル目録の差分設定・提供中モデルとの突合 | `admin/models*` |
| `GET /v1/admin/kbs` ・ `/v1/admin/kbs/{id}/documents` | 全 KB と文書 | `admin/kbs*` |
| `GET /v1/admin/trash` ・ `POST /v1/admin/trash/transfer` | 全社ごみ箱・救出（移管） | `admin/trash*` |
| `POST /v1/admin/users/{id}/offboard` ・ `/reactivate` ・ `GET /offboard-preview` | 退職処理（個人 KB をごみ箱へ）。Better Auth 側の無効化と同時に呼ぶ | `admin/members/*offboard*`, `reactivate` |
| `GET /v1/admin/audit` | 監査ログ（フィルタ・ページング） | `admin/audit` |
| `GET /v1/admin/feedback` ・ `GET /v1/admin/feedback/{id}` ・ `POST …/{id}/resolve` ・ `/reopen` | 技術者への報告（評価・状態で絞る一覧と未対応の件数・ターンの全記録・対応済みと戻し。監査ログに残す。specs/028） | 新規 |
| `GET /v1/admin/analytics/overview` ・ `/gaps` ・ `/diagnostics/{message_id}` | 利用量・品質・知識ギャップ・診断 | `admin/analytics/*` |

## 4. 旧版にあって新版に作らない API

| 旧 API | 理由 |
|---|---|
| `api/capabilities/**`, `admin/members/[id]/capabilities/*` | 能力包は除外 |
| `api/work-calendar`, `admin/work-calendar*` | 工作日历は除外 |
| `api/skills` | スキルは後続 |
| `api/teams*`, `kbs/[id]/{grants,scope}` | チーム・部門 KB は後続 |
| `api/account/locale`, `api/account/onboarding` | 日本語のみ / ツアーは後続 |
| `auth/remember` | Better Auth の rememberMe で代替 |
| Python `/retrieve/stream`（web から呼ぶ検索 SSE） | 検索はエージェント内部の関数呼び出しになり、HTTP 越しに呼ばない |
