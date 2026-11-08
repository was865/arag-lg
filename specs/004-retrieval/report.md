# 004 検索（P2）— 実データでの結果（中間報告）

2026-11-08。Mac（compose: api / worker / postgres / qdrant / redis）+ GPU 機（TEI: bge-m3 :8081、bge-reranker-v2-m3 :8082、ruri-v3-310m :8083、ruri-v3-reranker-310m :8084、docling-serve :5001）。
数値は `eval/.reports/<題集>/compare.md`、基準値は `eval/suites/<題集>/baselines/`。nDCG・recall はチャンクを文書単位にたたんだ順位で数える（`runner.ranked_documents`）。

## 1. 題集

| 題集 | 言語 | 文書 | 問数 | 状態 |
|---|---|---|---|---|
| `agentic_rag_demo` | ja | PDF 7 | 6 | 旧版を移植 |
| `agentic_rag_demo_ext` | ja 46 / en 18（negative 5 を含む） | 同上 | 69 | LLM 候補 → 一次選別済み。**ユーザー確認待ち**（C6） |
| `beir_scifact` | en | 抄録 1,500 | 300 | BEIR SciFact test の部分集合（関連文書 + ID 順の先頭） |
| `jqara` | ja | 9,953（質問ごとの候補 100 件をまとめたもの） | 100 | hotchpotch/JQaRA test の先頭 100 問 |
| `jqara_en` / `scifact_ja` | en→ja / ja→en | 元の KB を共有 | — | 質問を DeepSeek で訳す題集。**残高不足で未作成**（§5） |

- `agentic_rag_demo_ext`: `python -m arag.eval.synth` で文書ごとに 8 問（fact・exact_id・multi_hop・paraphrase・english）と横断 13 問（cross_doc 8・negative 5）を生成。LLM が key_facts を「全部必要な語の列」として返したので 1 語ずつの事実に分け、質問に出る語・一般語（「あり」「なし」等）を除き、全事実が原文にあることを機械確認した。指示語だけの質問（「この文書の申請番号」等）4 問は文書名を入れて書き直した。候補の原本は `candidates.yaml`。
- 正解文書の無い題（negative）は検索指標を持たず集計から除く（回答側の評価 P3 で使う）。題集にタグ `ja` / `en` が混ざるときはタグ別の比較表も出す。

## 2. 比較（nDCG@10・recall@5、p50 / p95 ms）

### beir_scifact（英語）

| variant | nDCG@10 | recall@5 | p50 / p95 |
|---|---|---|---|
| default（bge-m3 + bge-reranker、RRF k=60） | 0.829 | 0.871 | 297 / 435 |
| no_rerank | 0.784 | 0.841 | 32 / 41 |
| dense_only / keyword_only（rerank あり） | 0.814 / 0.815 | 0.862 / 0.861 | |
| rrf_dense2 / rrf_sparse2 / dbsf | 0.830 / 0.828 / 0.829 | 0.871 / 0.875 / 0.870 | |
| rerank_text_only | 0.801 | 0.848 | |
| en_stem | 0.828 | 0.873 | |
| ruri_embed | 0.826 | 0.871 | |
| **ruri_rerank** | **0.843** | **0.902** | 452 / 512 |
| ruri_both | 0.843 | 0.902 | 460 / 518 |

### jqara（日本語）

| variant | nDCG@10 | recall@5 | p50 / p95 |
|---|---|---|---|
| default | 0.703 | 0.402 | 195 / 227 |
| no_rerank | 0.588 | 0.336 | 33 / 42 |
| dense_only / keyword_only（rerank あり） | 0.705 / 0.674 | 0.405 / 0.384 | |
| rrf_dense2 / rrf_sparse2 / dbsf | 0.706 / 0.702 / 0.702 | | |
| rerank_text_only | 0.693 | 0.402 | |
| en_stem | 0.704 | 0.402 | |
| ruri_embed | 0.708 | 0.402 | |
| **ruri_rerank** | **0.830** | **0.498** | 179 / 211 |
| **ruri_both** | **0.852** | **0.513** | 176 / 203 |

JQaRA の recall@5 が低いのは 1 問あたり正解文書が平均 5 件超あり、上位 5 件に全部は入らないため（MRR は 0.90 前後）。

### agentic_rag_demo / agentic_rag_demo_ext

ハイブリッド系の全 variant が recall@5 = 1.0（文書 7 件では差が出ない）。ext の英語の題（18 問）では **keyword のみ が recall@5 0.85・fact 0.69** に落ち、英語の質問を日本語文書に当てるには dense 経路が要ることを確認した。ruri_embed / ruri_both も ext の英語の題で 1.0（文書が少なく判別力は弱い）。

## 3. 分かったこと

1. **rerank は必須**: 外すと nDCG が SciFact −0.045、JQaRA −0.115。所要時間の大半は rerank（30 ms → 200〜300 ms）。
2. **融合方式・重みは効かない**: RRF k=60 等重み・dense 2 倍・sparse 2 倍・DBSF の差は ±0.004 以内。既定は RRF k=60・等重みのまま。
3. **rerank 入力は文脈 + 本文**: 本文だけにすると SciFact −0.028、JQaRA −0.010。
4. **英語ステミングは効かない**（±0.001）。`SPARSE_EN_STEM=false` のまま。
5. **ruri-v3-reranker-310m が bge-reranker-v2-m3 より良い**: JQaRA +0.127、英語の SciFact でも +0.014。JQaRA は日本語 reranker の評価で広く使われる題集で、学習データとの重なりによる上振れの可能性は確認していない点に注意（SciFact でも勝っているので、英語で劣ることはない）。
6. **埋め込みの差は rerank 後は小さい**: ruri_embed は bge-m3 と ±0.005。ruri_both は JQaRA で ruri_rerank より +0.022。埋め込みの変更は全量の再索引が要り、日英をまたぐ検索（bge-m3 は多言語学習、ruri は日本語中心）を未検証なので、今は変えない。
7. **E3（p50 ≤ 300 ms・p95 ≤ 800 ms）**: 既定で JQaRA 195 / 227、SciFact 297 / 435 で満たす（SciFact は抄録が長く rerank の入力が長い。測定時は入庫ワーカーが同じ TEI を使っていた）。ruri reranker は SciFact で 452 / 512 と p50 を超える。`candidate_k=50` は変えない。

## 4. 既定値の判断

- 確定: RRF k=60・重み `1,1`、rerank 有効・入力は文脈 + 本文、`SPARSE_EN_STEM=false`、`candidate_k=50`、埋め込み bge-m3。
- **保留（推奨は ruri-v3-reranker-310m）**: 品質は両言語で上だが、(a) 日英をまたぐ題集（`jqara_en`・`scifact_ja`）が未作成、(b) 長い英語文書で p50 が E3 を超える。(a) を確認し、(b) は rerank 入力の文字数に上限を設けるか p50 の目安を見直すかを決めてから切り替える。切り替えは `ARAG_TEI_RERANK_URL` を :8084 に向けるだけ（再索引不要）。

## 5. 問題: DeepSeek の残高切れ（文脈の比較が無効）

入庫の並列を 32 に上げた直後（11:39 UTC）に DeepSeek が `402 Insufficient Balance` を返し始め、以降の文脈付与はすべて既定の見出し文脈（`ファイル名 > タイトル`）に縮退した（R20 のとおり入庫自体は ready）。

| KB | LLM 文脈 | 見出しのみ |
|---|---|---|
| 評価: agentic_rag_demo | 25 | 0 |
| 評価: beir_scifact | 697 | 1,037 |
| 評価: jqara | 32 | 9,921 |

このため **文脈の有無（no_context）と、英語文書に日本語の文脈を付ける是非（design §10-4）は公開データでは判断できない**。残高を補充したら次を行う:

1. `cli reindex --content-hash …`（見出し文脈だけの内容）で文脈を付け直す（概算 1.1 万回の呼び出し）。
2. `prepare --suite jqara_en` / `scifact_ja`（訳 400 問）。
3. 4 題集 + 訳 2 題集で再比較し、基準値を保存し直す（今の `beir_scifact` / `jqara` の基準値は文脈が欠けた状態のもの）。

運用上の課題: 残高切れのような「全件失敗」でも入庫は黙って ready になる。文脈付与の失敗率が高いときに警告・停止する仕組みを P1 の追補として検討する。

## 6. 補足

- Qdrant の IDF（sparse の BM25）はコレクション全体で計算されるので、評価用 KB が同じコレクションに入ると本番の IDF も変わる。評価は開発環境だけで行う前提。
- 入庫の所要時間: 並列 8 で約 30 件/分（LLM 文脈待ち）、32 で約 700 件/分（残高切れ後の見出し文脈のみ。LLM ありの実効値は未測定）。
