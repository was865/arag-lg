# 030 解析の点検 — タスク

## P1 記録と体検（R1〜R8）
- [x] T1 `report.py` の規則とテスト（先に失敗するテスト）
- [x] T2 `ParseResult.meta`（status・errors・窓・所要時間）と偽サーバのテスト
- [x] T3 pipeline で `parse_report.json` を保存、`contents.parse_warnings`（移行 0009）
- [x] T4 API: `/parse-report`・`/docling`（admin）・`DocumentOut.parse_warnings`・`ChunkOut.body`、`make gen`
- [x] T5 CLI `reparse-report`
- [ ] T6 一覧・詳細に警告の札

## P2 対照の画面（R9〜R13）
- [ ] T7 座標変換・頁割り当ての純関数とテスト
- [ ] T8 「対照」の画面（PDF）
- [ ] T9 チャンクの 4 つの本文・頁の警告
- [ ] T10 出典の札から開く
- [ ] T11 `pdfjs-dist` のライセンス追記、`make lint test`、compose で実際に確かめる
