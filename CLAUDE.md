# CLAUDE.md

ARag を LangChain / LangGraph で作り直すプロジェクト（日本語版のみ）。

- **最初に `docs/handoff.md` を読むこと。** 目標・アーキテクチャ・ライセンス方針・段階計画・旧プロジェクトのソース地図がすべてここにある。
- 旧プロジェクト（参照専用・変更禁止）: `/Users/ansen/Documents/Projects/playground/a-rag`
- ユーザーとの会話は中国語。コードコメントとコミットメッセージは日本語（Conventional Commits、例 `feat: 〜を追加`）。UI 文言は日本語のみ。
- 商用利用に制限のある依存（ELv2・BSL・AGPL など）は採用しない（`docs/handoff.md` の「授权原则」節）。
- 開発は SDD + TDD。仕様は `specs/<番号>-<名前>/{requirements,design,tasks}.md`。
