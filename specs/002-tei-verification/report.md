# 002 TEI 数値一致検証 — 結果報告

decisions.md §11-1（TEI で bge-reranker-v2-m3・ruri-v3-310m・ruri-v3-reranker-310m が起動し、参照実装と同じスコアを返すか）の確認結果。検証ツールは `tools/tei-verify/`、生データは `tools/tei-verify/results/{bge,ruri}.json`。

## 結論

| 系列 | embedding | rerank | 判定 |
|---|---|---|---|
| bge（bge-m3 / bge-reranker-v2-m3） | **合格**（最小 cosine 0.99999） | **不合格**（raw 最大差 1.96〜2.15e-2、全 5 クエリで下位の順位が入れ替わる） | 不合格 |
| ruri（ruri-v3-310m / ruri-v3-reranker-310m） | **合格**（最小 cosine 1.00000） | **不合格**（raw 最大差 0.99〜1.47e-2、4 クエリで下位の順位が入れ替わる） | 不合格 |

- 4 モデルとも TEI 1.9.4（`89-1.9.4`）で**起動・応答に問題なし**（起動失敗・再起動ゼロ）。
- rerank の不一致は**基準（絶対差 ≤ 1e-2・全順位一致）を満たさない**が、入れ替わりはすべて**スコア差 0.005 logit 未満の僅差の非関連文書どうし**。**上位 3 件の並びは全クエリ・両系列で一致**し、sigmoid 後の最大差は 2.3e-3 以下。
- 原因（下記「不一致の分析」）は TEI の **GeLU の tanh 近似**（bge）と **fp16 推論**。TEI の設定では解消できない。
- 実用上の影響は小さいと考えるが、基準をどう扱うか（基準の見直し / TEI 継続採用）は Mac 側で判断してほしい。案は末尾。

## 環境

| 項目 | 値 |
|---|---|
| GPU 機 | MSI-RTX4090（Windows 11 Pro 10.0.26300、RAM 64GB） |
| GPU / ドライバ | GeForce RTX 4090 24GB / 616.92（CUDA UMD 13.4、WDDM） |
| Docker | Docker Desktop 4.90.0 / Engine 29.7.2（WSL2 カーネル 6.6.87.2） |
| TEI イメージ | `ghcr.io/huggingface/text-embeddings-inference:89-1.9.4`（`sha256:1a284d9c…0fce2`、TEI commit `e80ef22`） |
| TEI 設定 | 既定（dtype=float16、auto_truncate=true、max_client_batch_size=32）。embed は `--max-batch-tokens 16384` |
| 参照実装 | CPU・fp32。sentence-transformers 6.2.0、FlagEmbedding 1.4.2、transformers 5.22.2、torch 2.15.0+cpu、Python 3.13 |
| 評価データ | `tools/tei-verify/data/corpus.json`：架空の社内文書 20 件（規程・仕様書・議事録・手順書。表記揺れ・型番・条項番号を含む）、クエリ 5 件 |

モデル revision（TEI 側ボリュームと参照側 HF キャッシュで同一 commit を確認。TEI 1.9.4 の `/info` は `model_sha` が null を返すため、ツールは参照側 snapshot の commit を JSON に記録する）:

| モデル | revision | TEI のバックエンド |
|---|---|---|
| BAAI/bge-m3 | `5617a9f61b028005a4858fdac845db406aefb181` | FlashBert（fp16, pooling=cls） |
| BAAI/bge-reranker-v2-m3 | `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e` | FlashBert（fp16） |
| cl-nagoya/ruri-v3-310m | `18b60fb8c2b9df296fb4212bb7d23ef94e579cd3` | FlashModernBert（fp16, pooling=mean） |
| cl-nagoya/ruri-v3-reranker-310m | `bb46934ee9ed09f850b9fcff17501b3ef7ddb2b3` | FlashModernBert（fp16） |

## 方法

- embedding: クエリ 5 + 文書 20 の計 25 件を TEI `/embed`（normalize=true, truncate=false）と `SentenceTransformer.encode(normalize_embeddings=True)` で計算し、行ごとの cosine を比べる。ruri は「検索クエリ: 」「検索文書: 」を両者に同じく付ける。基準: 全件 ≥ 0.999。
- rerank: 5 クエリ × 20 文書を TEI `/rerank`（raw_scores=true / false）と参照実装（bge: `FlagReranker(use_fp16=False).compute_score(normalize=False)`、ruri: `CrossEncoder.predict(activation_fn=Identity)`、sigmoid は参照側で計算）で比べる。基準: 絶対差 ≤ 1e-2 かつクエリごとの降順順位が完全一致。参考として上位 3 件の並びも出す（合否には使わない）。
- 速度: 820 文字の長文 32 件（bge-m3 で平均 511 token、ruri で 466〜469 token）を 1 リクエストにまとめ、ウォームアップ 2 回のあと 10 回計測。

## 結果

数値一致（3 回実行。最終回の表は `results/*.md`）:

| 系列 | 最小 cosine | 平均 cosine | rerank raw 最大差（3 回） | sigmoid 最大差（3 回） | 全順位の不一致 | 上位 3 件の不一致 |
|---|---|---|---|---|---|---|
| bge | 0.99999 | 0.99999 | 2.15e-2 / 2.15e-2 / 1.96e-2 | 2.24e-3 / 1.94e-3 / 2.05e-3 | q01〜q05 | なし |
| ruri | 1.00000 | 1.00000 | 9.89e-3 / 1.47e-2 / 1.13e-2 | 1.06e-3 / 1.06e-3 / 7.07e-4 | q01〜q04 | なし |

- 参照実装どうしの検算: transformers 直書き（exact GeLU）と FlagReranker の差は 4.8e-6、順位一致（参照側の実装に問題がないことの確認）。
- 上位 5 件では、bge q05 の 4・5 位だけが入れ替わる（TEI fp16 では両方 −11.0156 の同点、参照は −11.0130 / −11.0169）。
- 関連文書（corpus.json の `relevant`）は両系列・全クエリで上位 2 位以内に入る（TEI・参照とも同じ）。

速度と GPU メモリ（目安）:

| モデル | 単独起動時の GPU メモリ（ロード後 / 計測中ピーク、増分） | 文書/秒（32 件 × 約 500 token） | p50 / バッチ |
|---|---|---|---|
| bge-m3（embed） | +1.6 GB / +2.0 GB | 256〜279 | 110〜123 ms |
| bge-reranker-v2-m3 | +1.55 GB / +2.0 GB | 167〜264 | 117〜118 ms |
| ruri-v3-310m（embed） | +1.0〜1.3 GB / +1.8 GB | 158〜243 | 131〜211 ms |
| ruri-v3-reranker-310m | +2.3 GB / +2.8 GB | 65〜247 | 127〜138 ms |

- 4 コンテナ同時起動時の GPU 全体使用量は約 9.0〜9.4 GB（デスクトップアプリ分を含む。TEI 以外の使用は約 1.2〜3.6 GB で変動）。
- **速度はばらつきが大きい**: この機械は計測中も他アプリ（Android エミュレータ crosvm、Wallpaper Engine 等）が GPU を約 30% 使っていた。ruri reranker の 65 文書/秒は単独計測時の外れ値で、直後の再計測は 167〜209。正式な性能値が必要なら他アプリを止めて取り直す。
- 参考: 計測用長文が平均 374 token のときは bge で embed 346・rerank 353 文書/秒。

## 不一致の分析

事実:

1. TEI は bge 系（XLM-RoBERTa / Bert）の起動時に「`hidden_act=gelu` だが GeLU + tanh 近似を使う」と WARN を出す。ruri（ModernBERT）では出ない。
2. TEI を `--dtype float32` で臨時起動（ポート 8092）して bge reranker を比べると、raw 最大差 2.16e-2 はほぼ変わらず、全順位の不一致は 5 クエリ → 2 クエリ（q02, q03）に減った。
3. 参照実装の活性化関数だけを `gelu_pytorch_tanh` に変えて CPU で再計算すると、exact GeLU の参照との差は **2.00e-2・不一致 q02, q03**。TEI fp32 の結果とほぼ同じ。
4. ruri reranker の raw 最大差は 3 回の実行で 9.9e-3〜1.5e-2 と変動した（同じ入力でも TEI 側のバッチ構成によって fp16 の丸めが変わると考えられる）。
5. TEI fp32 は非 Flash 実装になり非常に遅い（bge reranker で 5 リクエストに約 7 分）。ruri reranker の fp32（ModernBert 非 Flash）は「Warming up model」から 10 分以上進まず、計測できなかった（臨時コンテナは削除済み）。

推定原因:

- **bge の raw 差 ≈ 0.02 は GeLU の tanh 近似が主因**（事実 2・3）。TEI のビルド上の仕様で、オプションでは切り替えられない。
- **全順位の入れ替わりの残りは fp16**（事実 2・4）。入れ替わる文書はスコア −8〜−11 の非関連文書どうしで、差が fp16 の分解能に埋もれる。
- **ruri の raw 差は fp16 のみ**（tanh 近似の WARN なし）で、基準 1e-2 の境界付近を行き来する。

## 判断のための案（決定は Mac 側）

1. **基準を実用寄りに見直して TEI を継続**（推奨）: 例「sigmoid 後の絶対差 ≤ 5e-3」かつ「上位 k 件（k = rerank 後に LLM へ渡す件数、例 5〜10）の順位一致。ただし参照スコア差 < 0.01 logit の同点圏は除外」。今回の結果は両系列ともこれを満たす（bge q05 の 4・5 位は同点圏）。
2. 厳密一致を求めるなら TEI fp32 だが、速度が実用にならない（事実 5）。
3. 参照実装（FlagEmbedding / sentence-transformers）を自前サービスで GPU 推論する案もあるが、TEI 採用の利点（バッチ処理・保守不要）を失う。

## 疎通

- コンテナは GPU 機で起動したまま（8081〜8084、`restart: unless-stopped`）。
- Windows ファイアウォールには **Docker Desktop Backend の受信許可規則（Public / Private）が既にある**ため、規則は追加していない。Mac（10.32.1.34）からの到達確認は Mac 側に依頼する。届かない場合は、ユーザーが管理者 PowerShell で規則を追加する（送信元 10.32.0.0/16・100.64.0.0/10 に限定）。なお、GPU 機の有線 LAN（以太网）のネットワークプロファイルは **Public**（Tailscale は Private）なので、Private 限定の規則だけでは LAN 経由が通らない点に注意。

## 起動時の記録

- 失敗なし。WARN のみ: `model.safetensors` が無い bge-m3 は `pytorch_model.bin` を使う（初回ロードが遅い。ダウンロード含め約 6 分）、`config_sentence_transformers.json` が無い reranker は ST 設定なしで起動（問題なし）、`Invalid hostname, defaulting to 0.0.0.0`（無害）。
- 初回のモデル取得はコンテナ当たり 4〜7 分（キャッシュは名前付きボリューム `arag-gpu_tei-cache`）。2 回目以降の起動は数秒。
- TEI イメージは約 5.0 GB。
