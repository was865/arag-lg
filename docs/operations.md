# 運用の手順

日々の起動・GPU 機・入庫と評価・止まったときの戻し方。決まりごと（何を守るか）は `AGENTS.md`、設計は `specs/`。

## 1. 開発機（Mac）で全体を起動する

```bash
cp .env.example .env   # 初回だけ。推論の構成 [A] オフライン / [B] 軽量 / [C] 混在 は .env.example の先頭を参照
make up                # compose で全体（postgres・qdrant・redis・api・worker・runner・web・mailpit）
```

| URL | 中身 |
|---|---|
| http://localhost:3100 | 画面（compose の `web`）。実際の質問はここで |
| http://localhost:8100 | API（`/healthz`・`/readyz`。readyz は推論の部品まで確かめる） |
| http://localhost:8025 | mailpit（確認・再設定のメール） |

- `.env` の値は画面・ログ・コミットに出さない。テスト用アカウントも `.env` にある。
- コードを変えたら作り直す: エージェント・プロンプト → `runner`、ルート → `api`、入庫 → `worker`、画面 → `web`。

  ```bash
  docker compose up -d --build --no-deps runner web
  ```

- 画面だけを速く回すなら `make dev-web`（ただし質問は 3100 からしか送れない。`AGENTS.md` 参照）。

## 2. GPU 機（Windows + RTX 4090、Docker Desktop + WSL2）

起動（GPU 機の作業ツリーで）:

```bash
docker compose -f compose.gpu.yaml --profile llm --profile vlm up -d
```

役割ごとに必要なものだけでもよい（例 `up -d tei-embed tei-rerank-ruri`）。`compose.gpu.yaml` の先頭のコメント参照。

| サービス | ポート | 確かめ方 |
|---|---|---|
| tei-embed | 8081 | `curl http://<GPU機>:8081/health` |
| tei-rerank-ruri | 8084 | `curl http://<GPU機>:8084/health` |
| docling-serve | 5001 | `curl http://<GPU機>:5001/health` |
| vllm（会話・文脈付与） | 8090 | `curl http://<GPU機>:8090/health`、`/v1/models` |
| vllm-vl（図の説明） | 8091 | 同上 |

### vLLM が起動しない・止まった

症状: `/health` が応答しない、`nvidia-smi` で GPU 100% のまま、ログが CUDA graph の取得で止まっている。原因はたいてい 2 つの vLLM の同時起動。

1. `vllm-vl`・`vllm` を止める（`docker compose -f compose.gpu.yaml stop vllm-vl vllm`）。
2. `vllm` だけ起動し、8090 の `/health` が 200 になるまで待つ（初回はモデルの取得で数分）。
3. `vllm-vl` を起動する。

`vllm-vl` の entrypoint は `vllm` の `/health` を待つので、普段は順番を気にしなくてよい（ログに `[wait]` が出る）。

### VRAM

24GB に TEI・docling・2 つの vLLM を同居させている。`nvidia-smi` で 24GB の近くまで使っていたら、`VLM_KV_BYTES`・`--kv-cache-memory-bytes` を増やさない。超えても OOM にならず、共有メモリに追い出されて静かに遅くなる。

### コードの更新

GPU 機では push しない。Mac で変更を push し、GPU 機は `git pull` する。GPU 機の作業は、そこで動く Claude Code（Remote Control）に頼める。

## 3. 入庫・再索引・評価

評価と CLI は、開発用ヘッダで認証する api（127.0.0.1:8101）を使う。

```bash
make eval-api
cd api
uv run python -m arag.cli ingest-dir ../eval/assets/agentic_rag_demo --kb <KB の ID>   # まとめて入庫
uv run python -m arag.cli reindex --all          # 解析し直さずに再索引（--dry-run で対象だけ）
uv run python -m arag.cli gc                     # ごみ箱の期限切れと孤立した内容を回収
uv run python -m arag.cli sync-payload           # Qdrant の payload を DB に合わせる
uv run python -m arag.eval run --suite agentic_rag_demo --variant default dbsf   # 検索の評価
uv run python -m arag.eval answer --suite agentic_rag_demo_ext                  # 回答の評価
cd .. && make eval-api-down
```

- 題集は `eval/suites/`、構成の違いは `eval/variants.yaml`。指標と閾値は `specs/004-retrieval`・`specs/005-agent`。
- 埋め込みのモデルや次元を変えたら `ARAG_QDRANT_COLLECTION` を別名にして再索引する（次元が違うと入庫が止まる）。

## 4. 回答を確かめる

- 「詳細」でエージェントの段階（検索・読む・計算・見直し）と、末尾の「システムの処理」（ツールの必須化・回数の上限・履歴の省略・回答の整形・要約）を見る。
- 数字は元の文書で確かめる（例 `eval/assets/harukaze_mix/docs/`。xlsx は openpyxl、pptx は python-pptx）。出典番号が付いていても、その資料に数字が無いことがある。

## 5. よくある詰まり

| 症状 | 原因と対処 |
|---|---|
| 変えたはずのエージェントの動きが変わらない | `runner` を作り直していない。`docker compose up -d --build --no-deps runner` |
| 開発サーバから質問が送れない | 送信元を 3100 に限っている。3100 で確かめる |
| 回答がすぐ失敗する・モデルが切り替わる | GPU 機の vLLM が落ちている、または外部 API の残高切れ（402）。「詳細」のモデル切り替えのステップに理由が出る |
| 入庫が進まない | `worker` のログ、api の `/readyz`、docling-serve（5001）の `/health` を見る |
| `make gen-check` が CI で落ちる | API を変えて `make gen` をしていない |
