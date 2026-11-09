# 007 文書ビューア — 設計

- API: `router_documents.py` に `GET /v1/documents/{id}/sections`（`SectionOut[]`、`ordinal` 順、offset/limit）。
- Web:
  - `lib/library/api.ts`: `document(id)`、`outline(id)`、`sections(id, offset, limit)`。
  - `lib/library/viewer.ts`（純粋関数・テスト対象）: `resolveAssets(text, docId)`、`outlineDepth(sections)`（最小レベルを 0 にした字下げ）、`textPreviewKind(filename)`、`activeSectionId(offsets, scrollTop)`。
  - `components/library/document-viewer.tsx`: 重ねる画面。ヘッダ・タブ（整形表示 / 原本）・目次・本文。本文は `RenderedSectionBody`。
  - `components/documents/original-preview.tsx`: テキスト系の表示を追加。
  - `LibraryView`: 行クリック → `onOpenDocument(doc)`。`ChatApp` が `viewerDoc` を持ち、`history.pushState`（同じ URL に state だけ）で戻るボタンに対応。
  - 質問: `ScopeValue.documentIds` を足し、`runBody` で `document_ids` を送る。
