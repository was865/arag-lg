# 004 検索（P2）— 要件

`docs/handoff.md` 第 3 節 P2。完了基準: **評価用 7 文書の題集で recall@5 が旧版（0.944〜1.0）以上**、かつ融合方式（RRF / 重み付き RRF / DBSF）と埋め込み・リランクのモデル（BGE-M3 系 / ruri-v3 系）の比較結果で既定値を決める。

前提: P1（`specs/003-ingestion/`）の索引（Qdrant `dense` + `bm25`、親セクション・子チャンク・文脈）。**本アプリは日本語に最適化するが、英語の文書・質問にも対応する**（UI は日本語のみ）。既定値は日本語の題集で決め、英語と日英をまたぐ検索（日本語の質問で英語の文書、またはその逆）で大きく劣らないことを確認する。エージェント（`search` ツール等）とストリームは P3。P2 は検索関数・管理用 API・評価基盤を作る。

## 1. 検索範囲と権限

- R1. システムは検索要求 `{query, kb_ids?, document_ids?, include_archived=false, block_types?, mode=hybrid|dense|keyword, top_k=6, candidate_k=50, include_section=false, must_contain?}` を受け、利用者（Principal）が閲覧できる範囲だけを検索する。
- R2. 検索対象 KB は「閲覧可・ごみ箱でない」KB のうち、アーカイブされていないもの。`include_archived=true` のとき、または `kb_ids` で明示したときはアーカイブ済みも含める（旧版と同じ意味）。`kb_ids` は閲覧可能な KB との積をとり、閲覧できない ID は黙って除く（存在を推測させない）。積が空なら 0 件を返す。
- R3. ごみ箱の文書・KB の内容は常に結果に出さない。`document_ids` を指定したときはその文書に限る（閲覧不可の ID は除く）。
- R4. 同じ内容（content_hash）が利用者の見える複数の文書にあるとき、各結果は利用者の見える文書を 1 つだけ指す（個人 KB の文書を優先し、次に作成日時の古いもの）。
- R5. アーカイブの切替で Qdrant の payload を書き換えない（payload の `kb_ids` はごみ箱でない KB をすべて持ち、アーカイブの判定は検索時のフィルタで行う）。既存の索引は一括同期コマンドで新しい形にそろえられる。

## 2. ハイブリッド検索と再順位付け

- R6. `mode=hybrid` のとき、システムはクエリを dense 埋め込み（TEI、モデル別のクエリ接頭辞つき）と Sudachi BM25 sparse（入庫と同じ分かち書き）に変換し、Qdrant Query API の 1 要求で両経路を prefetch（各 `candidate_k` 件）してサーバ側で融合する。融合方式は設定で選ぶ: RRF（既定 k=60、経路ごとの重み）または DBSF。
- R6a. sparse 経路の分かち書きは日本語を Sudachi で処理し、英数字の語は小文字化・NFKC 正規化して同じ語 ID にする（英語の語形変化の扱い〈ステミング有無〉は評価で決める）。文書側とクエリ側は同じ処理を使う。
- R7. `mode=dense` は dense 経路のみ、`mode=keyword` は sparse 経路のみで検索する（評価・型番検索用）。
- R8. `must_contain` が与えられたとき、システムは候補のうち本文（NFKC 正規化後）に全語を部分一致で含むものだけを残す（型番・条項番号の完全一致用。候補 `candidate_k` 件の中での絞り込み）。
- R9. システムは融合後の候補（最大 `candidate_k` 件）を TEI の rerank で採点し、上位 `top_k` 件を返す。rerank に渡す文は既定で「文脈 + 本文」とする（設定で本文のみに切替可）。
- R10. rerank が失敗（再試行後もタイムアウト・5xx・接続失敗）したとき、システムはエラーにせず融合順の上位 `top_k` 件を返し、結果に `degraded: ["rerank"]` を付けて警告ログを出す。
- R11. dense 埋め込みが失敗したとき、`mode=hybrid` は sparse 経路のみで続行し `degraded: ["dense"]` を付ける。Qdrant が失敗したときは 503（`search_unavailable`）を返す。
- R12. 同じ索引・同じ要求に対して結果の順序は決定的にする（同点は chunk_id 順）。

## 3. 結果

- R13. 各結果は `{chunk_id, document_id, document_name, kb_id, section_id, heading_path, page_start, page_end, block_type, text, context, boxes, score, fused_score, rank}` を持つ（`score` は rerank 後、縮退時は融合スコア）。
- R14. `include_section=true` のとき、各結果に親セクションの本文を付ける。同じセクションの結果が複数あるときは最初の結果だけに付け、以降は `section_id` で参照させる。
- R15. 結果には段階ごとの所要時間と件数（埋め込み・検索・rerank・本文取得）を持つ `trace` を付ける。`debug=true` のとき、dense のみ・sparse のみの上位一覧も同じ Qdrant 往復（バッチ問い合わせ）で取得して付ける（P3 のツール表示用）。
- R16. `query` が空白のみ・1,000 文字超のとき 422。`top_k` は 1〜50、`candidate_k` は `top_k`〜200。

## 4. API

- R17. `POST /v1/search` は R1 の要求を受け R13〜R15 の結果を返す。admin（owner を含む）のみ、それ以外は 403（評価・診断用。エージェントは同じ関数を直接呼ぶ）。

## 5. 評価

- R18. 評価題集は `eval/suites/<名前>/golden.yaml`（旧版互換: `documents`・`thresholds`・`cases[{id, query, top_k, tags, relevant_documents, key_facts[{any}]}]`）で管理する。
- R19. `python -m arag.eval ingest --suite S` は題集の文書を専用の全社 KB（`評価: S`）へ API 経由で入庫し、完了まで待つ（既に ready なら何もしない）。
- R20. `python -m arag.eval run --suite S [--variant V ...] [--gate] [--out FILE]` は各ケースを検索関数で実行し、文書単位の recall@5・recall@k・precision@k・MRR・nDCG@k、fact_coverage（結果本文 + 親セクション本文に key_facts が出るか）、検索の p50 / p95 所要時間を出す。`--gate` で閾値を下回ったら終了コード 1。
- R21. 比較条件（variant）は `eval/variants.yaml` に名前付きで定義する（mode・融合方式・重み・rerank 有無・rerank 入力・埋め込みモデル・文脈有無・コレクション）。複数 variant を指定すると比較表（Markdown）を出す。
- R22. `python -m arag.eval index --variant V` は Postgres に保存済みの子チャンク（本文・文脈）から、variant の埋め込みモデル・文脈有無で別コレクションを作る（再解析・再文脈付与をしない）。本番のコレクション・エイリアスには触れない。
- R23. 題集は次の 4 つ: `agentic_rag_demo`（旧版 6 問の移植）、`agentic_rag_demo_ext`（7 文書から LLM で候補を作り人が選んだ 50 問以上。型番・条項番号の完全一致、複数文書の比較、多段推論、例外・版の衝突、該当なし、**英語の質問で日本語の文書を引く 5 問以上** を含む）、日本語の公開データセットの部分集合 1 つ、英語の公開データセットの部分集合 1 つ（旧版の BEIR SciFact を移植）。公開データはライセンスを確認し、実行時に取得してリポジトリに入れない。
- R24. variant ごとの基準値（aggregate）を `eval/suites/<名前>/baselines/<variant>.json` に保存し、レポートに差分を出す（ゲートは題集の thresholds で行う）。

## 完了の確認（GPU 機の TEI・Mac の Qdrant で実行）

- E1. 既定設定（bge-m3 + bge-reranker-v2-m3 + RRF k=60、rerank 入力は文脈 + 本文）で `agentic_rag_demo` の recall@5 ≥ 0.944・fact_coverage ≥ 0.90。
- E2. `agentic_rag_demo_ext` と公開データセットの部分集合で、dense のみ / keyword のみ / RRF / 重み付き RRF / DBSF、rerank 有無、文脈有無、bge-m3 と ruri-v3-310m（埋め込み）、bge と ruri（rerank）の比較表を作り、既定値の決定を `specs/000-overview/decisions.md` に記録する。
- E2a. 英語の題集（SciFact 部分集合）と日英をまたぐケースで、既定設定が比較対象の最良値から大きく劣らない（目安: nDCG@10 の差 0.05 以内）。日本語特化モデル（ruri）を既定にする場合は、この条件を満たすことを必須とする。
- E3. 既定設定・`top_k=6`・`candidate_k=50` で、検索の p50 ≤ 300 ms・p95 ≤ 800 ms（初回呼び出しを除く）。
- E4. 他人の個人 KB・ごみ箱の文書が結果に出ず、アーカイブ済み KB は R2 の条件のときだけ出る（integration テスト）。
