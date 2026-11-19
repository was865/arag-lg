# AGENTS.md

社内ナレッジ検索エージェント ARag を LangChain / LangGraph で作り直したもの（日本語版のみ）。
AI エージェント（Claude Code・Codex など）と人の両方が最初に読む、作業の決まりと地図。
Claude 専用の補足は `CLAUDE.md`、運用の手順は `docs/operations.md`。

## 地図

| 場所 | 中身 |
|---|---|
| `api/` | Python（FastAPI + LangChain/LangGraph、uv）。`src/arag/` の主な区分: `agent/`（エージェント・middleware・runner）、`search/`（Qdrant の混合検索 + rerank）、`ingest/`（Docling → 分块 → 文脈付与 → 索引、worker）、`eval/`（評価 CLI）、`prompts/`、`auth/`、`kb/` |
| `web/` | Next.js 16（画面 + Better Auth、pnpm）。`src/components/chat/` が会話、`src/i18n/locales/ja/` が文言 |
| `specs/` | 仕様（SDD）。一覧は `specs/README.md`、全体像（機能・画面・API・データモデル・採否・ライセンス台帳）は `000-overview/` |
| `docs/architecture.html` | 今の構成図。回答の流れは `docs/agent-graph.md`（`make graph` がコードから書き出す。手で直さない）。`docs/operations.md` は運用手順。`docs/handoff.md` は着手時（2026-11-08）の計画で、歴史的な資料 |
| `eval/` | 評価の題と資料（`suites/`・`assets/`）、比較する構成（`variants.yaml`） |
| `compose.yaml` / `compose.gpu.yaml` | 開発機（Mac）の全体 / GPU 機（Windows + RTX 4090）の推論 |

旧プロジェクト `/Users/ansen/Documents/Projects/playground/a-rag` は参照専用（変更禁止）。

## 言語

- UI の文言は日本語のみ。コードのコメント・コミットメッセージも日本語（Conventional Commits、例 `feat: 〜を追加`）。
- 文言の置き場: UI は日本語だけなので、すべてを辞書（`web/src/i18n/locales/ja/`）に移す必要は無い。辞書に置くのは、2 つ以上の場所で使う文言と、すでに `useT()` を使っている部品（会話・出典・サイドバー・アップロード・トースト）の文言。1 つの画面だけの文言（管理画面・ライブラリ・解析の確認など）は部品に直接書いてよい。1 つの部品の中で両方を混ぜない。
- 検索と回答は日本語に最適化するが、英語の文書・質問、言語をまたぐ検索も動くこと（`specs/019`）。

## 進め方（SDD + TDD）

- 機能は先に `specs/<番号>-<名前>/{requirements,design,tasks}.md` を書く（requirements は EARS「〜のとき、システムは〜する」）。仕様と実装は同じ変更に入れ、`tasks.md` の項目に印を付ける。
- 先に失敗するテストを書く。エージェント・middleware は偽のモデル（台本どおりに答える）で分岐を確かめる（`api/tests/test_agent_graph.py`）。
- 依存を足したら `specs/000-overview/licenses.md` に追記し、`make licenses` を通す。

## コマンド（`Makefile`）

```bash
make setup          # 依存の導入（api: uv、web: pnpm）
make test           # api の pytest・scripts・web の vitest
make lint           # ruff・mypy・eslint・tsc
make gen            # API を変えたら: OpenAPI → web の TS 型（CI の gen-check が一致を確かめる）
make graph          # 回答の流れ（api/src/arag/agent/flow.py）を変えたら: 図と画面用の JSON を書き出す（CI の graph-check）
make licenses       # 本番依存のライセンス走査
make up-infra       # postgres・qdrant・redis だけ
make up / make down # 全体を compose で（開発構成。ソースを載せ、保存で反映）
make up-prod        # 本番と同じ構成（build した image）で確かめる
make eval-api       # 評価・CLI 用の api（開発用ヘッダで認証、127.0.0.1:8101）。終わったら make eval-api-down
```

- CI（`.github/workflows/ci.yml`）は上の lint・test・`web` の build・gen-check・licenses・compose 起動スモークを回す。push 前に `make lint test` を通す。
- 評価は api/ で `uv run python -m arag.eval ...`、入庫や再索引は `uv run python -m arag.cli {ingest-dir,reindex,gc,sync-payload}`（どちらも `make eval-api` の api を使う）。

## 動かして確かめる（docker compose）

- compose のサービス: `api`（:8100、HTTP を受けるだけ）・`runner`（エージェントの実行）・`worker`（入庫）・`web`（:3100）・postgres・qdrant・redis・mailpit（:8025、確認メール）。
- **ふだんは開発構成**（`compose.override.yaml`。素の `docker compose` が自動で読む）。ソースを容器に載せ、保存すると反映する: `web` は `next dev`、`api` は `--reload`、`runner`（エージェントの実行）・`worker`（入庫）は watchfiles で再起動（実行中の回答・入庫は切れる）。作り直し（`--build`）は依存を変えたときだけ。依存を変えたら `make up`（node_modules を作り直す）。
- **本番の構成で確かめる**ときは `make up-prod`（`docker compose -f compose.yaml`。上書きを読まない）。build の失敗・表示の差・速さは開発構成では分からない。画面の大きな変更は push 前に一度ここで見る。CI の compose スモークもこの構成。戻すときは `make up`。
- 実際の質問は **3100**（compose の `web`）で確かめる。プロキシ（`web/src/lib/api/proxy.ts`）が送信元を 3100 に限るので、ホストで別に開いた開発サーバ（3200 など）からは質問を送れない。
- 推論（埋め込み・rerank・解析・vLLM）は GPU 機で動かし、`.env` の URL（`ARAG_TEI_EMBED_URL` など、`.env.example` 参照）で指す。Mac では TEI を動かさない（CPU イメージが amd64 のみ）。
- 回答の正誤は評価用の元の文書と突き合わせる（例 `eval/assets/harukaze_mix/docs/`。xlsx・pptx は openpyxl・python-pptx で読める）。もっともらしい数字に正しく見える出典番号が付いていることがあるので、数字は元の表で確かめる。
- Next.js 16 は学習データと違う点がある。`web/AGENTS.md` のとおり `web/node_modules/next/dist/docs/` を先に読む。

## 画面の部品（`web/src/components/ui/`）

- 部品の見本は **http://localhost:3100/dev/ui**（開発構成のときだけ。ライトとダークを並べる）。新しい部品や形を足したら見本にも足す。Storybook は入れない（見本はアプリの Tailwind・テーマ・i18n をそのまま使えるこの 1 ページで足りる）。
- 画面を作る前に `ui/` と見本を見る。あるものを使い、同じ見た目の className を書き写さない。主なもの:
  - 面: `Card`（tone: surface・sunken・raised・linked）、文字列だけなら class の `card`・`card-sunken`・`card-raised`
  - 区切りの小見出し: class の `eyebrow`。処理中の輪: `Spinner`（画面の読み込みは `Skeleton`）。形式の札: `FileTile`
  - 印とカードが互いに光る連動: `ui/link-marks`（`data-on` を切り替えるだけ）
  - ボタン `Button`/`IconButton`、札 `Badge`、入力 `Input`/`SearchField`、切り替え `Segmented`/`Tabs`、一覧 `ListGroup`、メニュー `Menu`、ダイアログ `Dialog`
- 決まりは ESLint で止める（`web/eslint.config.mjs` の `UI_PARTS`・`UI_LOOKS`）。手書きのモーダル・メニュー・輪・小見出し・面・形式の札は lint で落ちる。わざと違う見た目（警告の面・強調の札など）は色を変えて書く。
- 2 つ以上の画面で同じ形が出たら `ui/` に移す。見た目の組み合わせは CSS（`globals.css` の `@utility`）、振る舞いを持つものは部品にする。表示の整形（頁 `pageLabel`・見出し `headingCrumb`・日付・大きさ）は `web/src/lib/` の純関数にしてテストする。
- class の定数（`tabsTriggerClass` など）を export するファイルには `"use client"` を付けない。付けるとサーバーの描画でその値が null になり、見た目が崩れる（hydration の不一致）。フォルダに分けた部品は入口のファイルだけに付ける。
- 色の使い分け: 朱（accent）は引用の印・送信・選択中だけ。警告は `danger`。文言は日本語（`web/src/i18n/locales/ja/`）。

## 後端の動きはすべて記録に出す

- エージェント・RAG の動き（検索・再検索・差し戻し・ツールの強制・回数の上限・履歴の省略・回答の整形・要約など）は黙って行わず、必ずステップ（`StepClock` / `record_system`、`api/src/arag/agent/middleware.py`）として送り、保存する。技術者が「詳細」で後から追えるようにする。モデルに渡す履歴に入れないのは構わないが、記録から外さない。
- 画面では階層で見せる: 見出しと文書の札 → 「詳細」（グラフの実行経路と、その段階ごとのステップ）→ 各段階の中のシステムの処理（`name="system"`、種類は `input.kind`。淡い行）→ 各処理の入力と出力。段階の区切りと時間は上の経路と同じにする（`tool-steps/staged.tsx`）。経路の無い古い回答は、末尾の「システムの処理 N 件」に畳む。新しい種類を足したら `web/src/components/chat/tool-steps/`（システムの処理は `system-fields.tsx`、ツールの入出力は `step-input.tsx`・`step-output.tsx`）と `web/src/i18n/locales/ja/chat.ts` に読みやすい表示を足す。
- 検索した文書の内容はデータとして扱い、指示として扱わない（プロンプトで隔離する）。

## ライセンス

商用利用に制限のある依存（ELv2・BSL・SSPL・AGPL・GPL など）と、ライセンスの確認に外部への接続が要るものは採用しない。制限の緩い許可（MIT・Apache-2.0・BSD・PostgreSQL）を優先する。モデルの重みも同じ基準。経緯は `docs/handoff.md` の「授权原则」と `specs/000-overview/decisions.md`。

## GPU 機（`compose.gpu.yaml`）

- サービスとポート: `tei-embed` :8081・`tei-rerank-ruri` :8084・`docling-serve` :5001・`gemma` :8093（`--profile llm`。Gemma 4 12B が会話・補助・文脈付与・図の説明を 1 つで兼ねる。2026-11-13 から既定）。
- 以前の構成（`vllm` :8090 Qwen3-8B は `--profile qwen`、`vllm-vl` :8091 Qwen3-VL は `--profile qwen-vl`）は比較用。`gemma` と同時には載らない（24GB を超える）。この 2 つを同時に起動すると CUDA graph の取得で止まるので、`vllm-vl` は entrypoint で `vllm` の `/health` を待つ（`depends_on` は `docker compose up` でしか効かない。この待ちを外さない）。
- モデルを替えるときは harukaze_mix（69 題）で比べてから決める（`eval/.reports/`、手順は `docs/operations.md`）。Qwen3.8-27B の INT4 は 24GB では余裕が無く、長い入力で止まったので見送った（2026-11-12）。
- VRAM 24GB に全部を同居させている。KV の量（`--kv-cache-memory-bytes`）を増やす前に `nvidia-smi` で空きを確かめる（超えても OOM にならず、WDDM が追い出して静かに遅くなる）。
- 止まったときの戻し方は `docs/operations.md`。

## ブランチと push

- 作業は main（小さな変更）か `feat/<名前>`。main の push はユーザーの了承を得てから。
- GPU 機（Windows）からは push しない。変更は Mac で入れて push し、Windows は pull する。
- `legacy/ui-v1` は作り直す前の画面（2026-11-12 まで）。消さない。
- `.env` の値（API キー・`BETTER_AUTH_SECRET`・`ARAG_SECRET_KEY`・`ARAG_FORWARD_SECRET`・テスト用アカウント）は出力・コミットしない。
