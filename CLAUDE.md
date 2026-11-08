# CLAUDE.md

ARag を LangChain / LangGraph で作り直すプロジェクト（日本語版のみ）。

- **最初に `docs/handoff.md` を読むこと。** 目標・アーキテクチャ・ライセンス方針・段階計画・旧プロジェクトのソース地図がすべてここにある。
- 旧プロジェクト（参照専用・変更禁止）: `/Users/ansen/Documents/Projects/playground/a-rag`
- ユーザーとの会話は中国語。コードコメントとコミットメッセージは日本語（Conventional Commits、例 `feat: 〜を追加`）。UI 文言は日本語のみ。
- 商用利用に制限のある依存（ELv2・BSL・AGPL など）は採用しない（`docs/handoff.md` の「授权原则」節）。
- 開発は SDD + TDD。仕様は `specs/<番号>-<名前>/{requirements,design,tasks}.md`。

## 開発コマンド（詳細は `Makefile`・`specs/001-p0-skeleton/design.md`）

- `make setup` / `make test` / `make lint` / `make gen`（OpenAPI → TS 型）/ `make licenses`
- `make up-infra` で postgres・qdrant・redis、`make dev-api` / `make dev-web` で各アプリを起動。`make up` は全体を compose で起動。
- 推論（TEI）は GPU 機（Windows + RTX 4090）で `compose.gpu.yaml` を起動し、`.env` の `ARAG_TEI_*_URL` で参照する。Mac では TEI を動かさない（CPU イメージが amd64 のみ）。
- Next.js 16.4 は学習データと異なる点がある。`web/AGENTS.md` のとおり `web/node_modules/next/dist/docs/` を先に読む。
