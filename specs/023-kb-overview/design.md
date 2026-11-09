# 023 ナレッジベースの概要 — 設計

- API は `api/src/arag/kb/router_documents.py` の `document_overview`。読める範囲の条件は一覧・統計と同じ `_readable_kb_filter`。
  - 引用の回数は `citations` を `messages.created_at` で 30 日に絞って文書ごとに数え、読める文書と結ぶ。
- 画面は `web/src/components/library/library-overview.tsx`。統計（文書数・状態の内訳）が変わったら取り直す（アップロードや処理の完了で更新される）。
- 形式の行は `formatRows`（`web/src/lib/library/view.ts`）。棒は単色の量の表示で、数は文字でも出す。
