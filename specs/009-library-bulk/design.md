# 009 文書ライブラリの一括操作 — 設計

- `lib/library/selection.ts`（テスト対象）: `toggleId`・`selectRange`（起点〜対象を一覧順で）・`chunk`（500 件ずつ）。
- `lib/library/api.ts`: `removeDocuments(ids)`（bulk-delete）。移動は既存の `moveDocuments`。
- `LibraryView`: `selected: Set<string>`・`anchor`・`selecting`。行の左端のアイコンをチェックボックスに切り替える。操作バーは一覧の下に重ねて固定。
