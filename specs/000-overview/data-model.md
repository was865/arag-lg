# 000 データモデル

## 1. 所有の境界

| 所有者 | 保存先 | 中身 | マイグレーション |
|---|---|---|---|
| Next.js（Better Auth） | Postgres スキーマ `auth` | ユーザー・セッション・アカウント（パスワードハッシュ）・検証トークン・JWKS | Better Auth CLI（`@better-auth/cli migrate`） |
| Python | Postgres スキーマ `app` | KB・文書・チャンク・ジョブ・スレッド・メッセージ・引用・フィードバック・run・監査・LLM 設定 | Alembic |
| Python（LangGraph） | Postgres スキーマ `lg` | checkpoint（`checkpoints` / `checkpoint_blobs` / `checkpoint_writes` / `checkpoint_migrations`） | `PostgresSaver.setup()` |
| Python | Qdrant | 子チャンクのベクトル（dense + BM25 sparse）と絞り込み用 payload | 起動時に collection を冪等作成 |
| Python | Redis | run イベントストリーム・取消フラグ・入庫ジョブキュー・レート制限 | — |
| Python | ファイルストレージ（ローカルボリューム / S3 互換） | 原本・解析成果物（Markdown・画像・レイアウト JSON） | — |

- 旧版は web（drizzle）が users / threads / messages / citations を持ち、rag（Alembic）が documents を持つ二重構造だった。新版は **Next は認証表のみ**、他はすべて Python（handoff 第 1 節）。
- スキーマをまたぐ外部キーは張らない（`user_id` は Better Auth の `user.id` を文字列で保持）。ユーザー削除の代わりに無効化（BAN）を使うため、孤児行は生じない運用とする。

## 2. Better Auth（`auth` スキーマ、Next 所有）

Better Auth 標準表 + 追加列。

| 表 | 主な列 | 備考 |
|---|---|---|
| `user` | id, email, emailVerified, name, image, createdAt, updatedAt, **role**（owner/admin/member）, **banned**, banReason, banExpires | role・ban は admin プラグイン |
| `session` | id, userId, token, expiresAt, ipAddress, userAgent, createdAt, updatedAt | セッション一覧 UI に使う |
| `account` | id, userId, providerId, accountId, password(hash), … | |
| `verification` | id, identifier, value, expiresAt | メール検証・パスワード再設定 |
| `jwks` | id, publicKey, privateKey, createdAt | jwt プラグイン（Python 検証用） |
| （後続）`organization` / `member` / `team` / `teamMember` / `invitation` | | チーム機能を入れるとき organization プラグインで追加 |

旧版との対応: `users.first_name / initials / org` は表示用の派生値なので保存しない（name から算出、組織名は設定値）。`users.disabled_at` → `banned`。`users.onboarded_at` は後続。`session_tokens`（自前 jti 失効表）→ `session`。`auth_tokens` → `verification`。

## 3. Python（`app` スキーマ）

### 3.1 知識ベースと文書（旧版の内容寻址をそのまま継承）

```
knowledge_bases 1─* documents *─1 contents 1─* sections 1─* chunks
       │                │                 └─* ingest_jobs
       └─* folders ─────┘(folder_id)
```

| 表 | 列 | 備考 |
|---|---|---|
| `knowledge_bases` | id, **kind**（personal / org）, owner_user_id（personal のみ）, name, status（active / archived）, deleted_at, deleted_by, created_at | 個人 KB はユーザーごとに 1 つ（部分 UNIQUE）。後続で kind=team と `kb_grants` を追加 |
| `folders` | id, kb_id, parent_id, name, deleted_at, deleted_by, created_at | 表示専用ツリー。生存行だけの兄弟名 UNIQUE（部分 index） |
| `contents` | **content_hash**（PK, sha256）, mime, size, page_count, status, error, raw_path, parsed_path, ref_count, indexed_at, parser_version, chunker_version, embed_model, created_at | 同一バイトは 1 回だけ解析。`*_version` / `embed_model` は再索引判定用（新規） |
| `documents` | id, kb_id, content_hash, folder_id, filename, uploaded_by, deleted_at, deleted_by, created_at | UNIQUE(kb_id, content_hash)。引用・URL の識別子 |
| `sections` | id, content_hash, ordinal, heading_path, level, page_start, page_end, text, token_len | **新規**: 親チャンク（章・節）。`read_section` / `get_outline` / 引用表示に使う |
| `chunks` | id, content_hash, section_id, ordinal, block_type（text / table / figure_caption …）, page_start, page_end, text, **context**（文脈付与文）, token_len | 子チャンク。ベクトル化する本文は `context + text` |
| `ingest_jobs` | id, content_hash, status, stage, progress, stage_detail, error, attempts, created_at, updated_at | 段階: parsing → chunking → contextualizing → embedding → indexing → ready |

削除と GC: 文書・フォルダ・KB は `deleted_at` で論理削除 → 30 日後にワーカーが物理削除し、`contents.ref_count` が 0 になった実体（ファイル・行・Qdrant 点）を GC。

### 3.2 対話

| 表 | 列 | 備考 |
|---|---|---|
| `threads` | id, user_id, title, pinned, created_at, updated_at | LangGraph の `thread_id` と同じ値 |
| `messages` | id, thread_id, ordinal, query, answer_text, model_id, tokens_in, tokens_out, duration_ms, steps(jsonb), no_answer_reason, checkpoint_id, run_id, created_at | 1 ターン = 1 行。run 完了時に確定。`steps` は旧 `ToolCall[]` 形式（履歴表示用）。`checkpoint_id` は分岐（再生成・質問編集）の起点 |
| `citations` | id, message_id, ordinal(n), document_id, chunk_id, section_id, document_title, heading_path, snippet, block_type, page, score | 旧版と同じ。文書削除後も表示できるようスナップショットを保持 |
| `message_feedback` | id, message_id(UNIQUE), user_id, rating（up / down）, reason_tags[], comment, trace_id, created_at, updated_at | `trace_id` は Langfuse（任意）との突合用 |
| `runs` | id, thread_id, message_id, user_id, status（running / completed / failed / cancelled）, started_at, finished_at, error | 実行中 run の検出・再接続。イベント本体は Redis Stream（TTL 1 時間） |

**checkpoint と `messages` の関係**: LangGraph の checkpoint が**エージェント状態の正**（再開・分岐・interrupt に使う）。`messages` / `citations` は一覧・履歴表示・分析のための**確定済みビュー**で、run 完了時に 1 トランザクションで書く。履歴表示で checkpoint を読む必要は無い。

### 3.3 運用・管理

| 表 | 列 | 備考 |
|---|---|---|
| `audit_logs` | id, ts, actor_id, actor_email, action, resource_type, resource_id, result（ok / denied / error）, ip, request_id, detail(jsonb) | 追記専用（旧版 web の `audit_logs` と rag の `audit_events` を統合）。認証イベントは Better Auth の hook から Python に送るか、Next 側で同じ形式に書く（P4 で決定） |
| `llm_provider_keys` | provider（PK）, encrypted_key, key_last4, updated_at, updated_by | AES-256-GCM。env が設定されていれば env 優先（旧版どおり） |
| `llm_model_config` | id（'default' 固定）, config(jsonb), updated_at, updated_by | 内置目録への差分 |
| `usage_monthly` | user_id, month, tokens | 月次トークン上限の判定用（旧版は messages を集計していた） |

## 4. Qdrant

collection `chunks`（埋め込みモデルを切り替えるときは `chunks__<model>` を並行作成して alias で切替）:

| 項目 | 内容 |
|---|---|
| point id | `chunks.id` |
| named vector `dense` | bge-m3（1024 次元, cosine）／比較候補 ruri-v3-310m（768 次元） |
| sparse vector `bm25` | Sudachi（モード C + 正規化形）で分かち書きした語の出現数、`modifier: idf` |
| payload | content_hash, section_id, document_ids[]（参照中の文書）, kb_ids[]（参照中の KB）, block_type, page_start, heading_path, lang |
| payload index | content_hash, kb_ids, document_ids, block_type（keyword） |

- 旧版は検索時に SQL で可視 KB の content_hash 一覧を解決して渡していた。新版は payload に `kb_ids` / `document_ids` を持たせ、**文書の追加・移管・削除のたびに set_payload で更新**する（Qdrant フィルタで完結し、KB が大きくても検索リクエストが肥大しない）。整合性はワーカーの定期照合で担保する。
- 可視性の最終判定は必ず Python 側でも行う（payload は高速化のための複製であり権限の正ではない）。

## 5. Redis

| キー | 型 | 用途 | TTL |
|---|---|---|---|
| `run:{run_id}:events` | Stream | SSE 中継（entry id = `Last-Event-ID`） | 完了後 1 時間 |
| `run:{run_id}:cancel` | String | 取消フラグ | 1 時間 |
| `ingest:job:{id}` | Pub/Sub | 入庫進捗の通知（キュー本体は Postgres の `ingest_jobs`） | — |
| `rl:{scope}:{key}` | String/ZSet | レート制限 | 窓長 |

## 6. ファイルストレージ

```
<root>/contents/<hash[0:2]>/<hash>/
  original.<ext>         原本
  docling.json           Docling の DoclingDocument（再チャンク用に保存）
  rendered.md            プレビュー用 Markdown
  layout.json            ページ座標（引用ハイライト用）
  assets/                抽出画像
```

`docling.json` を保存しておくことで、チャンク戦略や文脈付与を変えたときに**再解析なしで再索引**できる。
