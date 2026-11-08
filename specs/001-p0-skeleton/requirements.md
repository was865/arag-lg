# 001 P0 骨格 — 要件

`docs/handoff.md` 第 3 節 P0。完了基準: `docker compose up` でヘルスチェックが通り、CI が緑。

## 受け入れ条件（EARS）

### リポジトリ構成
- R1. システムは `web/`（Next.js 16 + pnpm）と `api/`（FastAPI + uv, Python 3.13）の 2 つのアプリを 1 リポジトリに持つ。
- R2. 開発者が `make setup` を実行したとき、システムは両アプリの依存をロックファイルどおりに導入する。

### API（FastAPI）
- R3. `GET /healthz` が呼ばれたとき、システムは依存先を確認せず 200 と `{"status":"ok"}` を返す。
- R4. `GET /readyz` が呼ばれたとき、システムは Postgres・Qdrant・Redis・TEI（embed / rerank）の疎通を並行に確認し、全て成功なら 200、1 つでも失敗なら 503 を返す。応答には各依存の `ok` 真偽値だけを含め、失敗の詳細はログにのみ出す。
- R5. TEI の URL が未設定のとき、システムは当該依存を `skipped` とし、readiness の判定から外す（Mac での開発時に GPU 機が止まっていても他の開発を妨げない）。
- R6. 各依存確認は設定値（既定 2 秒）でタイムアウトし、タイムアウトは失敗として扱う。
- R7. リクエストに `X-Request-Id` があるとき、システムはその値を、無いときは新しい UUID を、応答ヘッダとその要求中の全ログ行に付ける。
- R8. システムはログを 1 行 1 JSON（`ts`, `level`, `msg`, `request_id`, `logger`）で標準出力に出す。`print` は使わない。
- R9. システムは OpenAPI 文書を `api/openapi.json` に書き出すコマンドを持ち、CI はコミット済みの文書と実装が一致しない場合に失敗する。

### Web（Next.js）
- R10. `GET /api/healthz` が呼ばれたとき、Web は 200 を返す。
- R11. Web は `api/openapi.json` から `openapi-typescript` で型を生成し、`openapi-fetch` の型付きクライアントで API を呼ぶ。CI は生成物がコミット済みと一致しない場合に失敗する。
- R12. Web のトップページは仮表示（日本語）とし、サーバ側で API の `/healthz` を呼んだ結果を表示する。UI 移植は P4。

### コンテナ構成
- R13. `docker compose up` で postgres・qdrant・redis・api・web が起動し、各サービスのヘルスチェックが通る。
- R14. `--profile cpu` を付けたとき、TEI（embed / rerank, CPU イメージ・小モデル）も起動する（CI 用。amd64 のみ）。
- R15. GPU 機（Windows + RTX 4090）では `compose.gpu.yaml` で TEI（Ada 用イメージ）を起動でき、Mac 側は `TEI_EMBED_URL` / `TEI_RERANK_URL` でそれを参照する。
- R16. Redis はイメージ差し替え（`REDIS_IMAGE`）だけで Valkey に置き換えられる。

### CI（GitHub Actions）
- R17. PR とmain への push で、api（ruff・mypy・pytest）、web（eslint・型検査・vitest・build）、OpenAPI 生成物の一致、ライセンス走査、compose 起動スモークを実行する。
- R18. ライセンス走査は禁止ライセンス（AGPL / GPL / SSPL / BUSL / Elastic-2.0）を含む依存があれば失敗する。LGPL は `specs/000-overview/licenses.md` で許可したもの（psycopg）だけ通す。

## 対象外
- 認証（P4）、DB スキーマとマイグレーションの中身（P1 以降。P0 では Alembic の初期化のみ）、UI 移植（P4）。
