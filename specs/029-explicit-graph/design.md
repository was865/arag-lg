# 029 回答の流れを明示のグラフにする — 設計

## 今の形と、変える所

今（`graph.py`）: `create_agent(model, tools, middleware=[Primer, Summarization, AgentPolicy, ModelSwitch, Step, Citation])`。`create_agent` 自体が LangGraph のグラフ（model ⇄ tools の輪）で、私たちの流れはその前後と内側に middleware として挟んである。続けて聞く・画像の読み取り・回答の確定は `runner.py` の手続き。

変えた後: 外側に私たちの `StateGraph` を置き、`create_agent` は「調査」の 1 節点（部分グラフ）として中に入れる。モデルと道具の輪・要約・モデルの切り替え・道具のステップの記録は、今の middleware のまま部分グラフに残す（動いているものは動かさない）。外へ出すのは、**流れの制御**だけ。

```
START
  └─ read_image ──（画像なしは素通り）
       └─ understand
            ├─ kind=chat ─────────────────────────────┐
            └─ kind=docs → primer_search ─────────────┤
                                                      ▼
                                                 investigate   ← create_agent（model ⇄ tools）
                                                      │
                                                      ▼
                                                   guard        空の生成／差し戻しへの返事／引用の消失
                                   ┌── retry（1 度）───┤
                                   │                  ├── use_draft ──────────────┐
                                   ▼                  ▼                           │
                              investigate          review       調べ残し・表・数字   │
                                   ▲                  │                           │
                                   └── send_back ─────┤（種類ごとに 1 度）          │
                                                      ▼                           │
                                                  finalize  ◀─────────────────────┘
                                                      │        引用の刈り込み・整形・数字の照合・理由の分類
                                                      ▼
                                                  followups    （完了の後に届ける。条件に合わなければ素通り）
                                                      │
                                                     END
```

## 状態（`AgentState`）

`messages`（部分グラフと共有）に加えて、流れの制御に要るものを**状態に**持つ（今は `RunContext` と `RunStats` に散っている）:

| 鍵 | 中身 |
|---|---|
| `understanding` | kind・queries・table（今の `Understanding`） |
| `primer` | 最初の検索の結果（今の `Primer`。モデルに渡す直前に質問へ付ける扱いは変えない） |
| `draft` | 直近の下書き（今の `review_draft`） |
| `reviews_done` | 済んだ確認の種類の集合（`gap`・`table`・`numbers`） |
| `empty_retries` | 空の生成のやり直しの回数 |
| `outcome` | `answered`・`used_draft`・`empty_failed` など、確定の理由 |
| `suggestions` | 続けて聞くの候補 |

`RunContext`（依存・設定・資料の登録簿・ステップの送り先）は今のまま `context` で渡す。状態に入れるのは、分岐の判断に使う値だけ。

## 節点と辺（どこから移すか）

| 節点 | 今ある場所 | 備考 |
|---|---|---|
| `read_image` | `runner.py`（`query_image`） | 画像が無ければ何もしない |
| `understand` | `PrimerMiddleware.abefore_agent` の前半 | 初回のターンは質問そのものの検索と並行（`asyncio.gather`）— 節点 1 つの中で並行のままにする。節点を 2 つに割ると並行でなくなり、遅くなる |
| `primer_search` | 同・後半 | `understand` と同じ節点にするか分けるかは、上の並行の都合で **1 つの節点 `prepare`（中で 2 つのステップを出す）** にする。図の上では 2 段に見せる（節点の中の段として描く） |
| `investigate` | `create_agent` | middleware は Summarization・ModelSwitch・Step と、primer を質問へ付ける処理・回数の上限だけを残す |
| `guard` | `AgentPolicyMiddleware._guard_empty`・書き直しの取り消し | 辺: `retry` / `use_draft` / `ok` / `failed` |
| `review` | `pick_review`・`_send_back` | 辺: `send_back`（差し戻しの文を `messages` に足して `investigate` へ）/ `pass` |
| `finalize` | `CitationMiddleware.aafter_agent`・`runner.py` の確定と `_classify` | 数字の照合の記録もここ |
| `followups` | `runner.py:_deliver_followups` | `run.completed` を先に送る今の順序を保つため、`finalize` の終わりで完了を送り、この節点は後から届ける |

辺の関数は、状態だけを見る純関数にする（`route_after_guard(state) -> Literal[...]` など）。偽モデルなしで分岐のテストが書ける。

### ストリームの扱い（挙動を変えないための要点）

- 今は `agent.astream(stream_mode=["messages","custom"])` で、本文の断片（`answer.delta`）とステップ（`custom`）を受けている。部分グラフにしても同じ 2 つの mode を `subgraphs=True` で受け、`runner` 側の変換は今のまま使う。
- 差し戻しのとき `answer.reset` を送るのは、`review` から `investigate` へ戻る辺を通った時。今は middleware の中で送っているので、`review` 節点が `stream_writer` で送る形にする。
- `investigate` の中の「最後の回答」と「途中の発話」の見分け（道具を呼ぶ前の発話は回答にしない）は今の規則のまま。

### checkpoint

既に `langgraph-checkpoint-postgres` を使っている（スレッドごと）。外側のグラフも同じ checkpointer に載せる。状態の鍵が増えるので、古い checkpoint から読むときに欠けた鍵を既定値で補う（`AgentState` の既定値で足りる）。再生成のときに checkpoint を消す今の扱いは変えない。

## 図の生成（R5・R6）

- `api/src/arag/agent/diagram.py`: `build_graph(...).get_graph(xray=1).draw_mermaid()`。節点の表示名（日本語）と、辺の札（`差し戻し`・`やり直し`・`下書きへ`）を付けて整える。モデルや DB に触れずに組み立てられるよう、偽の依存で組む。
- `make graph` → `docs/agent-graph.md`（Mermaid と、節点ごとの 1 行の説明。説明は節点の docstring から取る）。CI に `graph-check`。
- `docs/architecture.html` は、全体の構成（箱と矢印）だけを持ち、回答の流れは `agent-graph.md` を指す。

## 経路の表示（R7〜R9）

### データ
- ステップに `node`（節点の名前）を足す（`Step` の任意の項目。`StepClock`・`record_system` が、今いる節点を `RunContext` から読んで付ける）。API の型が変わるので `make gen`。
- 経路は保存しない。**ステップの列から画面で組み立てる**（`web/src/lib/chat/flow.ts`）: 節点ごとの通過回数・所要時間の合計・戻りの有無・退避の有無。保存する形を増やさないので、古い回答にも同じ関数が使える（`node` が無ければステップの種類から推定: `understand`→prepare、`search` で `by=system`→prepare、`review`→review、`system` の `empty_generation`/`rewrite_discarded`→guard、`citation_pruned`/`number_check`→finalize、`followups`→followups、その他→investigate）。
- グラフの形（節点の並びと辺）は、`make graph` が `web/src/lib/chat/flow-graph.json` にも書き出す。画面はこれを読む（図と画面が同じ源から出る）。

### 見た目（`web/src/components/chat/run-flow.tsx`）
- 「詳細」を開いた一番上に、高さ 56px ほどの横一列。節点は角丸の小さな札（表示名 + 所要時間）、辺は細い線。
  - 通った節点: 地は surface、文字は fg、左に既存の済みの印。通らなかった節点: 文字 muted-2、線は点線。
  - 戻り（確認 → 調査）: 上側に弧の矢印、札「差し戻し 2 回」。退避: 下側に弧、札「下書きへ」。やり直し: 節点の右肩に「×2」。
  - 実行中は、いまの節点だけ既存の呼吸する点。今の `StageRail`（理解 → 検索 → 回答 → 確認）はこの表示に置き換える（同じ情報の 2 つ目の表現を持たない）。
- 幅が足りないとき（< 560px）は節点を表示名だけにし、所要時間は押したときに出す。横スクロールはさせない（札を詰める）。
- 色は既存のトークンだけ。動きは既存の `ar-g-*` と同じ速さ。`motion-reduce` では動かさない。
- 節点を押すと下のステップの一覧がその節点に絞られる（R8）。絞っているあいだ、節点に輪郭、一覧の上に「調査のステップだけを表示中 · 解除」。

### 文言
| 鍵 | 文 |
|---|---|
| flowTitle | 流れ |
| nodes.read_image / prepare / investigate / guard / review / finalize / followups | 画像 / 理解と検索 / 調査 / 見張り / 確認 / 確定 / 続けて聞く |
| flowSentBack | 差し戻し {n} 回 |
| flowRetried | やり直し {n} 回 |
| flowUsedDraft | 下書きへ |
| flowFiltered | {node}のステップだけを表示中 |
| flowClear | 解除 |
| flowInferred | 古い記録のため、流れは推定です |

## 聞き返し（R10〜R12。任意）

- `prepare` の後に条件つきの辺 `clarify`。判定は補助モデルではなく、最初の検索の結果から決定的に出す: 上位の資料が「同じ文書の別の版」「別の機種」「別の拠点」に割れていて（題名・見出しから取れる対象の語が 2 つ以上）、質問にそのどれも書かれていないとき。対象の語の取り出しは資料のメタデータ（版・機種・拠点）が要るので、入庫側に項目が無ければ先にそこから（この項目が無いと作れない。着手前に調べる）。
- 聞き返しのターンは、回答の本文が「どれについて知りたいですか？」+ 選択肢。選択肢は `suggestions` と同じ運び方・同じ部品で出し、押すと「（元の質問）— HP-300 第3版について」の形で送る。
- 評価: 対象を指定しない題を 10 題ほど足し、聞き返すべき題で聞き返すか・指定のある題で聞き返さないかを測る。

## 途中からの再開（R13。任意）

- 外側のグラフが checkpoint に載っていれば、落ちた run を別の runner が同じ `thread_id` で `astream(None, config)` して続けられる。要るのは、run の行に「どの節点まで進んだか」を持たせることと、送り済みのイベントの続きから流すこと（`sink` の連番は既にある）。`investigate` の途中（モデルが文を流している最中）で落ちた場合は、その節点の最初からやり直す（本文は `answer.reset` で消す）。

## 進め方と危うい所

- ブランチ `feat/explicit-graph`。main には、69 題の指標と全テストが作り直しの前と一致してから入れる。
- 段階: **P1**（R1〜R4: 作り直し。画面は変えない）→ **P2**（R5・R6: 図の生成）→ **P3**（R7〜R9: 経路の表示）。P4（聞き返し）・P5（再開）は別に判断。
- 危うい所:
  1. ストリームの順序（`answer.reset` と `answer.delta` の前後）。偽モデルのテストに、イベントの列をそのまま比べるものを先に足す（作り直しの前に、今の列を記録しておく）。
  2. `create_agent` の内側でしか取れない値（モデルの応答の `response_metadata` など）を `guard` が使う。部分グラフの出力（最後の `AIMessage`）から読めるかを P1 の最初に確かめる。読めなければ、その値だけ middleware が状態に書く。
  3. 節点が増えるぶんの checkpoint の書き込み（1 ターンに数回 → 十数回）。所要時間への影響を 69 題の p50 で見る（+100ms を超えたら、`investigate` の内側の checkpoint を減らす）。

## 実装で変えた点（P1・P2、2026-11-14）

- **`prepare` を 2 つの節点 `understand`・`primer_search` に分けた**。初回のターンの「質問文での検索」は `understand` の中で理解と並行のまま行い、`primer_search` は整理した残りの語だけを検索する（今と同じ並行の度合い）。これで「雑談は最初の検索を飛ばす」を条件つきの辺（`understand` → `investigate`）として書ける。初回の `primer-1` のステップは `understand` の節点のものになる。
- **最初の検索の結果の文は状態に入れず `RunContext` に置く**（`primer`・`primer_texts`）。状態には理解の結果（`understanding`: kind・queries・table・残りの語）だけを置く。結果の文はターンごとに数 KB〜数十 KB あり、checkpoint に毎ターン残す理由が無いため。途中からの再開（P5）では `primer_search` からやり直す。
- **差し戻しと空のやり直しの「結果の記録」は、調査の中のモデル呼び出しの直後に出す**（`AgentPolicyMiddleware`）。判断（やり直す・退避する・差し戻す）は外の `guard`・`review` が行い、状態の `send_back`・`empty_pending` に置く。部分グラフはこの鍵を読んで、差し戻しの依頼を次のモデル呼び出しにだけ添え、応答が来たら「見直し」のステップを閉じる。外で閉じると、書き直しがツールを呼んだときに「見直し」の完了がツールのステップより後になり、記録の順が変わるため。状態の書き換えは `ExtendedModelResponse` で行い、部分グラフに節点を足さない（回数の上限・`recursion_limit` を変えない）。
- **`answer.reset` は今のまま runner が送る**（新しいモデル呼び出しの断片が来たら、それまでの本文を消す）。`review` が送る形にすると、届く順が変わるおそれがあるため。
- **`guard` の辺は `retry`・`use_draft`・`ok` の 3 つ**。空のまま下書きも無い（`failed`）は、今と同じく確認へ進む（`ok`。表の集計の確認は空の回答にも掛かりうる）。区別は状態の `outcome`（`empty_failed`）で持つ。
- **節点の名前の付け方**: 外側の節点は送るときに `tag_node` で付け、部分グラフの中のステップ（ツール・システムの処理・モデルの切り替え・考えた過程）は runner がストリームの namespace（`investigate:…`）から付ける。「見直し」のステップは調査の中で閉じても `review` の節点のもの。続けて聞くの記録は `followups`。
- **runner の入出力は `RunContext.hooks` で渡す**: `finalize` が確定した回答（`Completion`）を `hooks.completed` に渡し、runner が保存して `run.completed` を送る。`followups` の節点は `hooks.followups` を呼ぶ（保存済みのメッセージに候補を足して `followups` を送る、今の処理のまま）。画像は `hooks.read_image`。テストでは空のまま（記録だけが出る）。確定の後の取消・失敗では保存し直さず、候補を待っている画面には空の `followups` を送って閉じる。
- **流れの状態はターンの始め（`read_image`）で初期値に戻す**（`FRESH`）。前のターンの差し戻し済み・やり直し済みを持ち越さない。
- **古い checkpoint**: 作り直しの前（create_agent だけのグラフ）が保存したスレッドも、`messages` の鍵が同じなのでそのまま続きを読める（テストあり）。応答の無いツール呼び出しを閉じる処理は `as_node="investigate"` で書く。取消が調査の途中に来たときは、外側の状態にはそのターンの質問だけが残り、途中のツールの結果は残らない（部分グラフの checkpoint にだけある）。

