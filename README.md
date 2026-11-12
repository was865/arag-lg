# arag-lg

社内ナレッジ検索エージェント ARag の LangChain / LangGraph 版（日本語）。
資料をナレッジベースに入れ、エージェントが検索・目次・章の読み込み・計算を使って、出典付きで答える。

```
web/  Next.js 16（画面・Better Auth）──▶ api/  FastAPI + LangChain/LangGraph
                                           ├ runner: エージェントの実行（Redis Stream で配信）
                                           ├ worker: 入庫（Docling → 分块 → 文脈付与 → 索引）
                                           └ Postgres / Qdrant / Redis
推論（埋め込み・rerank・解析・vLLM）は GPU 機の compose.gpu.yaml、または外部 API
```

## はじめに

```bash
cp .env.example .env   # 推論の構成を選んで URL・モデルを書く
make setup
make up                # http://localhost:3100
```

## 文書

| 文書 | 内容 |
|---|---|
| [AGENTS.md](AGENTS.md) | 開発の決まりと地図（人と AI エージェントの両方が最初に読む） |
| [docs/operations.md](docs/operations.md) | 起動・GPU 機・入庫と評価・止まったときの戻し方 |
| [docs/architecture.html](docs/architecture.html) | 今の構成図 |
| [specs/](specs/) | 機能ごとの仕様（requirements・design・tasks）。全体像は [specs/000-overview](specs/000-overview/README.md) |
| [docs/handoff.md](docs/handoff.md) | 着手時（2026-11-08）の計画と、旧版からの変更の理由（歴史的な資料） |
