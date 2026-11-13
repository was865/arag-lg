# 026 設計

## 流れ

```
質問 ─▶ ① 理解（補助モデル、JSON）──┐
   └──▶ ② 最初の検索（系統）  ◀────┘（最初のターンは ① と並行）
                │  結果を質問に添える（状態には保存しない）
                ▼
        ③ 補足の調査（モデルのループ。ツールは任意）
                │  search / keyword_search / list_documents / get_outline / read_section
                │  table_query（表の集計）/ calculate
                ▼
        ④ 確認（系統）: 調べ残し → 表の集計 → 数字の照合（各 1 度だけ差し戻し）
                ▼
        ⑤ 回答の整形（引用の正規化。既存）
```

## モジュール（`api/src/arag/agent/`）

| ファイル | 役割 |
|---|---|
| `understand.py` | `understand(model, history, question) -> Understanding`。プロンプト `agent_understand.md`、JSON の読み取り、失敗時の既定 |
| `primer.py` | `PrimerMiddleware.abefore_agent`: ①② を行い、`ctx.primer` に結果を置く。ステップ `understand`・`search`（`input.by="system"`）を送る |
| `table.py` | Markdown の表の読み取り、条件・計算式の評価（ast、許した節だけ）、結果の整形。`op_table_query` |
| `numbers.py` | 数字の取り出しと照合（カンマ・全角・万/千/億・漢数字） |
| `middleware.py` | `AgentPolicyMiddleware`: 添える・回数上限・差し戻し（gap / table / numbers）・数字の照合の記録。ツールの強制は削除 |

## ① 理解

出力: `{"kind": "docs"|"chat", "queries": [...], "table": bool}`。入力は直近 2 往復（回答は 300 字まで）と今回の質問。
15 秒で打ち切る。読めなければ `Understanding(kind="docs", queries=(質問,))`。

## ② 最初の検索

- 最初のターン: `gather(understand, search(質問))`。整理で出たクエリのうち質問文と違うものを追加で検索（合計 3 まで）。
- 2 ターン目以降: 整理を待ち、そのクエリだけを並行で検索。
- 検索は既存の `op_search`（関連度が低いときの書き換えを含む）。親ステップは `id="primer-N"`・`name="search"`・`input={"query","by":"system"}`。
- 複数の結果は、同じ出典番号の資料を 2 度目以降で省いてつなぐ。
- 渡し方: `AgentPolicyMiddleware` がモデルを呼ぶたびに、このターンの HumanMessage の末尾へ
  `<検索結果>…</検索結果>` を足す（状態は変えない）。合成のツール呼び出しは作らない
  （Anthropic の思考モードは、思考ブロックの無いツール呼び出しの履歴を受け付けないため）。

## ④ 確認

`awrap_model_call` で最終回答（ツール呼び出しなし）を受けたとき、順に 1 つずつ当てる（各種類ターンに 1 度、回数の余裕があるとき）:

1. gap: 調べ残しの語があり、モデル自身の検索が 1 回以下。
2. table: `understanding.table` かつ表のある資料があり、`table_query` を呼んでいない。
3. numbers: 見当たらない数字がある。

差し戻しは `review` ステップ（`input.kind`）。最後に数字の照合を `system`（`kind="number_check"`）で記録する。
依頼の末尾には共通の `SEND_BACK_TAIL`（システムの確認であり返事は不要、元の質問への回答を質問と同じ言語で書き直す）を付ける（R22）。
`<検索結果>` の後ろにも「上の質問と同じ言語で答える」の 1 行を付ける。

### 数字の照合

- 回答から数字を取り出す（引用記号・行頭の箇条書き番号は除く。1 桁の整数は数えない）。
- 照合先: 添えた検索結果・このターンのツール結果（計算・表を含む）・質問・今日の日付。
- 正規化: NFKC、3 桁区切りのカンマ、`1万8,400`→`18400`、漢数字（照合先のみ）。

## 表の集計（`table_query`）

`table_query(source, where="", compute="", table=1)`

- `source`: 出典番号かセクション ID。章の本文（全文）から Markdown の表を取り出す。
- 見出し: 区切り行の直前の行。1 セルだけの題名行なら次の行を見出しにする。
- 列名: そのまま、または括弧の単位を除いた別名（`単価（円）` → `単価`）。
- `where`: 比較（`< <= > >= == !=`）、`and / or / not`、`"語" in 列`、四則。`＝`・`≦`・`AND`・`かつ`・`contains` などは正規化する。
- `compute`: 行ごとの式（例 `(発注点 - 在庫) * 単価`）。結果は「計算」列。
- 返すもの: 該当行（50 行まで）の表、行数（全体と該当）、数値列と「計算」列の合計（計算列は平均・最大・最小も）。同じ出典番号の `<資料>` で包む。

## 画面

- `understand`: 種類と検索クエリを 1 行で。
- `search` で `input.by == "system"`: 「自動」の札。
- `table_query`: 条件・式を等幅で、結果は表で。
- `review`: 種類ごとの見出し（調べ残し / 表の集計 / 数字）。
- `system` の `number_check`: 見当たらない数字があれば、回答の下に注意の札。
- 進行中の段階の表示（理解 → 検索 → 回答 → 確認）。

## 消すもの

- `tool_choice="any"` と最初の呼び出しでのツールの絞り込み（18b2f8f）、「資料を読むまでツール必須」。
