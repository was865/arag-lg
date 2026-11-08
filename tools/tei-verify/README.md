# tei-verify

TEI（text-embeddings-inference）の出力が参照実装と数値的に一致するかを確かめる開発専用ツール。
仕様と結果は `specs/002-tei-verification/report.md`。api の依存には含めない。

```bash
cd tools/tei-verify
uv sync
uv run pytest -q
# bge（GPU 機で compose.gpu.yaml を起動済みとする）
uv run python -m tei_verify --preset bge --embed-url http://localhost:8081 --rerank-url http://localhost:8082
# ruri（--profile ruri で起動）
uv run python -m tei_verify --preset ruri --embed-url http://localhost:8083 --rerank-url http://localhost:8084
```

- 比較対象: embedding は sentence-transformers（正規化あり）、rerank は bge が FlagEmbedding の `FlagReranker`、ruri が sentence-transformers の `CrossEncoder`。参照側は CPU・fp32。
- TEI の `/info` が返す `model_sha` と同じ revision を参照側でも読み込む。
- 判定: embedding は全件 cosine ≥ 0.999、rerank は raw / sigmoid とも絶対差 ≤ 1e-2 かつクエリごとの順位が完全一致。
- 出力: `results/<preset>.json`（全スコア）と `results/<preset>.md`（表）。不合格なら終了コード 1。
- 評価データ: `data/corpus.json`（架空の社内文書 20 件・クエリ 5 件）。
