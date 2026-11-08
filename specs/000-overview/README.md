# 000 全体像（overview）

`docs/handoff.md` 第 8 節の手順 1・2 の成果物。旧版 `a-rag@main(83b37005)` を読み込み、新版の範囲を決めるための資料。

| ファイル | 内容 | 状態 |
|---|---|---|
| [decisions.md](decisions.md) | 主要コンポーネントの最新版・ライセンス・採否 | 確定（2026-11-08 時点） |
| [licenses.md](licenses.md) | 依存ライセンス台帳（以後、依存追加ごとに追記） | 運用開始 |
| [features.md](features.md) | 機能一覧（MVP / P5 / 後続 / 廃止）と確認事項 | 確定（2026-11-08） |
| [pages.md](pages.md) | 画面・URL・モーダル一覧 | 確定（2026-11-08） |
| [api.md](api.md) | Next（Better Auth）と Python（FastAPI）の API、SSE イベント | 案 |
| [data-model.md](data-model.md) | Postgres（auth / app / lg）・Qdrant・Redis・ファイル配置 | 案 |

範囲が確定したら P0（骨格・CI）に進み、以降の機能は `specs/<番号>-<名前>/{requirements,design,tasks}.md` で起こす。
