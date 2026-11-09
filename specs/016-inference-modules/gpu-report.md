# 図の説明用 vLLM（vllm-vl）の GPU 計測（GPU 機）

specs/016 R3 の図の説明モデルを GPU 機（RTX 4090 24 GB、Windows + Docker Desktop/WSL2）で起動し、VRAM・応答時間・疎通を測った（2026-11-09）。
Qwen2.5-VL-7B-Instruct-AWQ（既定）と Qwen3-VL-8B-Instruct-FP8（比較）の 2 つ。どちらも会話・文脈付与の vllm（Qwen3-8B-AWQ、:8090）と同時に常駐させた。

## 結論

- **どちらも Qwen3-8B と同時に起動・応答できた**。ただし 24 GB をほぼ使い切る（専用 VRAM 23.4〜23.5 GB / 24.0 GB、空き 0.7〜1.8 GB）。
- **Qwen2.5-VL-7B-AWQ**: 既定（KV 1500M・8192 トークン）のまま起動。重み 6.67 GiB。KV 27,424 トークン（8192 で 3.35 並列）。図 1 枚の説明が **2.2〜2.7 秒**。
- **Qwen3-VL-8B-FP8**: 重みが 10.1 GiB と大きく、16384 トークンは KV 1500M では足りず起動しない。**8192 トークン・KV 1500M で起動**（KV 10,656 トークン、1.30 並列）。図 1 枚の説明が **1.75〜1.8 秒**で、説明はより具体的。ツール呼び出し（tool_choice=auto）は hermes パーサで `tool_calls` が返る。
- **compose の修正が必要だった**: `--kv-cache-memory-bytes` を指定しても vLLM は起動時に「空き ≥ `--gpu-memory-utilization`（既定 0.92）× 全体」を確かめるため、他と同居すると必ず失敗する。`--gpu-memory-utilization=${VLM_GPU_UTIL:-0.3}` を追加した（実際の確保量には効かない。空きより小さい値ならよい）。
- ファイアウォールの変更は不要。:8091 は 10.32.1.30 経由でも 200（既存の「Docker Desktop Backend」受信規則が TCP 全ポートを許可している）。
- いま :8091 で動いているのは **qwen3-vl**（Mac 側の比較用）。既定の compose 値（Qwen2.5-VL）で起動し直すには環境変数なしで `up -d vllm-vl` する。

## 環境

| 項目 | 値 |
|---|---|
| GPU | RTX 4090 24 GB（24,564 MiB）、ドライバ 616.92（CUDA 13.4、WDDM） |
| イメージ | `vllm/vllm-openai:v0.32.0`（`sha256:befccf0e…5c34`。:8090 の vllm と同じ） |
| モデル | `Qwen/Qwen2.5-VL-7B-Instruct-AWQ`（rev 536a357、Apache-2.0、6.46 GiB）、`Qwen/Qwen3-VL-8B-Instruct-FP8`（rev 9cdc631、Apache-2.0、9.88 GiB） |
| 同居 | arag-llm（Qwen3-8B-AWQ、KV 2600M、:8090）、tei-embed（:8081）、tei-rerank-ruri（:8084）、docling-serve（:5001）。比較用の tei-rerank（bge）・tei-embed-ruri は途中で停止（下記） |
| 計測 | `nvidia-smi` の GPU 全体使用量（5 秒ごと）。WDDM ではプロセス別が N/A のため、Windows のパフォーマンスカウンタ `\GPU Process Memory(*)\Dedicated Usage` でコンテナ（WSL の vmwp プロセス内の割り当て単位）ごとの常駐量を見た |
| 画像 | 評価文書 05（冷却ライン CL-2 異常報告）の 1 ページ目の画像を 543×768 の PNG（40 KB）にして data URL で送信。プロンプト「この図の内容を日本語で 3〜5 文で説明してください。」、temperature 0、max_tokens 400 |

## Qwen2.5-VL-7B-Instruct-AWQ

| 試行 | 条件 | 結果 | 起動前 → 起動後（GPU 全体） |
|---|---|---|---|
| A | 全コンテナ稼働、compose のまま（KV 1500M） | 失敗: `Free memory on device cuda:0 (14.13/23.99 GiB) on startup is less than desired GPU memory utilization (0.92, 22.07 GiB)` | 19,720 MiB（変化なし） |
| B | A + `--gpu-memory-utilization=0.3` | **起動**（重みのダウンロード 95 秒を含め約 2.5 分） | 19,721 → 22,318 MiB（ピーク 23,762）、空き 1,821 MiB |

- 起動ログ: `Model loading took 6.67 GiB`、`GPU KV cache size: 27,424 tokens, Maximum concurrency for 8,192 tokens per request: 3.35x`。
- コンテナごとの常駐（カウンタ）: vllm-vl 9.7 GB、**Qwen3-8B は 4.8 GB に減っていた**（単独時は約 8.3 GB）。GPU 全体の増分が 2.6 GB しかないのは、WDDM が他コンテナの割り当ての一部を VRAM から追い出したため（共有 GPU メモリのカウンタは 0.6 GB 程度で、追い出し分は表に出ない）。
  - このとき Qwen3-8B の 300 トークン生成は 5.1〜8.1 秒（約 37〜58 トークン/秒）。後述の Qwen3-VL 同居時（2.3 秒）より明らかに遅く、追い出しの影響とみられる。
- 比較用 2 コンテナ（tei-rerank bge・tei-embed-ruri、計 約 2.6 GB）を止めても Qwen3-8B の速度は 5.1〜5.5 秒で変わらなかった（ユーザー確認のうえ停止。現在も停止中）。
- 疎通: `GET /v1/models` → `qwen2.5-vl`（max_model_len 8192）。
- 図の説明: **2.67 秒 / 2.22 秒**（入力 554、出力 90 トークン）。出力:

  > この図は、サンテックの冷却ラインCL-2異常報告書です。2026年5月21日14:35に第2工場で温度上昇と流量低下が同時発生したことを記録しています。一次対応として、添付図面の赤枠部位を交換候補として扱うことが提案されています。

## Qwen3-VL-8B-Instruct-FP8

`VLM_HF_MODEL=Qwen/Qwen3-VL-8B-Instruct-FP8 VLM_SERVED_NAME=qwen3-vl` で起動（main c78443c の compose、上記の `--gpu-memory-utilization` 追加あり）。Qwen3-8B（:8090）は止めていない。

| 試行 | 条件 | 結果 | 起動前 → 起動後（GPU 全体） |
|---|---|---|---|
| C | `VLM_MAX_LEN=16384`、KV 1500M | 失敗: `To serve at least one request with the model's max seq len (16384), (2.25 GiB KV cache is needed, which is larger than the available KV cache memory (1.46 GiB)` （推定最大長 10,640） | 13,460 MiB（ピーク 23,464） |
| — | `VLM_KV_BYTES=1000M` | 試していない。KV は 1 トークン 144 KiB なので 1000M では 16384（2.25 GiB）も 8192（1.13 GiB）も入らず、確実に同じエラーになる | — |
| D | `VLM_MAX_LEN=8192`、KV 1500M | **起動**（重みはキャッシュ済み。約 1 分） | 9,066 → 22,320 MiB（ピーク 23,136）、空き 1,819 MiB |

- 起動ログ: `Model loading took 10.12 GiB`、`GPU KV cache size: 10,656 tokens, Maximum concurrency for 8,192 tokens per request: 1.30x`。
- 安定後の常駐（カウンタ）: vllm-vl 10.2 GB、Qwen3-8B 8.4 GB、tei-embed 1.55 GB、tei-rerank-ruri 1.04 GB。GPU 全体 23,456 MiB、空き 683 MiB。docling-serve は 0.5 GB 未満に追い出されている（変換すると戻るはずだが、そのとき他が追い出される）。
- 疎通: `GET /v1/models` → `qwen3-vl`（max_model_len 8192）。
- 図の説明: **1.80 秒 / 1.75 秒**（入力 438、出力 146〜148 トークン）。Qwen2.5-VL より出力が長いのに速い。出力:

  > この図は、SUNTECH社の「冷却ライン CL-2 異常報告」の表紙です。発生日時は2026年5月21日14時35分、場所は第2工場と記載されています。異常内容は、冷却ラインCL-2で温度上昇と流量低下が同時に発生したものです。一次対応として、添付図面の赤枠部分の部品を交換候補として扱うことが決定されています。全体的に、製造現場での設備異常に関する正式な報告書の形式をとっています。

- ツール呼び出し: `tools=[get_weather(city)]`、`tool_choice=auto`、「東京の今日の天気を調べてください。」→ 0.27 秒、`finish_reason=tool_calls`、`get_weather({"city": "東京"})`、content は null。
- 同居中の他サービス: Qwen3-8B の 300 トークン生成 2.29〜2.30 秒（初回のみ 4.0 秒）、TEI 埋め込み 10 ms・rerank 12 ms（初回のみ 0.8〜1.1 秒）。初回だけ遅いのは追い出された割り当てを VRAM に戻すため。

## 気づき

1. **`--kv-cache-memory-bytes` だけでは他と同居できない**。起動時の空きチェックは `--gpu-memory-utilization`（既定 0.92）で行われる。:8090 の vllm が最初に起動できたのは、そのとき WSL から見えた空きが 22.45 GiB（他コンテナ分が見えていなかった）だったため。今回は 14.13 GiB と見えた。vllm（llm）にも同じ引数を入れておくと、起動順に左右されない。
2. **24 GB を超えても OOM にならず、WDDM が他コンテナの割り当てを VRAM から追い出す**。エラーにならない代わりに、追い出された側（今回は Qwen3-8B、docling）が遅くなる。`nvidia-smi` の合計だけでは分からないので、Windows のカウンタ `\GPU Process Memory(*)\Dedicated Usage` で見る必要がある。
3. GPU 機では Sunshine（ゲーム配信のホスト）が 1.4〜4.5 GB、dwm（画面）が 1.3〜1.4 GB を使っている。VLM と Qwen3-8B の同時常駐を本番相当で回すなら、これらを止めるか、入庫（VLM）と会話（Qwen3-8B）の時間を分けるのが安全。
4. Qwen3-VL-8B-FP8 で 16384 トークンにするには KV が 2.25 GiB 以上要る。今の同居構成では余地がないため 8192 にした。図の説明は 1 枚 500 トークン前後なので 8192 で足りる。

## 単モデル（Qwen3-8B を止め、Qwen3-VL-8B-FP8 だけを常駐）

会話と図の説明を Qwen3-VL 1 つで兼ねる案の試験。vllm（Qwen3-8B、:8090）を停止し、TEI（:8081・:8084）と docling-serve（:5001）は稼働したまま、文脈長と KV を大きくして起動した。

```
VLM_HF_MODEL=Qwen/Qwen3-VL-8B-Instruct-FP8 VLM_SERVED_NAME=qwen3-vl VLM_MAX_LEN=32768 VLM_KV_BYTES=6G VLM_GPU_UTIL=0.6 \
  docker compose -f compose.gpu.yaml --profile vlm up -d vllm-vl
```

| 試行 | 条件 | 結果 | 起動前 → 起動後（GPU 全体） |
|---|---|---|---|
| E | 32768 トークン、KV 6G、利用率チェック 0.6 | **初回で起動**（16384 や KV 4G/3G への引き下げは不要） | 2,961 → 20,932 MiB（空き 3,207 MiB） |

- 起動ログ: `Model loading took 10.13 GiB`、`GPU KV cache size: 43,680 tokens, Maximum concurrency for 32,768 tokens per request: 1.33x`。`/v1/models` → `qwen3-vl`（max_model_len 32768）。
- 起動前の 2,961 MiB は、Qwen3-8B 停止直後に TEI と docling の割り当てが VRAM から追い出されたままだったため（使うと戻る）。
- 300 トークン生成（日本語、`min_tokens=300`）: **3.51〜3.52 秒**（約 85 トークン/秒、3 回とも同じ）。同居時の Qwen3-8B-AWQ（2.3 秒）より遅い。
- TEI: 埋め込み 11 ms・rerank 21 ms（初回のみ 0.16〜0.20 秒）。
- docling: 文書 04（4 ページ）の変換が 6.83 秒 → 4.76 秒。G1 計測時（g1-gpu.md、2.06 秒）の 2 倍以上かかる。

変換後の常駐（`\GPU Process Memory(*)\Dedicated Usage`）:

| プロセス | 専用 VRAM |
|---|---|
| vllm-vl（Qwen3-VL、重み 10.1 GiB + KV 6 GiB + CUDA graph 等） | 17,853 MiB |
| docling-serve | 2,136 MiB（**変換で VRAM に戻った**） |
| tei-embed | 1,554 MiB |
| tei-rerank-ruri | 582 MiB（1,042 MiB から一部追い出し） |
| Sunshine（ゲーム配信のホスト。WSL 外） | **7,849 MiB** |
| dwm（画面） | 1,128 MiB |
| GPU 全体 | 23,931 MiB / 24,564 MiB（空き 約 0.2 GB）、共有 756 MiB |

- Qwen3-8B を止めて空いた約 8 GB は、ほぼ KV の拡大（1.5G → 6G）と Sunshine の増加（4.5 → 7.8 GB）で埋まった。Sunshine は配信中に大きく増えるため、同居させる限り VRAM の余裕は読めない。
- 結果として GPU は再び満杯で、TEI rerank の一部が追い出され、docling は遅い。単モデル構成で余裕を持たせるなら、KV を 3〜4G に下げる（32768 で 1 並列なら 4.5 GiB で足りる。3G なら 16384）か、Sunshine を止める。

### 単モデルの速度低下と KV 縮小（再計測）

KV 6G で起動直後は 300 トークン 3.5 秒（約 85 トークン/秒）だったが、その後 Mac から約 32 トークン/秒と報告があった。GPU 機で再計測すると同じく遅かった。

| 時点 | 条件 | 300 トークン（2 回） | GPU 全体（専用） |
|---|---|---|---|
| 縮小前 | 32768、KV 6G（起動から約 1 時間後） | 8.80 秒 / 8.70 秒（約 34 トークン/秒） | 23,694 MiB（空き 454 MiB） |
| F | 32768、`VLM_KV_BYTES=4500M` | 起動失敗: `4.5 GiB KV cache is needed, which is larger than the available KV cache memory (4.39 GiB)`（4500M は 4.19 GiB。M は MiB 単位） | — |
| G | 32768、`VLM_KV_BYTES=4700M` | **3.57 秒 / 3.55 秒**（約 85 トークン/秒に回復） | 22,221 MiB（空き 約 1.9 GB） |

- G の起動ログ: `GPU KV cache size: 33,408 tokens, Maximum concurrency for 32,768 tokens per request: 1.02x`（32768 の要求を 1 本だけ受けられる）。
- G のプロセス別（`\GPU Process Memory(*)\Dedicated Usage`）: vllm-vl 16,528 MiB、WSL のほかの割り当て（TEI・docling）1,472 / 1,426 / 978 MiB、dwm 1,214 MiB、Sunshine 14,864 MiB。
- **Sunshine のカウンタ値は常駐量ではない**。vllm-vl が止まっている間（F の後）も GPU 全体の専用使用量は 5.7 GB しかなかったのに、Sunshine は 14.9 GB と表示されていた。プロセス別カウンタは追い出された分も含む確保量とみられる。実際に VRAM に載っている量は GPU 全体の値（`\GPU Adapter Memory(*)\Dedicated Usage` か `nvidia-smi`）で見る。
- 遅くなった原因は、GPU 全体が 24 GB に張り付き（空き 0.45 GB）、vllm-vl の割り当ての一部が追い出されたためとみられる。Sunshine（ユーザーのリモートデスクトップ）の使用量は配信の状況で変わり、止められないため、空きを 1.5〜2 GB 残す設定（KV 4700M）にした。配信の負荷が増えれば再び遅くなりうる。
