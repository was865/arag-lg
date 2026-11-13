# 029 回答の流れを明示のグラフにする — タスク

状態: 着手（P0〜P2）。ブランチ `feat/explicit-graph`。

## P0 着手前の確認
- [ ] T1 ライセンスを確かめ直す: `langgraph`・`langgraph-prebuilt`・`langgraph-checkpoint-postgres`（MIT のはず）、`langgraph-api`・`langgraph-cli` の `dev`（ELv2 のはず）、Studio が LangSmith への接続を要するか。結果を `specs/000-overview/licenses.md` と `decisions.md` に書く
- [ ] T2 今のイベントの列を固定する: 代表的な分岐（そのまま回答／調べ残しの差し戻し／表の差し戻し／数字の差し戻し／空の生成のやり直し／下書きへの退避／雑談）ごとに、偽モデルで流したイベントとステップの列を記録するテストを足す（作り直しの物差し）
- [ ] T3 `create_agent` を部分グラフにしたとき、`subgraphs=True` で `messages`・`custom` が今と同じ形で届くか、最後の応答の `response_metadata` が外から読めるかを、小さな試し書きで確かめる

## P1 明示のグラフ（R1〜R4）
- [ ] T4 `AgentState` と節点の骨組み（`prepare`・`investigate`・`guard`・`review`・`finalize`・`followups`・`read_image`）、辺の純関数とそのテスト
- [ ] T5 `PrimerMiddleware` → `prepare`
- [ ] T6 `_guard_empty`・書き直しの取り消し → `guard`
- [ ] T7 `pick_review`・`_send_back` → `review`（`answer.reset` の送り方を含む）
- [ ] T8 `CitationMiddleware`・確定・`_classify` → `finalize`
- [ ] T9 `_deliver_followups`・画像の読み取り → 節点
- [ ] T10 ステップに `node` を足す（`make gen`）
- [ ] T11 T2 のテストと既存の全テストが通る。69 題を作り直しの前後で比べる（指標 ±0.01、`wrong_fact` 0、p50 +100ms 以内）

## P2 図をコードから（R5・R6）
- [ ] T12 `diagram.py`・`make graph`・`docs/agent-graph.md`・`web/src/lib/chat/flow-graph.json`・CI の `graph-check`
- [ ] T13 `docs/architecture.html` を今の構成に合わせ、回答の流れは `agent-graph.md` を指す。IP アドレスを消す

## P3 実行の経路（R7〜R9）
- [ ] T14 `flow.ts`（ステップの列 → 経路。`node` の無い記録は推定）とテスト
- [ ] T15 `run-flow.tsx`（見た目は design.md のとおり）。`StageRail` を置き換える
- [ ] T16 節点で一覧を絞る（R8）
- [ ] T17 管理画面のフィードバックの詳細に出す（R9）

## P4・P5（任意。別に判断）
- [ ] T18 聞き返し: 入庫側に版・機種・拠点の項目があるかを調べ、無ければ先にその設計を出す
- [ ] T19 途中からの再開: runner が落ちた run を checkpoint から続ける
