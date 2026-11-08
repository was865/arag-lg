# 004 検索（P2）— タスク

各タスクは先に失敗するテストを書いてから実装する。「Mac」は開発機、「Win」は GPU 機（TEI・docling-serve）。

## A. 索引側の準備

- [x] A1 Mac: `SparseEncoder` v2（英字語は表層の小文字、英語の機能語を除く、カタカナ化しない、型番保護は維持、`sparse_en_stem`）— R6a
- [x] A2 Mac: `TeiEmbedder` にクエリ・文書の接頭辞を追加し、入庫でも使う — R6
- [x] A3 Mac: payload の `kb_ids` / `document_ids` にアーカイブ済み KB を含める（`live_refs`）、アーカイブ切替で同期しない、`cli sync-payload --all` — R5
- [x] A4 Mac: 実データを `cli reindex`（sparse v2）と `sync-payload` で更新

## B. 検索関数

- [x] B1 Mac: `SearchRequest` の検証（空白・長さ・top_k・candidate_k）— R16
- [x] B2 Mac: `resolve_scope`（閲覧可・ごみ箱除外・アーカイブ条件・`kb_ids` / `document_ids` の積）— R1〜R3
- [x] B3 Mac: `build_query`（フィルタ・prefetch・RRF〈k・重み〉/ DBSF・単経路）— R6・R7
- [x] B4 Mac: `TeiReranker`（32 件ずつ・順序復元・再試行・失敗）— R9
- [x] B5 Mac: `search()`: hydrate・見える文書の選択・must_contain・rerank・縮退（rerank / dense）・決定的順序・trace — R4・R8〜R13・R15（integration）
- [x] B6 Mac: `include_section`（親セクション本文、重複排除）— R14
- [x] B7 Mac: `debug=true` の単経路一覧（batch 1 往復）— R15
- [x] B8 Mac: `POST /v1/search`（admin のみ、403、OpenAPI → TS 型の再生成）— R17

## C. 評価基盤

- [x] C1 Mac: `eval/dataset.py`・`metrics.py` を旧版から移植（旧版のテストも移植）— R18・R20
- [x] C2 Mac: `runner.py`（文書順位へのたたみ・セクション本文込みの fact_coverage・p50/p95）と `report.py`（差分・比較表・ゲート）— R20・R24
- [x] C3 Mac: `__main__.py` の `ingest` / `run`、`agentic_rag_demo` 題集の移植 — R19・R23
- [x] C4 Mac: `variants.yaml` と `index --variant`（Postgres の子チャンクから別コレクション）— R21・R22
- [x] C5 Mac: `public.py`: `beir_scifact` 部分集合（旧 `beir.py` 移植）と日本語公開データ 1 つ（ライセンス確認・decisions に記録）— R23
- [ ] C6 Mac+ユーザー: `agentic_rag_demo_ext` の候補を LLM で作成 → 一次選別 → **ユーザー確認** → 50 問以上で確定（英語質問 5 問以上）— R23
  - 69 問を一次選別済み（`eval/suites/agentic_rag_demo_ext/golden.yaml`）。ユーザー確認待ち

## D. 実データでの比較（Mac + Win）

- [x] D1 E1: 既定設定で `agentic_rag_demo` をゲート付きで実行
- [x] D2 E2・E2a: 4 題集 × variant の比較表を作成、既定値を決めて `decisions.md` と本書 §7 に反映
  - 文脈は GPU 機の Qwen3-8B で付け直して比較（report.md §5）。rerank は ruri-v3-reranker-310m に決定
- [x] D3 E3: 所要時間の測定（p50 / p95）、必要なら `candidate_k` を調整
- [x] D4 結果を `specs/004-retrieval/report.md` にまとめる
- [x] D5 rerank の既定を ruri-v3-reranker-310m に切り替える: `compose.gpu.yaml` の既定 reranker、`eval/variants.yaml` の対応、基準値の保存し直し。SciFact の p50 超過に備えて rerank 入力の文字数上限を検討
