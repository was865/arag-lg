# 030 解析の点検 — 設計

## 構成

| 場所 | 中身 |
|---|---|
| `api/src/arag/ingest/report.py` | 純関数。`build_report(doc, chunks, meta, assets) -> ParseReport`。警告の規則（R5）を 1 規則 1 関数で持つ |
| `api/src/arag/ingest/parser.py` | `ParseResult.meta` に docling-serve の `status`・`errors`・窓の数・所要時間・オプションを入れる |
| `api/src/arag/ingest/pipeline.py` | チャンク化と図の統合の後に `parse_report.json` を保存し、`contents.parse_warnings` を更新 |
| `api/src/arag/kb/router_documents.py` | `/parse-report`・`/docling`（admin）・`DocumentOut.parse_warnings`・`ChunkOut.body`（埋め込みに送った本文） |
| `api/src/arag/cli.py` | `reparse-report` |
| `web/src/components/library/inspect/` | 「解析の確認」の画面 |

## 記録の形（`parse_report.json`、version 1）

```
{ "version": 1, "parser": "docling-serve@1.38.2",
  "docling": { "statuses": ["success"], "errors": [], "windows": 3, "elapsed_sec": 41.2,
               "options": {"do_ocr": true, "ocr_lang": [], "page_window": 20} } | null,
  "totals": { "pages": 12, "texts": 340, "tables": 4, "pictures": 6, "chars": 18230, "chunks": 58 },
  "pages": [ { "page": 1, "items": 31, "chars": 1200, "tables": 0, "pictures": 1, "chunks": 5 } ],
  "warnings": [ { "code": "image_only_page", "severity": "warn", "page": 7, "message": "…" } ] }
```

- `docling` は `rendered` 再計算（R8）や PlainTextParser では `null`。
- 保存済みの `docling.json` から解析を飛ばしたとき（`_load_saved`）は、前の `parse_report.json` の `docling` を引き継ぐ。
- チャンクの埋め込み本文は `context + "\n\n" + text`（`pipeline.py` の `bodies`）。DB の `Chunk.context`・`text` から作れるので、新しい列は要らない。

## DB

- `contents.parse_warnings`（int, null 可）。warn 以上の件数。null は「記録なし」。移行 `0009`。

## 規則の閾値（設定にしない。定数で持つ）

- `image_only_page`: 文字 < 20 かつ図 ≥ 1。
- `garbled_text`: 頁の文字のうち U+FFFD と制御文字（改行・タブを除く）が 2% 超かつ 3 文字以上。
- `table_sparse`: 行 ≥ 3 で空のセル > 50%。
- `bbox_out_of_page`: 枠が頁の幅・高さを 10% 超えて外れる。頁の大きさが無ければ検査しない。

## 対照の画面

- PDF の描画は `pdfjs-dist`（Apache-2.0）。`licenses.md` に追記。原件は既存の `/original` から取る。
- 座標: `BOTTOMLEFT` は `y_view = page_height - y`。頁の大きさは `docling.json` の `pages[n].size`。`/parse-report` の頁に `size` を足す（枠の計算に要る）。
- 描画は頁ごとの canvas の上に絶対配置の枠。選んだチャンクの枠だけ強調する。
- 枠と一覧の行は同じ番号の印（`Seal` の `tone="neutral"`）を持ち、ホバー・フォーカスで互いに光る。回答の印と根拠カードの連動と同じ部品（`components/ui/link-marks.ts`）を使う。チャット側（`evidence-rail.tsx`）の移行は別の変更で行う。

## テスト

- 規則: 小さな DoclingDocument で 1 規則 1 ケース（`api/tests/test_parse_report.py`）。
- 解析器: 偽 docling-serve で `partial_success`・`errors` が `meta` に入ること。
- API: 権限（admin 以外は `/docling` が 403）、記録なしは 404（結合）。
- 画面: 座標変換と頁の割り当ては純関数にして vitest。
