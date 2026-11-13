# 000 機能一覧（MVP / 後続）

旧版 `a-rag@main(83b37005)` の機能を棚卸しし、新版での扱いを決める。本書の範囲は 2026-11-08 にユーザー確認済み（末尾「確認結果」）。各機能は `specs/<番号>-<名前>/` で起こす。

凡例:
- **MVP** = P0〜P4 で作る（「旧版の主要ユーザーフローが動く」状態）
- **P5** = 管理機能。MVP の後、優先度順に作る
- **後続** = 今回の範囲外（要望が出たら spec を起こす）
- **廃止** = 新版では作らない
- 「旧版の出処」は旧リポジトリ内のパス

## 前提（スコープを決める仮定）

1. **1 デプロイ = 1 企業**（旧版の決定を踏襲）。組織は 1 つだけ存在し、ロールは `owner` / `admin` / `member`。
2. **日本語のみ**。言語切替 UI・`locale` 列・中国語辞書は持たない。
3. **チーム（部門）と部門 KB・細かい共有付与は後続**（handoff「多团队高级功能」除外に従う）。MVP の KB は「個人 KB」と「全社 KB」の 2 種。
4. 能力包（`packages/cap-*`）、工作日历、共有リンク、PWA は handoff で除外済み。

## 1. 認証・アカウント

| 機能 | 区分 | 新版の実現 | 旧版の出処 |
|---|---|---|---|
| メール+パスワードで登録・ログイン・ログアウト | MVP | Better Auth | `src/app/api/auth/{register,login,logout}` |
| 「ログイン状態を保持」 | MVP | Better Auth セッション期限（remember） | `auth/remember` |
| メール検証（未検証はチャット不可のソフトゲート + バナー） | MVP | Better Auth emailVerification | `auth/email/*`, `components/auth/unverified-banner.tsx` |
| パスワード忘れ・リセット | MVP | Better Auth | `auth/password/{forgot,reset}`, `app/reset-password` |
| パスワード変更 | MVP | Better Auth | `auth/password/change`, `settings/password-change-form.tsx` |
| アクティブセッション一覧・個別/他デバイス/全デバイス サインアウト | MVP | Better Auth session API | `auth/sessions*`, `auth/revoke-all`, `settings/sessions-list.tsx` |
| ログイン失敗ロック・IP/メール単位レート制限 | MVP | Better Auth rateLimit + 失敗回数ロック（不足分は自作 hook） | `auth/login` |
| 表示名の変更 | MVP | Better Auth updateUser | `account/name` |
| CSRF（Origin 検査） | MVP | Better Auth の trustedOrigins + `proxy.ts` | `src/proxy.ts` |
| 設定画面の「現在の JWT をデコード表示」 | 廃止 | 開発者向け表示。セッション一覧で代替 | `settings-modal` securityJwt* |
| 言語設定の永続化 | 廃止 | 日本語のみ | `account/locale` |
| オンボーディングツアー | 後続 | 初期 UI が固まってから | `onboarding/onboarding-tour.tsx`, `account/onboarding` |
| SSO（IdP グループ連携） | 後続 | Better Auth の SSO プラグインで後付け可 | multi-tenancy.md |

## 2. チャット（知識アシスタント）

| 機能 | 区分 | 新版の実現 | 旧版の出処 |
|---|---|---|---|
| 質問 → エージェント検索 → 引用付き回答（ストリーム表示） | MVP | `create_agent` + tools、`messages`+`custom` ストリーム | `lib/agent/run.ts`, `chat/messages.tsx` |
| ツール実行の可視化（検索中・改写・リランク・評価…、所要時間・件数） | MVP | custom イベント → selector で旧 `ToolCall` へ写像 | `chat/tool-steps.tsx`, `agent-activity.tsx` |
| ツール表示形式（カード / タイムライン / ログ）・推論過程の表示切替 | MVP | 旧コンポーネント流用 | 設定「外観」 |
| 引用 `[n]` → 右パネルで原文（見出し・ページ・ハイライト） | MVP | 引用登録イベント + 生成後の `[n]` 実在検証 middleware | `lib/agent/citations.ts`, `sources/right-panel.tsx` |
| 引用スタイル（上付き / チップ / ピル） | MVP | 旧コンポーネント流用 | `answer-markdown.tsx` |
| 回答本文の Markdown・表・Mermaid・数式 | MVP | 旧コンポーネント流用 | `answer-markdown.tsx`, `sources/{mermaid-diagram,tex-text,html-table}.tsx` |
| 回答のコピー・トークン数・所要時間表示 | MVP | `usage_metadata` | `answer-footer.tsx` |
| 回答の再生成（最後のターン / 任意ターンから） | MVP | checkpoint から分岐 | `chat/route.ts` `regenerateFrom` |
| **質問を編集して再生成**（新規） | MVP | checkpoint 分岐（handoff 2-5） | — |
| 生成の取消 | MVP | run 取消（Redis フラグ + タスク cancel） | `chat/runs/[runId]/cancel` |
| 切断・リロード後に生成中の回答を続けて表示（Last-Event-ID 再接続） | MVP | 後台 run + Redis Stream | `chat/runs/[runId]/stream`, `lib/chat-stream.ts` |
| 回答不能の理由（資料なし / ステップ上限 / ツール失敗 / 生成失敗） | MVP | 構造化して保存（分析の知識ギャップ用） | `run.ts` `NoAnswerReason` |
| モデル選択（利用可能なモデルのみ選択可） | MVP | `init_chat_model` + モデル目録 | `chat/model-picker.tsx`, `api/models` |
| 検索範囲（全 KB / 特定 KB / アーカイブ含む） | MVP | `search` ツールの KB フィルタ | `chat/scope-picker.tsx` |
| チャットへの添付ファイル（その文書に絞って回答） | MVP | アップロード → 入庫 → `document_ids` フィルタ | `composer.tsx`, `attachmentDocIds` |
| 空状態の提案プロンプト・使い方ヒント | MVP | 旧コンポーネント流用（文言は ja 辞書） | `empty-state.tsx`, `tip-carousel.tsx` |
| 👍👎 フィードバック（低評価は理由タグ + コメント） | MVP | 保存 + Langfuse trace に紐付け（有効時） | `feedback-popover.tsx`, `threads/[id]/messages/[mid]/feedback` |
| エージェント挙動設定（最大ラウンド・top_k・候補数・再検索回数・評価閾値・引用必須・不明時は不明と答える・根拠検証） | MVP | run 入力 → middleware 設定 | `lib/agent/config.ts`, 設定「エージェント挙動」 |
| 並列ツール数 | MVP | LangGraph の並列ツール実行上限 | 同上 |
| 根拠検証と訂正再生成（verify/revise） | MVP | 忠実度チェック middleware（既定 OFF は旧版どおり） | `lib/agent/verify.ts` |
| 関連度評価 → クエリ改写 → 再検索（CRAG） | MVP | 評価・改写リトライ middleware | `lib/agent/grade.ts`, `tools.ts` |
| 多ホップ検索（決定論的 PRF） | 廃止 | エージェント自身の反復検索 + `get_outline`/`read_section` で代替。eval で劣る場合のみ復活 | `rag/app/retrieval/multihop.py` |
| 長い会話の要約 | MVP | SummarizationMiddleware（旧版は直近 8 ターン窓） | `chat/route.ts` |
| ユーザー単位レート制限・月次トークン上限 | MVP | FastAPI 依存関数 + Redis | `chat/route.ts` |
| **新ツール**: `keyword_search`（型番・条項番号の完全一致）, `list_documents`, `get_outline`, `read_section` | MVP | handoff 第 1 節 | — |
| 確認が要る操作で一時停止（interrupt / HITL） | 後続 | 現状ツールは読み取りのみで必要性が低い | — |
| スキル（明示選択でプロンプト・ツール・範囲を切替: 経営向け要約 等 5 種） | 後続 | 中身は日本語化して移植可能。MVP 後に要否判断 | `skills/`, `chat/skill-picker.tsx`, `api/skills` |
| Web 検索・Python 実行・SQL ツール | 廃止 | 旧版でも型定義のみ（未実装） | `lib/types.ts` ToolName |
| スレッド共有（org / 公開リンク）・`/s/[token]` 閲覧 | 後続 | handoff で除外 | `modals/share-modal.tsx`, `app/s/[token]` |

## 3. スレッド（サイドバー）

| 機能 | 区分 | 旧版の出処 |
|---|---|---|
| スレッド一覧（更新順・日付グループ）・新規・切替 | MVP | `sidebar/*`, `api/threads` |
| 名前変更・ピン留め・削除 | MVP | `threads/[id]` PATCH/DELETE, `thread-item.tsx` |
| サイドバー折りたたみ（レール表示）・モバイル下部シート | MVP | `sidebar-rail.tsx`, `app-shell.tsx` |
| スレッド検索（題名・質問・回答の本文） | 済（specs/022） | （旧版に無し） |

## 4. 知識ベース・文書

| 機能 | 区分 | 新版の実現 | 旧版の出処 |
|---|---|---|---|
| 個人 KB（自動作成）・全社 KB（admin が作成、全員閲覧） | MVP | KB 種別 `personal` / `org` | `rag/app/models.py` KnowledgeBase |
| KB の作成・名前変更・アーカイブ（検索対象外・閲覧可）・削除（ごみ箱経由）・復元 | MVP | | `api/kbs/*` |
| 部門 KB・部門間移動・KB への個別付与（user/team × read/write/manage） | 後続 | チーム機能と同時 | `kbs/[id]/{scope,grants}`, `api/teams` |
| アップロード（複数・フォルダ単位・ドラッグ&ドロップ）→ 進捗（解析/分块/嵌入/索引の段階表示） | MVP | Docling 管線、進捗は SSE | `uploads/uploads.tsx`, `api/upload`, `uploads/stream` |
| 内容ハッシュ重複排除（同じ内容は 1 回だけ解析） | MVP | `contents` 実体と `documents` 参照の分離 | document-lifecycle.md |
| 入庫失敗の自動リトライ・手動再試行・取消 | MVP | ジョブキュー | `uploads/[id]/{retry,cancel}` |
| 対応形式: PDF / Office（新旧）/ 画像 / Markdown / テキスト / CSV / JSON | MVP | Docling + LibreOffice 変換 | `rag/app/parsing/dispatch.py` |
| 大 PDF のページ窓分割解析 | MVP | | handoff 第 6 節 |
| 画像は表示のみ、図中テキストは VLM 説明として text 塊に | MVP（説明生成は設定で ON/OFF） | | handoff 第 1 節 |
| 文脈付与（Contextual Retrieval: 各塊に「この塊は〜」を付与） | MVP（P1。eval で効果確認） | 安価モデル + prompt caching | — |
| 親子チャンク（小塊で検索、章を返す） | MVP | HybridChunker | — |
| 文書一覧（KB 別・ページング・状態・チャンク数）・統計 | MVP | | `kb-library.tsx`, `documents/stats` |
| フォルダ（作成・名前変更・移動・削除・復元）、文書のフォルダ移動・一括移動 | MVP | 表示専用レイヤ（検索に影響しない） | `rag/app/routers/folders.py` |
| 一括削除 | MVP | | `documents/bulk-delete` |
| ごみ箱（30 日保持 → 自動 GC）・復元・完全削除（本人は 24h 以内、admin はいつでも） | MVP | | `library/trash-view.tsx`, document-lifecycle.md |
| 文書プレビュー: 原本（PDF）・Markdown 描画・表・Mermaid・数式・スプレッドシート・JSON・テキスト | MVP | 旧コンポーネント流用 | `components/documents/*` |
| 引用箇所へのジャンプ（ページ・範囲ハイライト） | MVP | | `documents/[id]/{span,layout}` |
| 文書の別 KB への移管 | P5 | admin のごみ箱救出と同時 | `documents/{id}/transfer` |

## 5. 設定（設定モーダル）

| タブ | 区分 | 備考 |
|---|---|---|
| モデル（既定モデル） | MVP | |
| データソース（KB 一覧・検索範囲の既定） | MVP | 旧「データソース」 |
| エージェント挙動 | MVP | §2 の各項目 |
| 外観（ダーク・アクセント色・ツール表示・密度・引用スタイル・推論表示） | MVP | ブラウザ保存 |
| セキュリティ（パスワード変更・セッション一覧） | MVP | JWT デコード表示は廃止 |
| アカウント（表示名・メール） | MVP | 言語欄は廃止 |
| ヘルプ（使い方モーダル） | MVP | `modals/help-modal.tsx` |
| ドキュメントサイト `/docs` | 後続 | 旧版の製品マニュアル |

## 6. 管理コンソール（P5）

| 機能 | 区分 | 旧版の出処 |
|---|---|---|
| 概要（件数・稼働状況） | P5 | `admin/admin-overview.tsx` |
| メンバー一覧・ロール変更・パスワード再設定・強制サインアウト・ロック解除 | P5（優先度 高） | `admin/members-table.tsx` |
| 退職処理（無効化 + 個人 KB をごみ箱へ）・再有効化 | P5 | `members/offboard*`, `reactivate` |
| LLM API キー（暗号化保存・末尾 4 桁表示・接続テスト・env 優先） | P5（優先度 高。MVP 中は env のみ） | `admin/llm-keys-panel.tsx` |
| モデル目録（既定・安価モデル・並び順・追加・提供中モデルとの突合） | P5（MVP 中は内置目録のみ） | `admin/model-catalog-panel.tsx` |
| KB 管理（全 KB 一覧・詳細・文書一覧） | P5 | `admin/kb-list.tsx`, `kb-detail.tsx` |
| 全社ごみ箱・選択文書の救出（移管） | P5 | `admin/org-trash.tsx` |
| 監査ログ（ログイン・質問・アップロード・削除…） | P5（記録は MVP から開始） | `admin/audit-log.tsx` |
| フィードバック（技術者への報告: 過程つきで読む・対応済みにする・診断用にコピー。specs/028） | 実装済み | 新規 |
| 分析: 利用量・品質（👍👎・回答不能率）・知識ギャップ（未解決クエリ）・1 件の診断ドリルダウン | P5 | `admin/analytics/*` |
| チーム管理・チーム別分析 | 後続 | `admin/teams-panel.tsx`, `analytics/teams-panel.tsx` |
| 工作日历 | 廃止（handoff 除外） | `admin/work-calendar` |
| 能力包の権限付与 | 廃止（handoff 除外） | `members/[id]/capabilities` |

## 7. 非機能（全期間）

| 項目 | 区分 | 備考 |
|---|---|---|
| 構造化 JSON ログ + `X-Request-Id` を Next → Python → ワーカーまで貫通 | MVP | 旧版踏襲 |
| `/healthz`（liveness）・`/readyz`（依存先） | MVP | |
| OpenTelemetry 計装 → Langfuse（任意） | MVP（計装）／任意（Langfuse） | decisions.md §8 |
| 文書内容をデータとして隔離（プロンプトインジェクション対策） | MVP | |
| ライセンス走査 CI | MVP（P0） | decisions.md §10 |
| 検索 eval（recall@k / MRR / nDCG）・回答 eval（引用再現率/精度・忠実度…） | P2 / P3 | handoff 第 5 節 |
| Playwright 視覚回帰（新旧比較） | P4 | handoff 第 2 節 7 |
| Storybook（旧 63 story を移植）+ a11y | P4 | |

## 確認結果（2026-11-08 ユーザー確認済み）

| # | 論点 | 結論 |
|---|---|---|
| 1 | KB の種類 | MVP は「個人 + 全社」のみ。部門 KB・個別付与は後続 |
| 2 | フォルダ | MVP に含める |
| 3 | スキル | 後続 |
| 4 | 多ホップ検索（PRF） | 廃止し、エージェントの目次閲覧ツールで代替（eval で劣れば復活） |
| 5 | 管理コンソール | P5。MVP 期間中は LLM キー = 環境変数、モデル目録 = 内置目録 |
