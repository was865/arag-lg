# 001 P0 骨格 — タスク

各タスクは先に失敗するテストを書いてから実装する（括弧内は対応テスト / 確認手段）。

- [x] T1 api: uv プロジェクト・ruff・mypy・pytest の設定（`uv run pytest` が 0 件で通る）
- [x] T2 api: `/healthz`（test_health.py::test_healthz_ok）— R3
- [x] T3 api: `/readyz` 全成功 200・一部失敗 503・例外は fail・タイムアウトは fail・未設定は skipped（test_health.py）— R4〜R6
- [x] T4 api: RequestIdMiddleware（受信値の採用・不正値の置換・未指定時の生成・ログ行に含まれる）（test_request_id.py）— R7・R8
- [x] T5 api: 実チェッカ（Postgres / Qdrant / Redis / TEI）（compose スモークで確認）
- [x] T6 api: OpenAPI 書き出し（test_openapi.py::test_export_is_deterministic）— R9
- [x] T7 api: Dockerfile（uv、非 root、`/healthz` ヘルスチェック）
- [x] T8 web: Next.js 16 雛形（日本語・Inter + Noto Sans JP は P4 で移植）、`/api/healthz`（vitest）— R10
- [x] T9 web: openapi-typescript 生成 + openapi-fetch クライアント、トップで API の `/healthz` 表示 — R11・R12
- [x] T10 web: Dockerfile（standalone、非 root）
- [x] T11 compose.yaml / compose.gpu.yaml / .env.example — R13〜R16
- [x] T12 Makefile（setup / dev / test / lint / gen / up）— R2
- [x] T13 scripts/check_licenses.py（禁止・許可リスト判定の単体テスト付き）— R18
- [x] T14 .github/workflows/ci.yml — R17
- [x] T15 ローカルで `docker compose up` → `/readyz` 200 を確認
