# 004 検索（P2）— 設計

要件: `requirements.md`。版・ライセンスの確認は `specs/000-overview/decisions.md` §3（Qdrant Query API）・§5（TEI・モデル）。

## 1. 全体の流れ

```
SearchRequest ─▶ scope.resolve()          … Postgres: 検索対象 KB・文書 ID（R1〜R4）
              ─▶ encode query             … TEI /embed（dense, 接頭辞つき）‖ SparseEncoder.encode_query
              ─▶ Qdrant query_points      … prefetch[dense, bm25] + RRF/DBSF（1 往復。debug 時は batch で単経路も）
              ─▶ hydrate                  … Postgres: chunks + sections + documents（本文・文脈・boxes・見える文書）
              ─▶ must_contain 絞り込み
              ─▶ rerank                   … TEI /rerank（32 件ずつ分割、失敗時は縮退）
              ─▶ SearchResult{hits, trace, degraded}
```

検索はエージェントのツール（P3）と `POST /v1/search` と評価ランナーが共有する 1 つの関数 `search(session, deps, principal, req)`。

## 2. モジュール

| パス | 役割 |
|---|---|
| `search/schemas.py` | `SearchRequest`（pydantic、R16 の検証）、`SearchHit`、`SearchTrace`、`SearchResult` |
| `search/scope.py` | `resolve_scope(session, principal, req) -> Scope{kb_ids, document_ids|None, doc_pref}`。閲覧可能 KB（P1 の `permissions`）∩ 指定、アーカイブ条件（R2） |
| `search/query.py` | Qdrant 要求の組み立て（純関数）: フィルタ・prefetch・融合。`build_query(scope, dense, sparse, cfg)` |
| `search/rerank.py` | `Reranker` Protocol、`TeiReranker`（`/rerank`、`raw_scores=false`、`truncate=true`、32 件ずつ、408/429/5xx/接続は再試行）、`RerankError` |
| `search/service.py` | `search()`。段階の計時・縮退（R10・R11）・決定的な並び（R12） |
| `search/router.py` | `POST /v1/search`（admin） |
| `search/config.py` | `SearchConfig`（Settings から作る。variant で上書き可） |
| `eval/` | 題集・指標・実行・比較表・variant 索引（§6） |

`ingest/embedder.py` の `TeiEmbedder` にクエリ・文書の接頭辞（`embed_query_prefix` / `embed_document_prefix`。ruri は「検索クエリ: 」「検索文書: 」、bge-m3 は空）を追加する。入庫も同じ設定を使う。

## 3. Qdrant 要求

```python
flt = Filter(must=[
    FieldCondition(key="kb_ids", match=MatchAny(any=scope.kb_ids)),
    *([FieldCondition(key="document_ids", match=MatchAny(any=scope.document_ids))] if scope.document_ids else []),
    *([FieldCondition(key="block_type", match=MatchAny(any=req.block_types))] if req.block_types else []),
])
prefetch = [
    Prefetch(query=dense, using="dense", limit=ck, filter=flt),
    Prefetch(query=SparseVector(...), using="bm25", limit=ck, filter=flt),
]
query = RrfQuery(rrf=Rrf(k=cfg.rrf_k, weights=cfg.weights))   # 既定 k=60, weights=[1,1]
     |  FusionQuery(fusion=Fusion.DBSF)
client.query_points(alias, prefetch=prefetch, query=query, limit=ck, with_payload=["content_hash","section_id","document_ids"])
```

- `mode=dense|keyword` は prefetch を使わず単経路を `query_points(using=...)` で引く。
- `debug=true` は `query_batch_points` で [融合, dense のみ, sparse のみ] を 1 往復で取る（R15）。
- payload に本文は持たない（P1 のまま）。本文・文脈・boxes は hydrate で Postgres から取る（候補 50 件を 1 クエリ）。

### 3.1 アーカイブの扱いの変更（R5）

P1 では payload の `kb_ids` / `document_ids` を「生存かつアクティブな KB」に限っていた。P2 で **「ごみ箱でない KB（アーカイブ含む）」** に広げ、アーカイブの判定は `scope.kb_ids` 側で行う。

- `ingest/index.py` の `live_refs` の条件から `status == 'active'` を外す。
- KB のアーカイブ・解除で payload 同期を呼ばない（呼んでも結果は変わらないので残してよいが、不要な書込を避けるため外す）。
- 既存索引は `python -m arag.cli sync-payload --all` で一括同期（新規コマンド。content_hash ごとに `live_refs` → `set_refs`）。

### 3.2 見える文書の選択（R4）

hydrate で `documents` を `content_hash IN (...) AND kb_id IN scope.kb_ids AND deleted_at IS NULL [AND id IN document_ids]` で引き、content_hash ごとに「個人 KB の文書 → created_at の古い順」で 1 件選ぶ。該当が無い候補（payload 同期の遅れ）は捨てる。

## 4. sparse の分かち書き（R6a）

現状の `SparseEncoder` は Sudachi の `normalized_form` を使うため、**英語の語がカタカナに変わる**（"Running"→「ランニング」、"The"→「ザ」、"were"→「ワー」）。英語の文書・質問で BM25 が機能しない。

変更（`SPARSE_VERSION = "sudachi-bm25-v2"`、`cli reindex` で再生成）:

| 形態素 | 語 |
|---|---|
| 表層が英字を含む ASCII 語（`[A-Za-z][A-Za-z0-9'\-]*`） | 表層を NFKC・小文字化。英語の機能語（a, an, the, of, to, is, were … 約 120 語、`ingest/stopwords_en.txt`）は捨てる。ステミングは設定 `sparse_en_stem`（既定 off。Snowball〈BSD-3、`snowballstemmer`〉で評価し、効けば on） |
| それ以外 | 従来どおり `normalized_form`（助詞・助動詞・補助記号・空白は捨てる） |
| 型番・条項番号（既存の正規表現） | 従来どおり保護（`mx-17` と `mx` / `17` を出す） |

## 5. rerank

- 入力文: `cfg.rerank_input = "context+text"`（既定）なら `f"{context}\n\n{text}"`、`"text"` なら本文のみ。
- TEI の `--max-client-batch-size` 既定 32 に合わせて 32 件ずつ送り、`index` で元の順に戻す。
- `rerank_timeout_sec`（既定 10）、再試行 2 回。最終的に失敗したら `RerankError` → service が縮退（R10）。
- `rerank_enabled=false` の variant では呼ばない（`score = fused_score`）。

## 6. 評価基盤（`api/src/arag/eval/`）

| ファイル | 内容 |
|---|---|
| `dataset.py` | 旧版 `rag/eval/dataset.py` を移植（`GoldenSuite`、`relevant_documents ⊆ documents` の検証）。`lang: ja|en|cross` タグを追加 |
| `metrics.py` | 旧版の純関数（recall@k・precision@k・MRR・nDCG@k・fact_coverage、NFKC 正規化）をそのまま移植 |
| `runner.py` | `run_suite(suite, search_fn)`。文書単位の順位列にたたむ。fact_coverage は結果本文 + 親セクション本文。所要時間 p50 / p95 |
| `variants.py` | `eval/variants.yaml` を読み `SearchConfig` と埋め込み設定・コレクション名を作る。`index --variant` で Postgres の子チャンクから別コレクションを作る（文脈有無・埋め込みモデル・接頭辞・sparse 版）。本番エイリアスには触れない |
| `public.py` | 公開データセットを取得してパッセージを `.md` に書き出し、golden.yaml を生成（旧 `beir.py` 相当）。保存先は `eval/.cache/`（gitignore） |
| `report.py` | JSON レポート、基準値との差分、variant 比較表（Markdown）、ゲート |
| `__main__.py` | `prepare` / `ingest` / `index` / `run` |

### 6.1 variant（`eval/variants.yaml`）

```yaml
default:          {mode: hybrid, fusion: rrf, rrf_k: 60, weights: [1, 1], rerank: true, rerank_input: context+text, embed: bge-m3, context: true}
dense_only:       {base: default, mode: dense}
keyword_only:     {base: default, mode: keyword}
no_rerank:        {base: default, rerank: false}
rrf_dense2:       {base: default, weights: [2, 1]}
rrf_sparse2:      {base: default, weights: [1, 2]}
dbsf:             {base: default, fusion: dbsf}
rerank_text_only: {base: default, rerank_input: text}
no_context:       {base: default, context: false}            # 別コレクション（本文のみで埋め込み・sparse）
ruri_embed:       {base: default, embed: ruri-v3-310m}        # 別コレクション（768 次元・接頭辞つき）
ruri_rerank:      {base: default, reranker: ruri-v3-reranker-310m}
en_stem:          {base: default, sparse_en_stem: true}       # 別コレクション
```

埋め込み・rerank のモデル名と TEI の URL は `eval/variants.yaml` の `models:` 節で対応づける（GPU 機の 8081〜8084）。

### 6.2 題集

| 題集 | 言語 | 文書 | 問数 | 作り方 |
|---|---|---|---|---|
| `agentic_rag_demo` | ja | 評価 PDF 7 件 | 6 | 旧版を移植（閾値 recall@5 0.90・fact_coverage 0.90） |
| `agentic_rag_demo_ext` | ja + cross | 同上 | 50+ | LLM（deepseek-v4-pro）で章ごとに候補を作り、Claude が一次選別、**ユーザーが最終確認**。英語の質問 5 問以上 |
| 日本語の公開データ（部分集合） | ja | パッセージ 1〜2 万 | 200 | 候補: MIRACL ja（Apache-2.0）・JQaRA・JaCWIR。ライセンスと規模を確認して 1 つ選び decisions に記録 |
| `beir_scifact`（部分集合） | en | 5,183 抄録 | 300 | 旧版 `beir.py` を移植（BEIR、CC BY-SA 4.0 系。確認して記録） |

公開データは評価専用で配布しない（取得スクリプトのみコミット）。

### 6.3 実行環境

GitHub の CI には GPU も実モデルも無いので、品質ゲートは **GPU 機の TEI に向けて手元で回す**（`make eval`）。CI では評価基盤の単体テスト（指標・題集の検証・比較表）と、偽の埋め込み・偽の rerank を使った検索の integration テストだけを回す。

## 7. 設定（`ARAG_` 接頭辞）

| 変数 | 既定 | |
|---|---|---|
| `SEARCH_TOP_K` / `SEARCH_CANDIDATE_K` | 6 / 50 | |
| `SEARCH_FUSION` | `rrf` | `rrf` / `dbsf` |
| `SEARCH_RRF_K` / `SEARCH_WEIGHTS` | 60 / `1,1` | dense, sparse の順 |
| `RERANK_ENABLED` / `RERANK_INPUT` | true / `context+text` | 評価で確認済み（report.md §3） |
| `RERANK_TIMEOUT_SEC` | 10 | |
| `EMBED_QUERY_PREFIX` / `EMBED_DOCUMENT_PREFIX` | 空 / 空 | ruri は「検索クエリ: 」「検索文書: 」 |
| `SPARSE_EN_STEM` | false | 評価で効果なし（report.md §3） |

## 8. テスト

| 層 | 内容 |
|---|---|
| 単体 | `query.py` のフィルタ・prefetch・融合の組み立て、`TeiReranker`（分割・順序復元・再試行・失敗）、`SparseEncoder` v2（英語の小文字化・機能語・カタカナ化しない・型番保護）、eval 指標・題集検証・比較表 |
| integration（Qdrant・Postgres 実体、偽 TEI） | 範囲（他人の個人 KB・ごみ箱・アーカイブ・`kb_ids`・`document_ids`）、同一内容の見える文書の選択、hybrid / dense / keyword、must_contain、rerank 縮退、dense 縮退、決定的順序、`include_section` の重複排除、`/v1/search` の権限、`sync-payload` |
| 実データ（手動） | §6 の題集 × variant を GPU 機の TEI で実行 → `report.md` |

## 9. 依存の追加（licenses.md に追記）

`pyyaml`（MIT、題集）、`snowballstemmer`（BSD-3、英語ステミングの評価用）。公開データの取得は `httpx` で直接（`datasets` ライブラリは入れない）。

## 10. 未決事項（評価で決めて本書へ反映）

> 2026-11-09 決定（`decisions.md` §13、`report.md` §3〜§5）: 1 は rerank を ruri-v3-reranker-310m に（切り替えは tasks D5）、埋め込みは bge-m3 のまま、文脈は有効。2 は JQaRA。3 は 50 のまま。4 は日本語の文脈のまま: 英語文書に日本語の文脈を付けても英語の質問（SciFact）は文脈なしと同じ 0.820、日本語の質問（scifact_ja）は +0.013。英語の文脈との直接比較はしていない（プロンプト変更が要るため、差が出る見込みが小さいので見送り）。

1. 融合方式・重み、rerank 入力、文脈の有無、埋め込み・rerank モデル、英語ステミング（E2・E2a）。
2. 日本語の公開データセットの選定（ライセンス・規模）。
3. `candidate_k` の既定（50 で rerank の所要時間が E3 を満たすか）。
4. 文脈付与の言語: 現在は文書の言語に関係なく日本語で文脈を作る。英語文書で英語の文脈にした方が良いか（sparse は同じ言語の語が効くため）を `beir_scifact` で比べる（P1 のプロンプト変更が必要なら P2 内で行う）。
