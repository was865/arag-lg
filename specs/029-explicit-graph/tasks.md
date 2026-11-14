# 029 回答の流れを明示のグラフにする — タスク

状態: P0〜P3 済み。P4・P5 は別に判断。ブランチ `feat/explicit-graph`。

## P0 着手前の確認
- [x] T1 ライセンスを確かめ直す: `langgraph`・`langgraph-prebuilt`・`langgraph-checkpoint-postgres`（MIT のはず）、`langgraph-api`・`langgraph-cli` の `dev`（ELv2 のはず）、Studio が LangSmith への接続を要するか。結果を `specs/000-overview/licenses.md` と `decisions.md` に書く
- [x] T2 今のイベントの列を固定する: 代表的な分岐（そのまま回答／調べ残しの差し戻し／表の差し戻し／数字の差し戻し／空の生成のやり直し／下書きへの退避／雑談）ごとに、偽モデルで流したイベントとステップの列を記録するテストを足す（作り直しの物差し）
  - `api/tests/test_agent_flow_snapshots.py`（17 の分岐。`runner._stream` を通したイベント・モデルが受け取った最後のメッセージ・状態のメッセージ・回数）。作り直しの後に期待を変えたのは `second_turn` の 1 件だけ: 2 ターン目の「質問の理解」の直後に出ていた `sources` イベントが出なくなった（中身は直後の検索の完了で送るものと同じ）。`sources` はステップを受け取った時点で資料が登録済みなら送るので、受け手の遅れで出たり出なかったりする（作り直しの前は、検索が終わってから理解の完了を受けていた）。節点の境目で受け手が追いつくようになったため
- [x] T3 `create_agent` を部分グラフにしたとき、`subgraphs=True` で `messages`・`custom` が今と同じ形で届くか、最後の応答の `response_metadata` が外から読めるかを、小さな試し書きで確かめる
  - 結果: `subgraphs=True` なら `messages`（本文の断片、`langgraph_node="model"`）と `custom`（部分グラフの中のステップ）が今と同じ中身で届く。形は `(namespace, mode, chunk)` の 3 つ組になる（`subgraphs` なしでは部分グラフの中の `custom` が届かず、本文も断片でなく完成したメッセージで届く）。`response_metadata`（`finish_reason`）と`usage_metadata` は外側の節点から状態のメッセージで読める。部分グラフと外側で同じ名前の鍵は双方向に渡り、外側の `RemoveMessage` の後に入り直すと、消したメッセージはモデルに渡らない。部分グラフの状態の書き換えは`ExtendedModelResponse`（モデルの呼び出しを包む middleware から `Command` を返す）で、節点を増やさずに行える

## P1 明示のグラフ（R1〜R4）
- [x] T4 `AgentState` と節点の骨組み（`prepare`・`investigate`・`guard`・`review`・`finalize`・`followups`・`read_image`）、辺の純関数とそのテスト
- [x] T5 `PrimerMiddleware` → `prepare`
- [x] T6 `_guard_empty`・書き直しの取り消し → `guard`
- [x] T7 `pick_review`・`_send_back` → `review`（`answer.reset` の送り方を含む）
- [x] T8 `CitationMiddleware`・確定・`_classify` → `finalize`
- [x] T9 `_deliver_followups`・画像の読み取り → 節点
- [x] T10 ステップに `node` を足す（`make gen`）
- [x] T11 T2 のテストと既存の全テストが通る（済み。単体・結合とも）。69 題を作り直しの前後で比べる（指標 ±0.01、`wrong_fact` 0、p50 +100ms 以内）
  - 結果（Gemma 4 12B、前 = `hm-gemma4-12b-026f`、後 = `hm-gemma4-12b-029`）: 引用再現率 1.000 → 1.000、引用精度 0.966 → 0.973、事実網羅 1.000 → 1.000、誤りの記述 0 → 0、p50 2698 → 2667ms、p95 5279 → 6079ms（測定中に画面から 2 問を並行して流した）
  - 回答不能率 0 → 0.014 は hm59（`expect_no_answer` の題）。前は「資料  や [1]」の崩れた引用が付いて回答扱いだったのが、T35（main で直した刈り込み）で引用が外れ、`no_relevant_sources` に分類された。退行ではない

## P2 図をコードから（R5・R6）
- [x] T12 `diagram.py`・`make graph`・`docs/agent-graph.md`・`web/src/lib/chat/flow-graph.json`・CI の `graph-check`
- [x] T13 `docs/architecture.html` を今の構成に合わせ、回答の流れは `agent-graph.md` を指す。IP アドレスを消す

## P3 実行の経路（R7〜R9）
- [x] T14 `flow.ts`（ステップの列 → 経路。`node` の無い記録は推定）とテスト
- [x] T15 `run-flow.tsx`（見た目は design.md のとおり）。`StageRail` を置き換える
  - 実行中の見出しは `FlowRail`（理解・最初の検索・調査・確認・確定の 5 段。画像・見張り・続けて聞くは前後の段にまとめる。雑談と分かったら最初の検索を外す）。「詳細」の上は `RunFlow`（全節点）。どちらも `flowOf` の同じ結果から出す
  - 動いているステップが無いあいだ（モデルが考える・書く）は `flowOf` の `idle` で今の節点を決める（確認の後は確認のまま。段階が後ろへ戻って見えないように）
  - 画像の節点は、画像のあるターンだけ並べる。戻り・退避の弧は節点の列の位置（列の幅の割合）から描く
- [x] T16 節点で一覧を絞る（R8）
- [x] T17 管理画面のフィードバックの詳細に出す（R9）
- [x] T20 流れの表示を作り直す（2026-11-14。最初の版の ×2・弧・見張りが分かりにくかった）: 実際にたどった順の経路（`routeOf`）・周回・ひと言の要約・停留所の印・横 / 縦の並び・描く動き。確認の通過も記録に残す（`review_passed`）。設計は design.md の「見た目」
- [x] T21 検索の記録を細かくする（2026-11-14）: 自動の 2 回の検索に狙いを付け（`質問文で検索` / `整理したクエリで検索`、入力に `role`・`purpose`）、各検索の内部の段（埋め込み → 候補の取得 → 再ランキング）を子ステップにする（`emit_search_stages`）。各段は終わった順に実時間で送り（`search.service.stage_hook`）、結果の行は最後に置く。整理したクエリが質問文と近い（0.85 以上）ときは検索せず、「近いクエリの省略」（`query_skipped`）として記録する。「候補の取得」には rerank 前の候補の一覧（融合スコアを最高 1 とした相対値）を出し、「探した文書」の数には入れない。検索の結果の行は候補の一覧を読める形で出す
- [x] T22 追質問で「さっきの資料」を文書に直せるようにする（2026-11-14）: 確定のとき、回答が引用した文書名を回答のメッセージ（`additional_kwargs.cited_documents`）に残す（出典番号は保存のとき振り直され、最初の検索の結果は履歴に残らないため）。前のターンのツール結果の代わりの文は、引用した文書名を最初の 1 件にだけ載せ（`prior_placeholder`）、残りは短い 1 文。質問の理解にも回答が引用した資料を渡す（`history_text`）。記録の出力は `placeholders`

## P4・P5（任意。別に判断）
- [ ] T18 聞き返し: 入庫側に版・機種・拠点の項目があるかを調べ、無ければ先にその設計を出す
- [ ] T19 途中からの再開: runner が落ちた run を checkpoint から続ける
