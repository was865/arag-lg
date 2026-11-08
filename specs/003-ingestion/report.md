# P1 入庫 実データ確認（E1〜E5）報告

実施日: 2026-11-08 ／ 実施: Mac（api・worker・postgres・qdrant・redis を compose）＋ GPU 機（Windows + RTX 4090）の docling-serve v1.38.2（:5001）・TEI bge-m3（:8081）・bge-reranker-v2-m3（:8082）

文脈付与モデル・画像説明モデルは未設定（`ARAG_CONTEXT_MODEL` / `ARAG_VLM_MODEL` 空）。文脈は見出しパスで代用され、費用は 0。LLM を使った文脈付与の費用実測は、モデルとキーの設定後に再測定する（design §10-3）。

## 結果

| # | 内容 | 結果 |
|---|---|---|
| E1 | 評価 PDF 7 件を `python -m arag.cli ingest-dir eval/assets/agentic_rag_demo --kb <組織KB>` で入庫 | **7/7 ready**、子チャンク 24、所要 13.6 秒（並列 2） |
| E2 | 見出しツリー・04 の表ヘッダ・05 の図 | 全件で見出しツリーを取得。04 の表チャンクは `設備ID` ヘッダ付き（下記「見つかった問題」で修正後、続きの行もヘッダ配下）。05 は図を `assets/fig-1.png` に取り出し済み。画像説明モデル未設定のため `figure` チャンクは無し（要件どおり「有効時」のみ） |
| E3 | 同じ PDF（07）を個人 KB にアップロード | `status: skipped`・`job_id: null`（解析なし） |
| E4 | Qdrant の点数と子チャンク数、dense と bm25 | 7 件すべて点数 = 子チャンク数、全点が `dense` と非空の `bm25` を持ち、payload の `document_ids` / `kb_ids` が正しい |
| E5 | 10 を削除→復元→削除→`python -m arag.cli gc --retention-days 0` | 削除中は payload の `document_ids` が空（検索対象外）、復元で戻る。GC 後は点 0・行 0（documents/chunks）・ファイル 0。監査ログに document.delete ×2・document.restore・gc.purge |

文書別（再索引後）:

| 文書 | ページ | セクション | 子チャンク（種別） |
|---|---|---|---|
| 04 cross-page-table | 4 | 5 | text 4・table 1 |
| 05 image-grounding | 3 | 4 | text 3・table 1 |
| 06 requirement-request | 2 | 3 | text 2・list 1 |
| 07 security-policy | 2 | 3 | text 2・list 1 |
| 08 vendor-quotes | 2 | 2 | text 1・table 1 |
| 09 acronym-runbook | 3 | 3 | text 2・table 1 |
| 10 exception-rule | 2 | 4 | text 4 |

## 見つかった問題と対応

1. **ページをまたぐ表の続きがヘッダを失う（04）**。docling は改ページで表を 2 つに分け、続きの表には列ヘッダが無い。Markdown 化で先頭のデータ行（MX-17）がヘッダ扱いになり、「MX-17 = 停止候補・N9」の対応が読めなくなっていた。
   → `merge_continued_tables` を追加（本文順で直前が表・次ページから始まる・列数が同じ・列ヘッダもキャプションも無い表を前の表へ結合）。`CHUNKER_VERSION` を `hybrid-md-v2` に上げ、`cli reindex` で再解析なしに再チャンク化して確認。実出力を `api/tests/fixtures/04-cross-page-table.docling.json` に置き回帰テスト化（G4）。
2. **OCR 言語 `ja,en` で変換が失敗**。docling-serve の既定エンジン RapidOCR は 1 言語しか受けない。→ 既定は `ocr_lang` を送らない（下記）。
3. GC を手動で回す手段が無かった。→ `python -m arag.cli gc [--retention-days N]` を追加。

## 日本語 OCR（G1・design §10-1）

評価 PDF 2 件（07・04）の 1 ページ目を 145dpi の PNG にし、`force_ocr` で変換してテキスト層と比較（空白除去後の一致率）。

| 設定 | 07 | 04 | 備考 |
|---|---|---|---|
| 既定（`ocr_preset=auto` → RapidOCR、PP-OCRv5） | 0.952・3.1 秒 | 0.954・2.1 秒 | 採用 |
| `ocr_lang=iso:ja` | 0.952 | 0.954 | 既定と同じ結果 |
| `ocr_lang=ja,en` | 失敗 | 失敗 | RapidOCR は 1 言語のみ |
| `ocr_preset=easyocr` / `ocr_custom_config` easyocr | 失敗 | 失敗 | v1.38.2 イメージでは使えない |
| Tesseract | — | — | イメージに jpn が無い（Windows 側で確認） |

差分の大半は空白・記号（「/」「:」）の揺れで、本文の漢字・かなの誤認識はほぼ無かった。

## 未測定

- docling-serve の GPU メモリと大きな PDF の変換時間（GPU 機の `nvidia-smi` が必要。Windows 側のセッション再開後に測る）。
- 文脈付与（LLM）の費用・所要時間（モデル未設定）。
