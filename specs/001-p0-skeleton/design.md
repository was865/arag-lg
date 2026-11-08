# 001 P0 骨格 — 設計

## ディレクトリ

```
api/
  pyproject.toml / uv.lock      Python 3.13、パッケージ名 arag
  src/arag/
    main.py                     create_app()（アプリファクトリ。依存を差し替えてテストする）
    settings.py                 pydantic-settings（環境変数 ARAG_*）
    logging.py                  JSON ログ（structlog）+ request_id の contextvar
    middleware.py               RequestIdMiddleware
    health.py                   /healthz・/readyz と依存チェッカ
    openapi_export.py           `python -m arag.openapi_export` → api/openapi.json
  alembic/ + alembic.ini        P1 以降のマイグレーション置き場（P0 は空）
  tests/
  Dockerfile
web/
  Next.js 16（App Router, src/, Tailwind 4）
  src/lib/api/schema.d.ts       openapi-typescript の生成物（コミットする）
  src/lib/api/client.ts         openapi-fetch のクライアント（サーバ側専用）
  src/app/api/healthz/route.ts
  Dockerfile（output: standalone）
compose.yaml                    既定: postgres / qdrant / redis / api / web、profile cpu: tei-embed / tei-rerank
compose.gpu.yaml                GPU 機用: tei-embed / tei-rerank（89-1.9.4）
.env.example
Makefile                        setup / dev / test / lint / gen / up
scripts/check_licenses.py       pip-licenses と pnpm licenses の結果を許可リストで判定
.github/workflows/ci.yml
```

## readiness チェック

```python
class Check(Protocol):
    name: str
    async def __call__(self) -> bool: ...   # 失敗は例外か False
```

- `build_checks(settings)` が Postgres（psycopg で `SELECT 1`）・Qdrant（`GET /readyz`）・Redis（`PING`）・TEI（`GET /health`）を返す。TEI の URL が空なら `skipped`。
- `/readyz` は `asyncio.wait_for` で各チェックを並行実行（タイムアウト `ARAG_READY_TIMEOUT_SEC`、既定 2.0）。
- 応答: `{"status": "ok"|"unavailable", "checks": {"postgres": "ok"|"fail"|"skipped", ...}}`。例外内容はログのみ。
- テストは `create_app(checks=[...])` に偽チェックを渡す（外部サービス不要）。

## ログと request id

- structlog の JSON レンダラ。`contextvars` に `request_id` を束縛し、全ログ行に自動で入る。uvicorn のアクセスログも同じ形式へ流す。
- 受信 `X-Request-Id` は 128 文字以内の `[A-Za-z0-9._-]` のみ採用（ログ注入対策）。それ以外は新規 UUID。

## 設定（環境変数）

| 変数 | 既定 | 用途 |
|---|---|---|
| `ARAG_DATABASE_URL` | `postgresql://arag:arag@localhost:5433/arag` | Postgres |
| `ARAG_QDRANT_URL` | `http://localhost:6343` | Qdrant |
| `ARAG_REDIS_URL` | `redis://localhost:6380/0` | Redis / Valkey |
| `ARAG_TEI_EMBED_URL` / `ARAG_TEI_RERANK_URL` | 空（= skipped） | TEI。Mac では GPU 機の `http://<host>:8081` 等 |
| `ARAG_READY_TIMEOUT_SEC` | `2.0` | readiness の各チェック上限 |
| `ARAG_LOG_LEVEL` | `INFO` | |
| `API_BASE_URL`（web） | `http://localhost:8100` | Next サーバ側から API への URL |

## コンテナ

ホスト側ポートは旧版 a-rag の開発スタック（5432 / 6333 / 6379 / 8000 / 3000）と同時起動できるようずらす（新旧の画面比較のため）。各ポートは `POSTGRES_PORT` 等の環境変数で変更可。

| サービス | イメージ | ポート | ヘルスチェック |
|---|---|---|---|
| postgres | `postgres:18` | 5433 | `pg_isready` |
| qdrant | `qdrant/qdrant:v1.20.0` | 6343 / 6344 | `/readyz`（bash の `/dev/tcp` で叩く。イメージに curl が無いため） |
| redis | `${REDIS_IMAGE:-redis:8.10.3}` | 6380 | `redis-cli ping`（Valkey は `valkey-cli` を `REDIS_CLI` で切替） |
| api | ローカル build | 8100 | `/healthz` |
| web | ローカル build | 3100 | `/api/healthz` |
| tei-embed（profile cpu） | `ghcr.io/huggingface/text-embeddings-inference:cpu-1.9.4` | 8081 | `/health` |
| tei-rerank（profile cpu） | 同上 | 8082 | `/health` |

- CI の TEI モデルは小さいもの（embed: 多言語の小型 `intfloat/multilingual-e5-small`、rerank: `BAAI/bge-reranker-base`）で疎通のみ確認。本番・GPU 機は `BAAI/bge-m3` / `BAAI/bge-reranker-v2-m3`。
- GPU 機（Windows）: Docker Desktop + WSL2。`docker compose -f compose.gpu.yaml up -d`。モデルキャッシュは名前付きボリューム。

## OpenAPI → TS

1. `uv run python -m arag.openapi_export` が `api/openapi.json` を書く（キー順固定）。
2. `pnpm -C web gen:api` が `openapi-typescript ../api/openapi.json -o src/lib/api/schema.d.ts`。
3. CI は両方を再生成し `git diff --exit-code`。

## ライセンス走査

- Python: `uv run --with pip-licenses pip-licenses --format=json`（本番依存のみ = `uv sync --no-dev` 環境）。
- JS: `pnpm licenses list --prod --json`。
- `scripts/check_licenses.py` が両方を読み、禁止パターン（`AGPL`, `GPL`（`LGPL` は除く）, `SSPL`, `BUSL`, `Elastic`）に当たり、かつ許可リスト（`psycopg`, `psycopg-binary` ほか licenses.md 記載分）に無いものがあれば失敗。`UNKNOWN` は警告に留め一覧を出す。
