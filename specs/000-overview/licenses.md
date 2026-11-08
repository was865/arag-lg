# 依存ライセンス台帳

新しい依存を加えるたびに 1 行追記する（`docs/handoff.md` 授权原则）。判断の経緯は `decisions.md`。CI のライセンス走査（`pip-licenses` / `pnpm licenses list`）はこの台帳と突き合わせる。

| コンポーネント | 種別 | 版 | ライセンス | 確認日 | 出典 |
|---|---|---|---|---|---|
| langchain / langchain-core | Python | 1.4.9 / 1.7.6 | MIT | 2026-11-08 | https://pypi.org/project/langchain/ |
| langgraph / langgraph-checkpoint-postgres | Python | 1.2.20 / 3.2.0 | MIT | 2026-11-08 | https://pypi.org/project/langgraph/ |
| langchain-openai / -anthropic / -deepseek | Python | 1.7.4 / 1.7.10 / 1.1.1 | MIT | 2026-11-08 | https://pypi.org/project/langchain-openai/ |
| qdrant-client | Python | 1.20.0 | Apache-2.0 | 2026-11-08 | https://pypi.org/project/qdrant-client/ |
| docling / docling-core | Python | 2.148.0 / 2.106.0 | MIT | 2026-11-08 | https://github.com/docling-project/docling |
| SudachiPy / SudachiDict-core | Python | 0.7.0 / 20261015 | Apache-2.0 | 2026-11-08 | https://pypi.org/project/SudachiPy/ |
| fastapi / pydantic | Python | 0.162.2 / 2.14.3 | MIT | 2026-11-08 | https://pypi.org/project/fastapi/ |
| sqlalchemy / alembic | Python | 2.1.8 / 1.20.1 | MIT | 2026-11-08 | https://pypi.org/project/SQLAlchemy/ |
| uvicorn / sse-starlette | Python | 0.54.0 / 3.7.0 | BSD-3-Clause | 2026-11-08 | https://pypi.org/project/uvicorn/ |
| redis-py / arq | Python | 8.1.0 / 0.28.0 | MIT | 2026-11-08 | https://pypi.org/project/redis/ |
| PyJWT | Python | 2.15.1 | MIT | 2026-11-08 | https://pypi.org/project/PyJWT/ |
| opentelemetry-sdk | Python | 1.45.2 | Apache-2.0 | 2026-11-08 | https://pypi.org/project/opentelemetry-sdk/ |
| langfuse（SDK、任意） | Python | 5.2.0 | MIT | 2026-11-08 | https://pypi.org/project/langfuse/ |
| psycopg / psycopg-binary（LGPL：改変なし・ライブラリ利用のみ。decisions.md §12 で許可） | Python | 3.3.8 | LGPL-3.0-only | 2026-11-08 | https://pypi.org/project/psycopg/ |
| pydantic-settings | Python | 2.16.2 | MIT | 2026-11-08 | https://pypi.org/project/pydantic-settings/ |
| structlog | Python | 26.1.0 | MIT OR Apache-2.0 | 2026-11-08 | https://pypi.org/project/structlog/ |
| httpx | Python | 0.28.1 | BSD-3-Clause | 2026-11-08 | https://pypi.org/project/httpx/ |
| certifi（推移的依存） | Python | 2026.10.23 | MPL-2.0（ファイル単位の弱いコピーレフト。改変しないため影響なし） | 2026-11-08 | https://pypi.org/project/certifi/ |
| ruff / mypy / pytest / pytest-asyncio（開発のみ） | Python | 0.17.4 / 2.4.1 / 9.2.0 / 1.4.1 | MIT / MIT / MIT / Apache-2.0 | 2026-11-08 | https://pypi.org/project/ruff/ |
| server-only | npm | 0.0.1 | MIT | 2026-11-08 | https://www.npmjs.com/package/server-only |
| caniuse-lite（Next の推移的依存・データ） | npm | — | CC-BY-4.0 | 2026-11-08 | https://www.npmjs.com/package/caniuse-lite |
| Mailpit（開発用メール受信、P4 で導入予定） | コンテナ | latest | MIT | 2026-11-08 | https://github.com/axllent/mailpit |
| pip-licenses（CI） | Python | 5.5.5 | MIT | 2026-11-08 | https://pypi.org/project/pip-licenses/ |
| next / react | npm | 16.4.5 / 19.3.1 | MIT | 2026-11-08 | https://github.com/vercel/next.js |
| tailwindcss | npm | 4.3.5 | MIT | 2026-11-08 | https://www.npmjs.com/package/tailwindcss |
| better-auth | npm | 1.7.18 | MIT | 2026-11-08 | https://github.com/better-auth/better-auth |
| zod | npm | 4.6.7 | MIT | 2026-11-08 | https://www.npmjs.com/package/zod |
| openapi-typescript / openapi-fetch | npm | 7.13.0 / 0.17.0 | MIT | 2026-11-08 | https://www.npmjs.com/package/openapi-typescript |
| storybook / vitest | npm | 10.6.6 / 5.1.0 | MIT | 2026-11-08 | https://www.npmjs.com/package/storybook |
| @playwright/test | npm | 1.65.0 | Apache-2.0 | 2026-11-08 | https://www.npmjs.com/package/@playwright/test |
| PostgreSQL | コンテナ | 17 系 | PostgreSQL | 2026-11-08 | https://www.postgresql.org/about/licence/ |
| Qdrant | コンテナ | v1.20.0 | Apache-2.0 | 2026-11-08 | https://github.com/qdrant/qdrant |
| Redis（RSALv2 を選択） | コンテナ | 8.10.3 | RSALv2 | 2026-11-08 | https://redis.io/legal/licenses/ |
| Valkey（代替） | コンテナ | 9.1.3 | BSD-3-Clause | 2026-11-08 | https://github.com/valkey-io/valkey |
| text-embeddings-inference | コンテナ | v1.9.4 | Apache-2.0 | 2026-11-08 | https://github.com/huggingface/text-embeddings-inference |
| Langfuse server（任意、`ee/` 不使用） | コンテナ | v4.76.0 | MIT | 2026-11-08 | https://github.com/langfuse/langfuse |
| LibreOffice（旧 Office 形式変換） | コンテナ内バイナリ | — | MPL-2.0 | 2026-11-08 | https://www.libreoffice.org/about-us/licenses/ |
| BAAI/bge-m3 | モデル重み | — | MIT | 2026-11-08 | https://huggingface.co/BAAI/bge-m3 |
| BAAI/bge-reranker-v2-m3 | モデル重み | — | Apache-2.0 | 2026-11-08 | https://huggingface.co/BAAI/bge-reranker-v2-m3 |
| cl-nagoya/ruri-v3-310m・130m・reranker-310m（比較候補） | モデル重み | — | Apache-2.0 | 2026-11-08 | https://huggingface.co/cl-nagoya/ruri-v3-310m |
| docling-layout-heron | モデル重み | — | Apache-2.0 | 2026-11-08 | https://huggingface.co/docling-project/docling-layout-heron |
| docling-models（TableFormer 等） | モデル重み | — | CDLA-Permissive-2.0 / Apache-2.0 | 2026-11-08 | https://huggingface.co/docling-project/docling-models |

## 不採用（記録のみ）

| コンポーネント | ライセンス | 理由 | 確認日 |
|---|---|---|---|
| LangGraph Agent Server | ELv2 + ライセンスキー | 本番自己ホストにキーが必要 | 2026-11-08 |
| MinerU 4.x | MinerU Open Source License（Apache-2.0 + 規模閾値・使用表示義務） | 表示義務が製品に及ぶ | 2026-11-08 |
| Infinity v3 | Infinity Restricted MIT 1.0 | 特定 25 事業者上での利用禁止（配備先を制約） | 2026-11-08 |
| MinIO | AGPL-3.0 | Langfuse 用 S3 は SeaweedFS か既存 S3 を使う | 2026-11-08 |
| license-checker（npm） | BSD-3-Clause | 2019 年以降更新なし。`pnpm licenses` を使う | 2026-11-08 |
