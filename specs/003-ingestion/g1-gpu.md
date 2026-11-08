# G1 docling-serve の GPU メモリ・変換時間（GPU 機）

tasks.md G1 の残り（docling-serve の常駐量・ピーク・変換時間）。OCR 比較は Mac 側で実施済み（design.md §11）のため含めない。
生データ: `g1-convert.json`（評価 PDF 7 件 × 3 回）、`g1-convert-large.json`（72 ページ一括）、`g1-convert-large-w20.json`（72 ページ・20 ページ窓）。計測ツールは `tools/docling-bench`（`convert --page-window` を追加）。

## 結論

- **ピーク VRAM（GPU 全体）は 14,639 MiB / 24,564 MiB**（72 ページの文書を変換中）。余裕は約 9.9 GB。このうち約 6.9 GB はデスクトップアプリ（Google Play Games のエミュレータ等）で、推論サービス 5 コンテナの合計は約 7.7 GB（本番構成の docling + bge 2 つなら約 5.6 GB）。
- **docling-serve 自体は起動直後 約 1.0 GB、初回変換後 約 2.1 GB、72 ページ変換後 約 2.5 GB** を確保したまま保持する（torch のキャッシュアロケータ。変換が終わっても解放しない）。
- **1 ページあたり 0.38〜0.58 秒**（クライアント側の所要時間。サーバの処理時間では 0.38〜0.46 秒）。評価 7 件（計 18 ページ）は 1 件 0.5〜3.0 秒。
- 72 ページを **20 ページ窓（アプリの既定）で 4 回に分けても一括とほぼ同じ**（30.0 秒 vs 27.3 秒、+10%）。ピーク VRAM も変わらない。窓分割の不利は小さい。
- 送信条件はアプリ（`DoclingServeParser`）と同じにした: `to_formats=json`、`image_export_mode=embedded`、`do_ocr=true`、`do_table_structure=true`、**`ocr_lang` は送らない**（既定 auto → RapidOCR）。依頼文の `ocr_lang=["ja","en"]` で送ると全件 `failure` になる（下記「気づき」）。

## 環境

| 項目 | 値 |
|---|---|
| GPU | RTX 4090 24 GB（24,564 MiB）、ドライバ 616.92（CUDA 13.4、WDDM） |
| docling-serve | `ghcr.io/docling-project/docling-serve-cu130:v1.38.2`（`sha256:1e7e5099…a8f`、展開後 9.8 GB）。docling 2.142.1 / docling-core 2.104.0 / docling-ibm-models 4.0.4。`cuda:0` で動作（cu130 はこのドライバで問題なし） |
| 同時起動 | tei-embed（bge-m3）、tei-rerank（bge-reranker-v2-m3）、tei-embed-ruri、tei-rerank-ruri（比較用。本番では不要） |
| 計測 | 所要時間 = 非同期投入から結果取得まで（ポーリング間隔のため約 0.5 秒刻み）。サーバ処理時間 = 応答の `processing_time`。VRAM = `nvidia-smi` の GPU 全体使用量を 0.2 秒ごとに採取（WDDM ではプロセス別の値が N/A のため） |

## 常駐量（コンテナを 1 つずつ起動して増分を測定）

計測前の状態（全コンテナ稼働・docling は数時間前に変換済み）: 14,655 MiB / 24,564 MiB。全コンテナを止めた状態（デスクトップアプリのみ）: 6,913 MiB。

| コンテナ | 常駐（起動直後） | 備考 |
|---|---|---|
| tei-embed（bge-m3, fp16） | 1,554 MiB | |
| tei-rerank（bge-reranker-v2-m3, fp16） | 1,552 MiB | |
| tei-embed-ruri | 1,042 MiB | 比較用 |
| tei-rerank-ruri | 1,042 MiB | 比較用 |
| docling-serve | 977 MiB | 初回変換で +1,152 MiB（計 約 2.1 GB）、72 ページ変換で さらに +400 MiB（計 約 2.5 GB）。以後は保持 |

- `nvidia-smi --query-compute-apps` は WDDM のためプロセス別メモリが全件 `[N/A]`（記録のみ）。
- 先に「1 つずつ止めて差を見る」方法も試したが、直前に再起動したコンテナのロード完了前に次を止めてしまい値が崩れたため、上表は「全停止 → 1 つずつ起動して増分」で取り直した値。

## 評価 PDF 7 件（各 3 回、中央値）

| 文書 | ページ | 所要秒 | サーバ秒 | 秒/ページ | GPU ピーク MiB（全体） | JSON | 図 / 表 |
|---|---|---|---|---|---|---|---|
| 04-cross-page-table-semantic-loss | 4 | 2.06 | 1.99 | 0.52 | 14,243 | 51 KB | 0 / 2 |
| 05-image-grounding-cooling-line | 3 | 2.06 | 1.74 | 0.69 | 14,242 | 83 KB（図を base64 で埋め込み） | 1 / 1 |
| 06-multi-file-requirement-request | 2 | 3.03 | 2.54 | 1.51 | 14,240 | 7 KB | 0 / 0 |
| 07-multi-file-security-policy | 2 | 1.56 | 1.09 | 0.78 | 14,239 | 7 KB | 0 / 0 |
| 08-multi-file-vendor-quotes | 2 | 0.56 | 0.37 | 0.28 | 14,239 | 25 KB | 0 / 1 |
| 09-query-rewrite-acronym-runbook | 3 | 0.55 | 0.30 | 0.18 | 14,239 | 17 KB | 0 / 1 |
| 10-exception-latest-rule-conflict | 2 | 0.55 | 0.17 | 0.28 | 14,239 | 7 KB | 0 / 0 |
| **計** | **18** | **10.4** | **8.2** | **0.58** | — | 197 KB | 1 / 5 |

- 3 回の差は小さい（最大でも 06 の 2.57〜3.07 秒）。
- docling-serve 再起動直後の最初の 1 件（04）は 4.08 秒（モデルの GPU 転送を含む）。2 件目以降は上表の水準。
- 06 は 2 ページでも 2.5 秒かかる。ページ内のビットマップ領域に OCR が走っていると推定（未確認）。

## 大きめの文書（72 ページ = 評価 7 件を 4 回結合、7.5 MB、1 回）

| 送り方 | 要求数 | 所要秒 | サーバ秒 | 秒/ページ | GPU ピーク MiB（全体） | JSON | 図 / 表 |
|---|---|---|---|---|---|---|---|
| 一括 | 1 | 27.26 | 27.06 | 0.38 | 14,639 | 776 KB | 4 / 20 |
| 20 ページ窓（1-20, 21-40, 41-60, 61-72） | 4 | 29.98 | 28.41 | 0.42 | 14,637 | 777 KB | 4 / 20 |

- 一括変換中に docling の確保量が +400 MiB 増え（14,239 → 14,639）、窓分割の実行時にはその分が既に確保済みだった。窓分割は 1 要求あたりの処理ページを抑えるので、より大きな文書ほどピークを抑える効果があるはず（今回の 72 ページでは差が出ない規模）。
- 結合元の PDF は一時ディレクトリに作成し、リポジトリには入れていない。

## RTX 4090 24 GB に対する余裕

| 構成 | 使用量の目安 | 24 GB に対する余裕 |
|---|---|---|
| 今回の実測（デスクトップアプリ + 5 コンテナ、72 ページ変換中のピーク） | 14.6 GB | 約 9.9 GB |
| 本番想定（docling + bge 2 コンテナ、デスクトップアプリなし） | 約 5.6 GB（2.5 + 1.55 + 1.55） | 約 18 GB |
| 上 + ruri 2 コンテナ | 約 7.7 GB | 約 16 GB |

TEI はバッチ処理中に 1 コンテナ当たり +0.4〜0.6 GB 一時的に増える（002 の report）。それを足しても余裕は大きい。docling のワーカー数を増やす（並列変換）余地もある（未計測）。

## 気づき

1. **`ocr_lang=["ja","en"]` を送ると全件 `failure`**。docling-serve のログによると、auto が RapidOCR を選んでも「`ja` のモデルなし」でスキップし、次に EasyOCR を選ぶが `japanese_g2.pth` が無くダウンロードも無効なので失敗する。結果の取得は 404（"Task result not found"）。アプリは `ocr_lang` を送らない設計（design.md §11）なので影響はない。計測ツールの既定もアプリと同じにした。
2. docling は一度確保した VRAM を返さない。他の GPU 処理（TEI のバッチなど）と同居させるとき、docling の常駐は「最大の文書を処理した後の量」（今回は約 2.5 GB）で見積もる。
3. GPU 機ではデスクトップアプリ（Google Play Games のエミュレータ crosvm、Wallpaper Engine など）が約 6.9 GB の VRAM と GPU 時間を使っている。処理時間の正式値が必要なら、これらを止めて取り直す。
