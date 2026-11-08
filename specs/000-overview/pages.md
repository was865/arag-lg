# 000 画面一覧

旧版はほぼ全機能を 1 画面（`/rag` の `Workspace`）に集約し、本体部分を `chat` / `library` / `trash` に切り替え、ログイン・設定・共有などをモーダルで出していた。新版も**見た目と導線は旧版のまま**にする。変更は URL まわりだけ（下表の「変更」列）。

UI 仕様の基準: Design System（https://claude.ai/artifact/QaGvknVyaiM1TwBwAHuNrY ）。収録外の画面（知識ベース・文書プレビュー・管理・設定各タブ・アップロードキュー）は旧ソースを直接参照する。

## 1. ルート（URL）

| URL | 内容 | 区分 | 旧版 | 変更 |
|---|---|---|---|---|
| `/` | ワークスペース（新規チャットの空状態） | MVP | `/` → `/rag` へリダイレクト | `/agents` が無くなるため `/` を本体にする |
| `/c/[threadId]` | ワークスペース（既存スレッド表示） | MVP | 無し（クライアント状態のみ） | **追加**: リロード後に同じスレッドと生成中の回答へ戻るため |
| `/library` ・ `/library/[kbId]` | ワークスペース本体を知識ベース表示に | MVP | `mainView = library`（URL 無し） | **追加**: 戻る/進むと再読込に対応（表示は旧版のまま） |
| `/trash` | ワークスペース本体をごみ箱表示に | MVP | `mainView = trash` | 同上 |
| `/reset-password?token=` | パスワード再設定 | MVP | 同じ | Better Auth のトークン形式に合わせる |
| `/verify-email?token=` | メール検証の結果 | MVP | 同じ | 同上 |
| `/admin` | 管理: 概要 | P5 | 同じ | |
| `/admin/analytics` ・ `/admin/analytics/threads/[id]` | 管理: 分析・診断ドリルダウン | P5 | 同じ | |
| `/admin/members` | 管理: メンバー | P5 | 同じ | |
| `/admin/kbs` ・ `/admin/kbs/[id]` | 管理: KB 一覧・詳細 | P5 | 同じ | |
| `/admin/trash` | 管理: 全社ごみ箱 | P5 | 同じ | |
| `/admin/audit` | 管理: 監査ログ | P5 | 同じ | |
| `/admin/llm-keys` | 管理: LLM API キー | P5 | 同じ | |
| `/admin/models` | 管理: モデル目録 | P5 | 同じ | |
| `/admin/teams` | 管理: チーム | 後続 | 同じ | |
| `/docs/[[...slug]]` | 製品マニュアル | 後続 | 同じ | |
| `/agents/**` ・ `/s/[token]` ・ `/admin/work-calendar` | 能力包・共有閲覧・工作日历 | 廃止 | — | handoff で除外 |

未ログインで保護 URL を開いた場合は、旧版どおり**同じ画面の上にログインモーダル**を出す（専用 `/login` ページは作らない）。

## 2. ワークスペースの構成要素

| 領域 | 構成 | 旧コンポーネント（流用元） |
|---|---|---|
| 外枠 | 3 カラム（サイドバー / 本体 / 右パネル）、ブレークポイント 769 / 1181px、モバイルは下部シート | `shell/app-shell.tsx`, `workspace/workspace.tsx` |
| サイドバー | ブランド・新規ボタン・スレッド一覧（ピン留め/日付グループ）・知識ベース入口・ごみ箱入口・フッター（ユーザーメニュー・テーマ切替・管理入口）・レール表示 | `sidebar/*` |
| 本体: チャット | 空状態（提案プロンプト・ヒントカルーセル）→ メッセージ列（ユーザー吹き出し・ツール活動・回答本文・回答フッター）→ コンポーザ（添付・モデル選択・範囲選択・送信/停止） | `chat/*` |
| 本体: 知識ベース | KB 切替・フォルダツリー・文書一覧（状態・チャンク数）・アップロードキュー・一括操作 | `library/kb-library.tsx`, `library/folder-picker.tsx`, `uploads/uploads.tsx` |
| 本体: ごみ箱 | 削除済み文書の一覧・復元・完全削除・残り保持日数 | `library/trash-view.tsx` |
| 右パネル | 引用元（原文セクション・ハイライト・スコア）／文書プレビュー（PDF・Markdown・表・Mermaid・数式・スプレッドシート・JSON・テキスト）、幅リサイズ | `sources/*`, `documents/*` |
| トースト | 情報 / 成功 / エラー | `feedback/toast-*` |
| 未検証バナー | メール未検証時に上部表示・再送ボタン | `auth/unverified-banner.tsx` |

## 3. モーダル・ポップオーバー

| 名称 | 区分 | 内容 | 旧コンポーネント |
|---|---|---|---|
| ログイン / 登録 / パスワード忘れ | MVP | ログインカード（タブ切替） | `auth/login.tsx`, `auth/auth-chrome.tsx` |
| 設定 | MVP | タブ: モデル / データソース / エージェント挙動 / 外観 / セキュリティ / アカウント（言語欄・JWT 表示は削除） | `modals/settings-modal.tsx`, `settings/*` |
| ヘルプ | MVP | 使い方 | `modals/help-modal.tsx` |
| 確認ダイアログ | MVP | 削除などの確認 | `modals/confirm-modal.tsx` |
| フィードバック | MVP | 低評価の理由タグ + コメント | `chat/feedback-popover.tsx` |
| モデル選択 / 範囲選択 | MVP | ポップオーバー | `chat/model-picker.tsx`, `chat/scope-picker.tsx` |
| フォルダ選択（移動先） | MVP | | `library/folder-picker.tsx` |
| スキル選択 | 後続 | | `chat/skill-picker.tsx` |
| 共有 | 後続 | | `modals/share-modal.tsx` |
| オンボーディングツアー | 後続 | | `onboarding/onboarding-tour.tsx` |
| 工作日历 | 廃止 | | `modals/work-calendar-modal.tsx` |

## 4. 視覚回帰の対象（P4、Playwright で新旧比較）

ログイン / 空状態 / 対話中（ツール活動展開・ストリーム中）/ 引用側パネル / 知識ベース（フォルダ + アップロード中）/ 文書プレビュー（PDF・表・Mermaid）/ ごみ箱 / 設定（各タブ）/ 管理概要。各画面をライト・ダーク × デスクトップ・モバイルで撮る。

## 5. 旧版からの修正（handoff 第 2 節 9 の再掲。移植時に直す）

- 共通 `Button`（primary / danger / secondary / icon / text link）と入力欄を抽出し、各所の直書き Tailwind を置換。
- 角丸を段階値へ統一（確認ダイアログのボタン 9px → `radius-8`、ログインカードとモバイル下部シート 18px → `radius-16`）。
- 直書き色 `#B83A1F`（24 ファイル）→ `danger-ink` トークン。ログインエラー枠の `#F0CFC4` / `#FDF0EC` もトークン化。
- コントラスト（WCAG AA）: `muted-2` は補助表示のみに限定、`muted` の小さい文字を調整、主ボタンの地色を濃く、ダーク時の `danger-ink` を明るく。変更は Design System にも反映する。
