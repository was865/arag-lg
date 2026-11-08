# 000 技術選定とバージョン・ライセンス確認

- 確認日: **2026-11-08**（PyPI / npm レジストリ / GitHub Releases / 公式ドキュメントを直接参照）
- 判定基準: `docs/handoff.md` 第 1 節「授权原则」
  - 宽松 OSS（MIT / Apache-2.0 / BSD / PostgreSQL）を優先。AGPL/GPL・ライセンスキー必須・自社事業に制限が及ぶ許諾は不可。
  - 「その製品自体をマネージドサービスとして売る」ことだけを禁じる許諾（RSAL / SSPL / ELv2 等）は、内部コンポーネントとしては可（条項を個別確認）。
  - オンラインのライセンス認証に依存しない。SaaS は任意扱い（無くても全機能が動く）。
- バージョンは P0 で `uv.lock` / `pnpm-lock.yaml` に固定する。以下は「本日時点の最新安定版」で、固定値の初期値とする。

## 1. 判定サマリ

| # | 対象 | 最新版（2026-11-08） | ライセンス | 判定 |
|---|---|---|---|---|
| 1 | LangChain / LangGraph（ライブラリ） | langchain 1.4.9 / langchain-core 1.7.6 / langgraph 1.2.20 | MIT | **採用** |
| 1' | LangGraph Agent Server | — | ELv2 + ライセンスキー | **不採用**（FastAPI で自前ホスト） |
| 1'' | Aegra（Agent Protocol 互換サーバ） | 0.11.0 | Apache-2.0 | **保留**（P3 で再評価。既定にしない） |
| 2 | Qdrant | v1.20.0（server）/ qdrant-client 1.20.0 | Apache-2.0 | **採用**（Query API サーバ側融合） |
| 3 | Docling | 2.148.0（docling-core 2.106.0） | MIT（モデル: Apache-2.0 / CDLA-Permissive-2.0） | **採用**（既定パーサ） |
| 3' | MinerU | 4.1.7 | **MinerU Open Source License**（Apache-2.0 + 追加条項） | **不採用**（理由は §4） |
| 4 | TEI（text-embeddings-inference） | v1.9.4 | Apache-2.0 | **採用**（dense 埋め込み・rerank） |
| 4' | Infinity v3（Rust） | v3.0.0 | **Infinity Restricted MIT 1.0**（独自） | **不採用**（理由は §5） |
| 4'' | infinity-emb（Python v2） | 0.0.78 | MIT | 予備（TEI で足りない場合のみ） |
| 5 | Better Auth | 1.7.18 | MIT | **採用**（ライブラリのみ。有料ダッシュボード等は使わない） |
| 6 | Next.js | 16.4.5（React 19.3.1 / Tailwind 4.3.5） | MIT | **採用** |
| 7 | Langfuse | server v4.76.0 / Python SDK 5.2.0 | MIT（`ee/` 配下を除く） | **任意**（compose の optional profile。無くても全機能可） |
| 8 | Redis | 8.10.3 | RSALv2 / SSPLv1 / AGPLv3 の三択 → **RSALv2 を選択** | **採用**（代替: Valkey 9.1.3, BSD-3） |

## 2. LangChain / LangGraph

| パッケージ | 版 | ライセンス | 出典 |
|---|---|---|---|
| langchain | 1.4.9（2026-11-04） | MIT | https://pypi.org/project/langchain/ |
| langchain-core | 1.7.6（2026-11-05） | MIT | https://pypi.org/project/langchain-core/ |
| langgraph | 1.2.20（2026-11-05） | MIT | https://pypi.org/project/langgraph/ |
| langgraph-checkpoint-postgres | 3.2.0（2026-10-14） | MIT | https://pypi.org/project/langgraph-checkpoint-postgres/ |
| langchain-openai | 1.7.4 | MIT | https://pypi.org/project/langchain-openai/ |
| langchain-anthropic | 1.7.10 | MIT | https://pypi.org/project/langchain-anthropic/ |
| langchain-deepseek | 1.1.1 | MIT | https://pypi.org/project/langchain-deepseek/ |
| @langchain/langgraph-sdk（npm） | 1.15.0 | MIT | https://www.npmjs.com/package/@langchain/langgraph-sdk |

確認事項:

- `create_agent` + middleware が標準。組み込み middleware に **ModelFallbackMiddleware / ModelRetryMiddleware / ToolRetryMiddleware / SummarizationMiddleware / ModelCallLimitMiddleware / ToolCallLimitMiddleware / HumanInTheLoopMiddleware / ContextEditingMiddleware / PIIMiddleware** などがある（https://docs.langchain.com/oss/python/langchain/middleware/built-in ）。
  → 旧版の「モデル降級」「最大ステップ」「ツール失敗時の扱い」は組み込みで置換し、**CRAG 評価・改写リトライ / 引用検証 / 忠実度チェック**だけを自作 middleware にする。
- ストリームは `stream_mode=["messages", "custom"]`。custom イベントは `get_stream_writer()` から送る（handoff 第 2 節の方針どおり）。
- **LangGraph Agent Server は使わない**（自己ホストの本番利用に ELv2 + LangSmith ライセンスキーが必要）。run の後台実行・Redis Stream 中継・取消は FastAPI で自作する。
- Aegra（https://github.com/aegra/aegra 、Apache-2.0、v0.11.0 / 2026-10-23、★約 1.3k）は `useStream` 互換を得る選択肢。成熟度とスキーマ所有の都合から既定にはせず、P3 着手時に PoC で比較する。

## 3. Qdrant（Query API の融合パラメータ）

| 対象 | 版 | ライセンス | 出典 |
|---|---|---|---|
| qdrant（server） | v1.20.0（2026-10-22） | Apache-2.0 | https://github.com/qdrant/qdrant/releases |
| qdrant-client（Python） | 1.20.0 | Apache-2.0 | https://pypi.org/project/qdrant-client/ |
| langchain-qdrant | 1.1.0（2025-10） | MIT | 使わない予定（Query API を直接叩くため） |

Query API の融合機能（https://qdrant.tech/documentation/concepts/hybrid-search/ ）:

| 機能 | 導入版 | 書式 |
|---|---|---|
| RRF | 1.10 | `query: {"rrf": {}}` |
| RRF の定数 `k`（既定 2） | 1.16 | `{"rrf": {"k": 60}}` |
| **Weighted RRF**（prefetch ごとの重み） | 1.17 | `{"rrf": {"weights": [3.0, 1.0]}}` ／ Python `models.RrfQuery(rrf=models.Rrf(k=60, weights=[...]))` |
| DBSF | 1.11 | `{"fusion": "dbsf"}`（prefetch 上位集合の平均±3σで正規化。prefetch の limit を大きめに） |
| Formula（スコア加工・時間減衰） | 1.14 | `{"formula": {"sum": ["$score", ...]}}` |
| multivector 再スコア | — | dense prefetch → `using: "colbert"` で late interaction（再スコア専用ベクトルは HNSW `m=0`） |

決定:

- 既定は **dense（prefetch）+ sparse BM25（prefetch）→ RRF(k=60)**。旧版の自前 RRF（k=60）と同条件で開始し、P2 eval で weights・DBSF と比較する。
- 注意: 旧 Qdrant からの移行は不要（新規構築）。1.17 で RocksDB が廃止されているため、将来のアップグレードはマイナー版を 1 つずつ上げる運用にする。

## 4. Docling / MinerU（解析）

| 対象 | 版 | ライセンス | 出典 |
|---|---|---|---|
| docling | 2.148.0（2026-11-05） | MIT | https://github.com/docling-project/docling |
| docling-core | 2.106.0 | MIT | https://pypi.org/project/docling-core/ |
| docling-layout-heron（レイアウトモデル） | 2026-02 | Apache-2.0 | https://huggingface.co/docling-project/docling-layout-heron |
| docling-models（TableFormer 等） | 2025-12 | CDLA-Permissive-2.0 / Apache-2.0 | https://huggingface.co/docling-project/docling-models |
| OCR エンジン（extra） | RapidOCR / EasyOCR / Tesseract | Apache-2.0 | docling の extras（`rapidocr` / `easyocr` / `tesserocr`） |
| LibreOffice（.doc/.xls/.ppt/.rtf 変換） | — | MPL-2.0（別プロセス実行） | Docling 公式の対応形式表 |

- 対応形式: PDF / DOCX / XLSX / PPTX / HTML / Markdown / CSV / 画像 ほか。旧 Office 形式は LibreOffice が必要（旧版の `soffice` 変換と同じ）。
- 決定: **Docling を既定パーサ**。実行形態は **docling-serve**（MIT, v1.38.2 / 2026-10-27, https://github.com/docling-project/docling-serve ）を HTTP で呼ぶ（GPU 機は `docling-serve-cu130`、Mac 単独は arm64 対応の `docling-serve-cpu`）。api/worker のイメージに torch を入れずに済み、GPU 機とファイル共有も不要になる（specs/003-ingestion/design.md §1）。`HybridChunker` で見出し階層 + token 上限の分割。P1 で確認する未決事項: 日本語 OCR の品質（RapidOCR の日本語モデル vs Tesseract `jpn`）、大 PDF のページ窓分割、表の跨ページ結合。

**MinerU（不採用）**: 4.x（3.1.0 / 2026-04 以降）で AGPL-3.0 から **「MinerU Open Source License」（Apache-2.0 + 追加条項）** に変更された（https://github.com/opendatalab/MinerU/blob/master/LICENSE.md ）。追加条項は (a) 月間 MAU 1 億超 または 月商 2,000 万 USD 超で商用ライセンス必須、(b) 第三者向けオンラインサービスで使う場合は UI か公開文書で MinerU 使用の明示が必須、(c) 違反時は自動失効。AGPL ではなくなったが、**表示義務が当社と顧客の製品に及ぶ**ため、授权原则の「自社事業に制限が及ぶ許諾」に該当すると判断し、既定・同梱とも不採用。Docling で品質が不足する文書種別が eval で判明した場合のみ、表示義務を受け入れるかをユーザーが判断する。

## 5. 推論サービス（TEI / Infinity）と各モデルの対応

| 対象 | 版 | ライセンス | 出典 |
|---|---|---|---|
| TEI | v1.9.4（2026-09-15） | Apache-2.0 | https://github.com/huggingface/text-embeddings-inference |
| Infinity v3（Rust/LibTorch） | v3.0.0（2026-10-26） | Infinity Restricted MIT 1.0 | https://github.com/michaelfeil/infinity/blob/main/libs/infinity-v3/LICENSING.md |
| infinity-emb（Python v2） | 0.0.78 | MIT | https://pypi.org/project/infinity-emb/ |

モデル対応表（TEI 公式「Supported models」・Infinity v3 の supported-models.md・HF モデルカードより）:

| モデル | 重みライセンス | アーキテクチャ | TEI | Infinity v3 | 備考 |
|---|---|---|---|---|---|
| BAAI/bge-m3（dense） | MIT | XLM-RoBERTa | ○（XLM-RoBERTa 系埋め込み対応） | ○ | |
| BAAI/bge-m3（**sparse**） | MIT | 専用ヘッド | **×**（SPLADE は `ForMaskedLM` のみ） | **×**（「dense のみ提供」と明記） | 両者とも非対応 |
| BAAI/bge-m3（multivector） | MIT | 専用ヘッド | × | ○（token-vector） | Infinity 不採用のため候補外 |
| BAAI/bge-reranker-v2-m3 | Apache-2.0 | XLM-RoBERTa 分類 | ○（XLM-RoBERTa 分類対応。カタログ記載は v1 系のみ → P0 で起動確認） | ○ | |
| cl-nagoya/ruri-v3-310m / 130m | Apache-2.0 | ModernBERT | ○見込み（ModernBERT 対応・`tokenizer.json` 有り → P0 で起動確認） | ○見込み | クエリ/文書のプレフィックス付与はアプリ側 |
| cl-nagoya/ruri-v3-reranker-310m | Apache-2.0 | ModernBERT 分類 | ○見込み（ModernBERT 分類ヘッド対応） | ○見込み | |

決定:

- **TEI を採用**（embedding 用と rerank 用で 2 コンテナ）。
- **Infinity v3 は不採用**: 独自ライセンスで、指定 25 社のクラウド/GPU 事業者上での利用を目的を問わず禁止している。顧客の配備先を制約するため授权原则に反する。Python v2（MIT）は保守の主軸が v3 に移っており、予備扱い。
- **BGE-M3 sparse はどの推論サーバでも出せない** → キーワード経路は handoff 既定どおり **Sudachi 分かち書き → BM25 sparse（Qdrant の IDF modifier）** をアプリ側で生成する。BGE-M3 sparse との比較は P2 eval で「FlagEmbedding を使う小さな自作サービス」を一時的に立てて行い、勝った場合のみ常設する。
- multivector 再スコアは候補から外す（P2 で必要になれば再検討）。

| 日本語分かち書き | 版 | ライセンス | 出典 |
|---|---|---|---|
| SudachiPy | 0.7.0 | Apache-2.0 | https://pypi.org/project/SudachiPy/ |
| SudachiDict-core | 20261015 | Apache-2.0 | https://pypi.org/project/SudachiDict-core/ |

## 6. Better Auth

| 対象 | 版 | ライセンス | 出典 |
|---|---|---|---|
| better-auth | 1.7.18（2026-11-05） | MIT | https://github.com/better-auth/better-auth |

- 使う機能（すべてライブラリ内・無料）: メール+パスワード、メール検証、パスワードリセット、セッション一覧・失効、レート制限、`jwt` プラグイン、`admin` プラグイン（ロール・強制サインアウト・BAN）。チーム機能が必要になれば `organization` プラグイン（teams 対応）。
- **Python 側の検証**: `jwt` プラグインが `/api/auth/jwks` で公開鍵を配布（既定 EdDSA / Ed25519、`kid` 付き）。FastAPI は JWKS をキャッシュしてローカル検証し、未知の `kid` のときだけ再取得する（https://www.better-auth.com/docs/plugins/jwt ）。Python は PyJWT 2.15.1（MIT）で検証する。
- 有料のダッシュボード／インフラサービスは使わない（無くても全機能が動く）。

## 7. Next.js 16 とフロント周辺

| 対象 | 版 | ライセンス | 出典 |
|---|---|---|---|
| next | 16.4.5（2026-11-03） | MIT | https://github.com/vercel/next.js/releases |
| react | 19.3.1 | MIT | https://www.npmjs.com/package/react |
| tailwindcss | 4.3.5 | MIT | https://www.npmjs.com/package/tailwindcss |
| zod | 4.6.7 | MIT | https://www.npmjs.com/package/zod |
| openapi-typescript / openapi-fetch | 7.13.0 / 0.17.0 | MIT | https://www.npmjs.com/package/openapi-typescript |
| storybook | 10.6.6 | MIT | https://www.npmjs.com/package/storybook |
| vitest | 5.1.0 | MIT | https://www.npmjs.com/package/vitest |
| @playwright/test | 1.65.0 | Apache-2.0 | https://www.npmjs.com/package/@playwright/test |

- Next 16 では `middleware.ts` が `proxy.ts` に改称（旧版も `src/proxy.ts`）。
- 旧版は drizzle-orm を使っていたが、新版の Next は Better Auth の表だけを持つため、Better Auth の Kysely/pg アダプタで足りる見込み（drizzle 不要なら入れない）。

## 8. Langfuse（任意）

| 対象 | 版 | ライセンス | 出典 |
|---|---|---|---|
| langfuse（server） | v4.76.0（2026-11-05） | MIT（`ee/`・`web/src/ee/`・`worker/src/ee/`・`packages/shared/src/server/ee/` を除く） | https://github.com/langfuse/langfuse/blob/main/LICENSE |
| langfuse（Python SDK） | 5.2.0 | MIT | https://pypi.org/project/langfuse/ |

- 自己ホストには Postgres・**ClickHouse**（Apache-2.0）・Redis/Valkey・**S3 互換ストレージ**・web/worker コンテナが必要（https://langfuse.com/self-hosting ）。EE 機能（Organization Creators / Instance Management API / UI Customization）はライセンスキーが必要だが使わない。
- S3 互換ストレージは **MinIO（AGPL-3.0）を使わない**。顧客の既存 S3 か、Apache-2.0 の SeaweedFS を compose の optional profile に置く。
- 決定: アプリは **OpenTelemetry（opentelemetry-sdk 1.45.2, Apache-2.0）で計装**し、Langfuse は任意の受け口とする。Langfuse 無しでも JSON ログ + request-id で追跡できること。

## 9. Redis / Valkey

| 対象 | 版 | ライセンス | 出典 |
|---|---|---|---|
| Redis | 8.10.3（2026-10-26） | RSALv2 / SSPLv1 / AGPLv3 から選択 | https://redis.io/legal/licenses/ ・ https://github.com/redis/redis/releases |
| Valkey | 9.1.3（2026-10-26） | BSD-3-Clause | https://github.com/valkey-io/valkey |
| redis-py | 8.1.0 | MIT | https://pypi.org/project/redis/ |

- **RSALv2 を選択**: 制限は「Redis 自体を第三者向けマネージドサービスとして提供しない」「ソースを改変して再配布しない」等で、アプリ内部コンポーネント利用には影響しない。
- 使うのは Streams・基本的なキー操作だけなので、OSI ライセンスを求める顧客には Valkey にそのまま差し替える（compose の image 差し替えのみ。CI で両方の起動テストを回す）。

## 10. その他（P0 で導入予定）

| 対象 | 版 | ライセンス | 出典 |
|---|---|---|---|
| fastapi | 0.162.2 | MIT | https://pypi.org/project/fastapi/ |
| pydantic | 2.14.3 | MIT | https://pypi.org/project/pydantic/ |
| sqlalchemy / alembic | 2.1.8 / 1.20.1 | MIT | https://pypi.org/project/SQLAlchemy/ |
| uvicorn | 0.54.0 | BSD-3-Clause | https://pypi.org/project/uvicorn/ |
| sse-starlette | 3.7.0 | BSD-3-Clause | https://pypi.org/project/sse-starlette/ |
| PostgreSQL | 17 系 | PostgreSQL License | https://www.postgresql.org/about/licence/ |
| pip-licenses（CI） | 5.5.5 | MIT | https://pypi.org/project/pip-licenses/ |

- JS 側のライセンス走査は `license-checker`（最終リリース 2019 年で保守停止）ではなく **`pnpm licenses list --json`** を CI で使う。
- 禁止リスト（CI で失敗させる）: AGPL-*, GPL-*（LGPL は個別判断）, SSPL-*, BUSL-*, Elastic-2.0, 独自 Restricted 系。Redis 本体はコンテナ利用で依存ツリーに入らないため走査対象外とし、本書で管理する。

## 11. 残課題（P0 で確認）

1. TEI で `bge-reranker-v2-m3`・`ruri-v3-310m`・`ruri-v3-reranker-310m` が起動し、FlagEmbedding / sentence-transformers と同じスコアを返すか（数値一致テストを P0 に入れる）。
   - **結果（2026-11-08、`specs/002-tei-verification/report.md`）**: 4 モデルとも TEI 1.9.4（`89-1.9.4`）で起動。embedding は両系列合格（最小 cosine 0.99999）。rerank は当初基準（raw 差 ≤ 1e-2・全順位一致）を満たさない（bge 最大 2.15e-2、ruri 最大 1.47e-2）。原因は TEI の GeLU tanh 近似（bge）と fp16 で、設定では消せない。入れ替わりは参照差 < 0.005 logit の非関連文書どうしに限られ、上位 3 件は全クエリで一致。
   - **決定（ユーザー確認済み）**: rerank の受け入れ基準を「sigmoid 後の最大差 ≤ 5e-3」かつ「上位 k 件（既定 3）の順位一致。参照差 < 0.01 の同点圏は除く」に改め、**TEI を継続採用**する。今回の結果はこの基準を満たす（sigmoid 最大差 bge 2.2e-3・ruri 1.1e-3）。TEI の fp32 起動は非 Flash 実装で極端に遅いため使わない。
2. TEI の CPU イメージで開発機（Apple Silicon）と CI が回るか。GPU 本番は `cuda` イメージ。
3. Docling の日本語 OCR エンジン選定（P1）。

## 12. 開発環境（2026-11-08 ユーザー確認）

| 機械 | 役割 | 備考 |
|---|---|---|
| Mac（Apple Silicon, arm64） | 日常開発。Next.js・FastAPI・Postgres・Qdrant・Redis を compose で起動 | TEI の CPU イメージは **amd64 のみ**（`cpu-1.9.4` を確認）。Mac では TEI を動かさず GPU 機を参照する |
| Windows + RTX 4090（同一 LAN, SSH 可） | 推論（TEI embed / rerank）と入庫ワーカー（Docling）、P1・P2 の全量 eval | Docker Desktop（WSL2 + NVIDIA GPU）で `compose.gpu.yaml` を起動。TEI は Ada 用イメージ `89-1.9.4` |
| GitHub Actions（ubuntu, amd64） | CI。TEI は `cpu-1.9.4` と小モデルで疎通のみ | GPU 不要 |

- アプリは推論先を環境変数（`TEI_EMBED_URL` / `TEI_RERANK_URL`）で受け取り、どの機械で動いているかを意識しない。
- 追加確認: **psycopg 3（LGPL-3.0）**は langgraph-checkpoint-postgres の必須依存。改変せずライブラリとして使う限り商用に制約はない（LGPL は「個別判断」の対象としてここで許可）。
