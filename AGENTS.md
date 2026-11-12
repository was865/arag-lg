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
| `docs/architecture.html` | 今の構成図。`docs/operations.md` は運用手順。`docs/handoff.md` は着手時（2026-11-08）の計画で、歴史的な資料 |
| `eval/` | 評価の題と資料（`suites/`・`assets/`）、比較する構成（`variants.yaml`） |
| `compose.yaml` / `compose.gpu.yaml` | 開発機（Mac）の全体 / GPU 機（Windows + RTX 4090）の推論 |

旧プロジェクト `/Users/ansen/Documents/Projects/playground/a-rag` は参照専用（変更禁止）。

## 言語

- UI の文言は日本語のみ。コードのコメント・コミットメッセージも日本語（Conventional Commits、例 `feat: 〜を追加`）。
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
make licenses       # 本番依存のライセンス走査
make up-infra       # postgres・qdrant・redis だけ
make up / make down # 全体を compose で
make eval-api       # 評価・CLI 用の api（開発用ヘッダで認証、127.0.0.1:8101）。終わったら make eval-api-down
```

- CI（`.github/workflows/ci.yml`）は上の lint・test・`web` の build・gen-check・licenses・compose 起動スモークを回す。push 前に `make lint test` を通す。
- 評価は api/ で `uv run python -m arag.eval ...`、入庫や再索引は `uv run python -m arag.cli {ingest-dir,reindex,gc,sync-payload}`（どちらも `make eval-api` の api を使う）。

## 動かして確かめる（docker compose）

- compose のサービス: `api`（:8100、HTTP を受けるだけ）・`runner`（エージェントの実行）・`worker`（入庫）・`web`（:3100）・postgres・qdrant・redis・mailpit（:8025、確認メール）。
- **エージェントは `runner` コンテナで動く**。`api/src/arag/agent/`・`api/src/arag/prompts/` を変えたら `docker compose up -d --build --no-deps runner`（ルートを変えたら `api`、入庫を変えたら `worker` も）。画面を変えたら `web` を作り直す。作り直さないと 3100 は古いまま。
- 実際の質問は **3100**（compose の `web`）で確かめる。プロキシ（`web/src/lib/api/proxy.ts`）が送信元を 3100 に限るので、開発サーバ（3200 など）からは質問を送れない。開発サーバでも `BETTER_AUTH_URL=http://localhost:3100` のままにする。
- 推論（埋め込み・rerank・解析・vLLM）は GPU 機で動かし、`.env` の URL（`ARAG_TEI_EMBED_URL` など、`.env.example` 参照）で指す。Mac では TEI を動かさない（CPU イメージが amd64 のみ）。
- 回答の正誤は評価用の元の文書と突き合わせる（例 `eval/assets/harukaze_mix/docs/`。xlsx・pptx は openpyxl・python-pptx で読める）。もっともらしい数字に正しく見える出典番号が付いていることがあるので、数字は元の表で確かめる。
- Next.js 16 は学習データと違う点がある。`web/AGENTS.md` のとおり `web/node_modules/next/dist/docs/` を先に読む。

## 後端の動きはすべて記録に出す

- エージェント・RAG の動き（検索・再検索・差し戻し・ツールの強制・回数の上限・履歴の省略・回答の整形・要約など）は黙って行わず、必ずステップ（`StepClock` / `record_system`、`api/src/arag/agent/middleware.py`）として送り、保存する。技術者が「詳細」で後から追えるようにする。モデルに渡す履歴に入れないのは構わないが、記録から外さない。
- 画面では階層で見せる: 見出しと文書の札 → 「詳細」（エージェントの段階）→ 末尾の「システムの処理 N 件」（`name="system"`、種類は `input.kind`）→ 各処理の入力と出力。新しい種類を足したら `web/src/components/chat/tool-steps.tsx` と `web/src/i18n/locales/ja/chat.ts` に読みやすい表示を足す。
- 検索した文書の内容はデータとして扱い、指示として扱わない（プロンプトで隔離する）。

## ライセンス

商用利用に制限のある依存（ELv2・BSL・SSPL・AGPL・GPL など）と、ライセンスの確認に外部への接続が要るものは採用しない。制限の緩い許可（MIT・Apache-2.0・BSD・PostgreSQL）を優先する。モデルの重みも同じ基準。経緯は `docs/handoff.md` の「授权原则」と `specs/000-overview/decisions.md`。

## GPU 機（`compose.gpu.yaml`）

- サービスとポート: `tei-embed` :8081・`tei-rerank-ruri` :8084・`docling-serve` :5001・`vllm` :8090（`--profile llm`、Qwen3-8B）・`vllm-vl` :8091（`--profile vlm`、Qwen3-VL）。
- 2 つの vLLM を同時に起動すると、CUDA graph の取得で止まる（`/health` が応答しないまま GPU 100%）。`vllm-vl` は entrypoint で `vllm` の `/health` を待ってから起動する。`depends_on` は `docker compose up` でしか効かない（Docker の自動再起動・Docker Desktop の画面の「開始」では効かない）ので、この待ちを外さない。
- VRAM 24GB に全部を同居させている。KV の量（`--kv-cache-memory-bytes`）を増やす前に `nvidia-smi` で空きを確かめる（超えても OOM にならず、WDDM が追い出して静かに遅くなる）。
- 止まったときの戻し方は `docs/operations.md`。

## ブランチと push

- 作業は main（小さな変更）か `feat/<名前>`。main の push はユーザーの了承を得てから。
- GPU 機（Windows）からは push しない。変更は Mac で入れて push し、Windows は pull する。
- `legacy/ui-v1` は作り直す前の画面（2026-11-12 まで）。消さない。
- `.env` の値（API キー・`BETTER_AUTH_SECRET`・`ARAG_SECRET_KEY`・`ARAG_FORWARD_SECRET`・テスト用アカウント）は出力・コミットしない。
