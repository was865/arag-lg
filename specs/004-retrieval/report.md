# 004 検索（P2）— 実データでの結果

2026-11-08〜09。Mac（compose: api / worker / postgres / qdrant / redis）+ GPU 機（TEI: bge-m3 :8081、bge-reranker-v2-m3 :8082、ruri-v3-310m :8083、ruri-v3-reranker-310m :8084、docling-serve :5001、vLLM Qwen3-8B-AWQ :8090）。
数値は `eval/.reports/<題集>/compare.md`、基準値は `eval/suites/<題集>/baselines/`。nDCG・recall はチャンクを文書単位にたたんだ順位で数える（`runner.ranked_documents`）。

## 1. 題集

| 題集 | 言語 | 文書 | 問数 | 状態 |
|---|---|---|---|---|
| `agentic_rag_demo` | ja | PDF 7 | 6 | 旧版を移植 |
| `agentic_rag_demo_ext` | ja 46 / en 18（negative 5 を含む） | 同上 | 69 | LLM 候補 → 一次選別済み。**ユーザー確認待ち**（C6） |
| `beir_scifact` | en | 抄録 1,500 | 300 | BEIR SciFact test の部分集合（関連文書 + ID 順の先頭） |
| `jqara` | ja | 9,953（質問ごとの候補 100 件をまとめたもの） | 100 | hotchpotch/JQaRA test の先頭 100 問 |
| `jqara_en` / `scifact_ja` | en→ja / ja→en | 元の KB を共有 | 100 / 300 | 質問を Qwen3-8B で訳した題集 |

- `agentic_rag_demo_ext`: `python -m arag.eval.synth` で文書ごとに 8 問（fact・exact_id・multi_hop・paraphrase・english）と横断 13 問（cross_doc 8・negative 5）を生成。LLM が key_facts を「全部必要な語の列」として返したので 1 語ずつの事実に分け、質問に出る語・一般語（「あり」「なし」等）を除き、全事実が原文にあることを機械確認した。指示語だけの質問（「この文書の申請番号」等）4 問は文書名を入れて書き直した。候補の原本は `candidates.yaml`。
- 正解文書の無い題（negative）は検索指標を持たず集計から除く（回答側の評価 P3 で使う）。題集にタグ `ja` / `en` が混ざるときはタグ別の比較表も出す。

## 2. 比較（nDCG@10・recall@5、p50 / p95 ms）

文脈はすべて GPU 機の Qwen3-8B-AWQ で付け直した後の値（§5）。基準値は `eval/suites/<題集>/baselines/` に保存済み。

### beir_scifact（英語）

| variant | nDCG@10 | recall@5 | p50 / p95 |
|---|---|---|---|
| default（bge-m3 + bge-reranker、RRF k=60） | 0.820 | 0.877 | 277 / 311 |
| no_context | 0.820 | 0.886 | |
| no_rerank | 0.778 | 0.832 | 33 / 42 |
| dense_only / keyword_only（rerank あり） | 0.796 / 0.809 | 0.859 / 0.866 | |
| rrf_dense2 / dbsf | 0.817 / 0.820 | 0.881 / 0.881 | |
| rerank_text_only | 0.801 | 0.857 | |
| en_stem | 0.802 | 0.861 | |
| ruri_embed | 0.824 | 0.879 | |
| **ruri_rerank** | **0.838** | **0.905** | 323 / 370 |
| ruri_both | 0.845 | 0.910 | 325 / 366 |

### jqara（日本語）

| variant | nDCG@10 | recall@5 | p50 / p95 |
|---|---|---|---|
| default | 0.699 | 0.400 | 150 / 179 |
| no_context | 0.694 | 0.396 | 163 / 185 |
| no_rerank | 0.584 | 0.326 | 32 / 46 |
| dense_only / keyword_only（rerank あり） | 0.707 / 0.672 | 0.407 / 0.387 | |
| rrf_dense2 / dbsf | 0.701 / 0.701 | 0.400 / 0.400 | |
| rerank_text_only | 0.694 | 0.401 | |
| en_stem | 0.698 | 0.400 | |
| ruri_embed | 0.702 | 0.402 | |
| **ruri_rerank** | **0.830** | **0.501** | 174 / 206 |
| ruri_both | 0.841 | 0.506 | 175 / 204 |

JQaRA の recall@5 が低いのは 1 問あたり正解文書が平均 5 件超あり、上位 5 件に全部は入らないため（MRR は 0.89 前後）。

### jqara_en（英語の質問 → 日本語の文書、E2a）

| variant | nDCG@10 | recall@5 | p50 / p95 |
|---|---|---|---|
| default | 0.527 | 0.297 | 129 / 169 |
| no_context | 0.530 | 0.299 | |
| no_rerank | 0.281 | 0.164 | 29 / 37 |
| dense_only / keyword_only | 0.546 / **0.179** | 0.301 / 0.099 | |
| ruri_embed | 0.564 | 0.319 | |
| **ruri_rerank** | **0.646** | **0.368** | 155 / 183 |
| ruri_both | 0.685 | 0.399 | 156 / 182 |

### scifact_ja（日本語の質問 → 英語の文書、E2a）

| variant | nDCG@10 | recall@5 | p50 / p95 |
|---|---|---|---|
| default | 0.786 | 0.858 | 210 / 238 |
| no_context | 0.773 | 0.843 | |
| no_rerank | 0.686 | 0.748 | 31 / 41 |
| dense_only / keyword_only | 0.779 / 0.740 | 0.851 / 0.791 | |
| ruri_embed | 0.793 | 0.868 | |
| **ruri_rerank** | **0.839** | **0.879** | 281 / 315 |
| ruri_both | 0.849 | 0.892 | 288 / 317 |

訳題集の質問は Qwen3-8B で訳した（`eval/.cache/<題集>/translations.json`。中国語の混入 1 件を手で直した）。訳の質の分だけ元の題集より下がる。

### agentic_rag_demo / agentic_rag_demo_ext

ハイブリッド系の全 variant が recall@5 = 1.0（文書 7 件では差が出ない）。ext の英語の題（18 問）では **keyword のみ が recall@5 0.85・fact 0.69** に落ち、英語の質問を日本語文書に当てるには dense 経路が要ることを確認した。ruri_embed / ruri_both も ext の英語の題で 1.0（文書が少なく判別力は弱い）。

## 3. 分かったこと

1. **rerank は必須**: 外すと nDCG が SciFact −0.042、JQaRA −0.115、日英をまたぐと −0.10〜−0.25。所要時間の大半は rerank（30 ms → 150〜300 ms）。
2. **融合方式・重みは効かない**: RRF k=60 等重み・dense 2 倍・DBSF の差は ±0.003 以内。既定は RRF k=60・等重みのまま。
3. **rerank 入力は文脈 + 本文**: 本文だけにすると SciFact −0.019、JQaRA −0.005。
4. **英語ステミングは効かない**（SciFact −0.018、JQaRA −0.001）。`SPARSE_EN_STEM=false` のまま。
5. **ruri-v3-reranker-310m が 4 題集すべてで bge-reranker-v2-m3 より良い**: JQaRA +0.131、SciFact +0.018、jqara_en +0.119、scifact_ja +0.053。日本語中心のモデルだが日英をまたぐ検索でも劣らず、むしろ差が大きい。JQaRA は日本語 reranker の評価で広く使われる題集で学習データとの重なりの可能性は確認していないが、他の 3 題集でも勝っている。
6. **日英をまたぐ検索は dense が支える**: jqara_en の keyword のみは nDCG 0.179（default 0.527）。sparse は語が一致しないので効かないが、RRF で混ぜても default は dense のみ（0.546）より −0.019 にとどまる。
7. **埋め込みの差は rerank 後は小さいが、日英をまたぐと開く**: ruri_embed は単一言語で bge-m3 と ±0.005、jqara_en で +0.037、scifact_ja で +0.007。ruri_both は全題集で最良（ruri_rerank より +0.007〜+0.039）。
8. **文脈（contextual retrieval）は効果が小さい**: no_context との差は SciFact ±0.000、JQaRA +0.005、jqara_en −0.003、scifact_ja +0.013。英語文書に日本語の文脈を付けると日本語の質問（scifact_ja）でわずかに上がり、英語の質問（SciFact）は下がらない。
9. **E3（p50 ≤ 300 ms・p95 ≤ 800 ms）**: bge-reranker の既定では全題集で満たす。ruri reranker は SciFact だけ p50 323 ms（抄録が長く rerank の入力が長い）。それ以外は 155〜288 ms。

## 4. 既定値の判断

- 確定: RRF k=60・重み `1,1`、rerank 有効・入力は文脈 + 本文、`SPARSE_EN_STEM=false`、`candidate_k=50`。
- **rerank モデル: ruri-v3-reranker-310m に切り替える**。品質の差（+0.02〜+0.13）が大きく、日英をまたぐ題集でも上。SciFact の p50 超過（+23 ms）は長い英語文書だけで起きるので、rerank 入力の文字数上限で抑える（後続タスク）。再索引は不要。切り替えは `compose.gpu.yaml` の既定 reranker のモデル入れ替えと、`eval/variants.yaml` の対応（`default` が指すモデル）を合わせて行う（tasks D5）。`ARAG_TEI_RERANK_URL` だけを :8084 に向けると評価の `default` が ruri を指したまま bge の名前で記録されるので避ける。
- **埋め込み: bge-m3 のまま（ruri-v3-310m は候補）**。ruri_both は ruri_rerank より最大 +0.039（jqara_en）良いが、切り替えには全量の再索引が要る。本番データが入る前（P3 以降の早い段階）に、実文書の題集（`agentic_rag_demo_ext` 確定後）でも確認してから決める。
- **文脈: 有効のまま（日本語の文脈・英語文書にも日本語）**。効果は小さいが下がる題集はなく、日本語の質問から英語文書を探すときに効く。

## 5. 文脈付与モデル: DeepSeek の残高切れとローカル LLM

入庫の並列を 32 に上げた直後（2026-11-08 11:39 UTC）に DeepSeek が `402 Insufficient Balance` を返し始め、以降の文脈付与はすべて見出し文脈（`ファイル名 > タイトル`）に縮退した（R20 のとおり入庫自体は ready）。JQaRA は 99.7%、SciFact は 60% が見出し文脈になった。

代わりに GPU 機で **vLLM + Qwen3-8B-AWQ**（Apache-2.0、思考無効）を立て、`cli reindex --heading-context` で見出し文脈だけの内容を付け直した。

- 設定: `ARAG_CONTEXT_MODEL=openai:qwen3-8b`、`ARAG_CONTEXT_BASE_URL=http://<GPU機>:8090/v1`、`ARAG_CONTEXT_MODEL_KWARGS`（temperature・max_tokens・`extra_body.chat_template_kwargs.enable_thinking=false`）、`ARAG_CONTEXT_MAX_DOCUMENT_TOKENS=12000`（KV キャッシュ 1.8 万トークンに収める）。
- 速度: 入庫の並列 32 で約 540 件/分・失敗 0（約 1.08 万チャンク / 20 分）。
- 質（`python -m arag.eval.ctxbench`、題集ごと 10 文書を DeepSeek の文脈と並べた）: 出力は安定しているが、DeepSeek より具体性が低く（文書名・数値を落としがち）、英語の専門語を日本語にするときに誤訳がある（例: 薬品名のカナ書き崩れ）。
- 検索への影響: §3-8 のとおり文脈そのものの効果が小さく、モデルの差は検索指標には出なかった。

結論: **開発・評価ではローカルの Qwen3-8B で十分**。本番の既定モデルは P3 以降の回答品質の評価と合わせて決める（文脈の質は回答の引用表示にも出るため）。

運用上の課題: 残高切れのような「全件失敗」でも入庫は黙って ready になる。文脈付与の失敗率が高いときに警告・停止する仕組みを P1 の追補として検討する。

再索引でチャンク ID が変わると variant 用の別コレクションが古くなり、`no_context` の値が 0.250 / 0.006 になる事故があった。`run` の前に DB のチャンク ID とコレクションの点を照合し、ずれていれば止めるようにした（`variants.collection_drift`）。

## 6. rerank の切り替え後（D5、2026-11-09）

`default` を ruri-v3-reranker-310m にして全題集を測り直し、基準値を保存し直した（旧既定は variant `bge_rerank`）。nDCG@10、p50 / p95 ms:

| 題集 | default（ruri rerank） | bge_rerank | no_context | ruri_embed（埋め込みも ruri） | default の p50 / p95 |
|---|---|---|---|---|---|
| beir_scifact | 0.840 | 0.820 | 0.842 | 0.846 | 304 / 335 |
| jqara | 0.830 | 0.699 | 0.819 | 0.842 | 147 / 172 |
| jqara_en | 0.645 | 0.527 | 0.654 | 0.685 | 159 / 180 |
| scifact_ja | 0.839 | 0.786 | 0.820 | 0.849 | 232 / 264 |
| agentic_rag_demo / _ext | recall@5 1.0 | 1.0 | | | 96 / 112 |

- 文脈の効果は rerank を変えても小さく、向きもまちまち（−0.009〜+0.019）。有効のまま。
- **rerank 入力の文字数上限**（`ARAG_RERANK_MAX_CHARS`、variant `rerank_cap1000` / `rerank_cap2000`）: SciFact で 2000 字は nDCG −0.002・p50 −9 ms、1000 字は −0.018・−60 ms。日本語のチャンク（最大 512 トークン）にはほぼ効かない。既定は上限なし（0）。SciFact の p50 は測るたびに 292〜323 ms と揺れ、E3（300 ms）の境目にある（GPU 機で vLLM も同居するため）。超えが続くなら 2000 字にする。
- GPU 機の `compose.gpu.yaml` は rerank の既定サービスを ruri（:8084）にし、bge（:8082）と ruri 埋め込み（:8083）を profile `compare` に回した。ポートの意味は変えていない。

## 7. 補足

- Qdrant の IDF（sparse の BM25）はコレクション全体で計算されるので、評価用 KB が同じコレクションに入ると本番の IDF も変わる。評価は開発環境だけで行う前提。
- 入庫の所要時間: 並列 8 で約 30 件/分（LLM 文脈待ち）、32 で約 700 件/分（残高切れ後の見出し文脈のみ。LLM ありの実効値は未測定）。
