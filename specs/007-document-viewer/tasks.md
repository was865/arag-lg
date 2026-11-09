# 007 文書ビューア — タスク

- [x] A1 API: 章の一覧（offset/limit・権限）— R10
- [x] B1 viewer の純粋関数（assets 解決・字下げ・テキスト判定・読んでいる章）— R5, R6, R8
- [x] B2 文書ビューア（ヘッダ・タブ・目次・章の追加読み込み）— R1〜R7
- [x] B3 原本のテキスト表示 — R8
- [x] B4 この文書に質問（document_ids）— R9
- [x] C1 ブラウザで確認（PDF・Markdown・表・モバイル）

## 実装メモ

- テキスト判定は既存の `getTextPreviewKind`（`lib/file-types.ts`）を使い、html を追加した（viewer 側に重複させない）。
- 解析結果の Markdown の | 表は `pipeTablesToHtml` で HTML 表にしてから描く（R3）。
- C1: PDF（目次・ページ・表・原本 iframe）、Markdown（整形表示・原本テキスト）、戻るボタンで閉じる、「この文書に質問」→ 範囲が文書名になり出典がその文書だけ、モバイル（目次の引き出し）をブラウザで確認。
