# 028 会話の動線 — 設計

## 判断: 過程の共有は「共有」ではなく「フィードバック」に載せる

- 共有リンク（specs/008）は読む人のためのもので、`public` にできる。ステップには検索語・資料の本文の一部・内部の判断が入るので、リンクに載せると外へ出る。R5 の「ステップは返さない」は変えない。
- フィードバックは既に回答（`message_id`）に結び付いていて、理由とコメントを持つ。ステップは回答と一緒に保存してある。足りないのは「管理者が読む場所」だけなので、そこを作る。
- 利用者の手間は増やさない: 「良くない」→ 理由 → 送信、の今の流れのまま。過程は自動で付く（付くことは明示する）。

## 1. 続けて聞く

- 場所: `runner` が回答を確定した後、`run.completed` を送る前。`api/src/arag/agent/followups.py`（新規）に `async suggest(model, question, answer, titles) -> Followups(questions, error, ms)`。
- プロンプト `prompts/agent_followups.md`: JSON `{"questions": ["…", "…"]}` だけを出させる。入力は質問・回答（先頭 1500 字）・引用した資料の題名。資料の本文は渡さない（題名だけで足りる。指示の混入も避ける）。
- 解析は `understand.parse` と同じ流儀（コードブロックの記号を外す・配列でなければ失敗）。重複と元の質問と同じ文を落とし、40 字を超えるもの（半角は 0.5 字と数える。実際の Gemma で英語の候補が 50〜74 文字になり全部落ちたため）は捨て、最大 3 個。
- （T6b）資料の抜粋も渡す: `CitationRegistry.items()`（検索に出た全件）を、資料ごとに「題名（見出し）+ 本文の先頭 240 字」、スコア順（スコアの無い節の読み込みは後ろ）に最大 8 件、全体で 2400 字まで。プロンプトでは `<資料>…</資料>` で囲み、中はデータであり指示ではないと書く。記録の input に `excerpts`（件数）と `excerpt_chars`（字数）を入れる。題名だけでは、資料に答えの無い候補（担当部署・保管場所など）が混じったため。
- （T15）runner は同じスレッドの前の 3 ターン（ordinal が今より小さいもの）の質問と回答（先頭 600 字）を読み、`suggest(…, history=)` に渡す。モデルの出力の後に `drop_known` で決定的に絞る: ①これまでの質問（今の質問を含む）と同じ文（NFKC・空白と句読点を除いて比較）②候補の内容の語（漢字・カタカナ・英数字と `-` の連なり、2 字以上）がすべて、今のターンと前の 3 ターンの質問と回答に含まれる（3 字以上で末尾が「数・名・先・額」の語は、その 1 字を除いた形でも照合）。語が 1 つも無い候補は落とさない。落とした候補は output の `dropped: [{question, reason}]`。
- `asyncio.wait_for(…, 3.0)`。例外・打ち切りは握って候補なしにし、`record_system(kind="followups", input={"model"}, output={"questions"|"error", …})`。
- 運ぶ形: `run.completed` に `suggestions: list[str]`（既定は空）。`messages` に `suggestions` JSONB（既定 `[]`、migration）。スレッドの詳細の各ターンに `suggestions` を含める。API を変えるので `make gen`。
- 画面: `web/src/components/chat/followups.tsx`（新規）。`messages.tsx` で、最後のターン・`status==="done"`・候補あり・実行中でない、のときだけ回答の操作の行の下に置く。
  - 見出し「続けて聞く」（caption、muted）。候補は縦に並べた行（最大 3）: 左に小さな矢印「↳」、文、ホバーで地の色。押すと `onSend(text)`。
  - 文書の札と同じ `animate-fade-up` を 50ms ずつずらす。`motion-reduce` では動かさない。
  - `Turn.suggestions?: string[]`。`turn.ts` の `run.completed` と履歴からの復元で入れる。

## 2. 回答の下の操作

- `answer-footer.tsx`: 並びは「コピー・再生成・良い・良くない・その他（…）」。その他は既存の Popover/Menu の部品で、項目は「Markdown で保存」「HTML で書き出す」と、その下に区切って「時間」「トークン」の 2 行（今の info の中身）。info のボタンは無くす。
- 「出典 n 件」の札（`sourcesChipLabel` と `onOpenSources`・`sourcesActive`）を footer から外す。使われなくなった props・文言・テストは消す。

## 3. 表の集計の見せ方

- `table.py` の `run_query` の結果から、ステップの `output` に構造（`rows_total`・`rows_matched`・`compute_label`・`aggregates: {列: {sum, avg, max, min}}`）を足す（モデルに渡す文 `render()` は変えない）。
- `tool-steps.tsx` の表の集計の表示: 該当行の表 → 「該当 n 行 / 全 m 行」→ `compute` があればその列の合計・平均・最大・最小 → 「すべての集計」（開閉、既定は閉）に残りの列。構造が無い古い記録は今の文のまま出す。

## 4. 技術者への報告

### データ
- `message_feedback` に `status`（`open` | `resolved`、既定 `open`）・`resolved_by`・`resolved_at` を足す（migration）。評価が `up` のものは一覧に出すが既定の絞り込みは「良くない・未対応」。
- 理由に `error` を足す（`FEEDBACK_REASON_TAGS`・API の検証・集計の表示名）。

### API（管理者のみ。既存の管理者の依存を使う）
- `GET /v1/admin/feedback?rating=&status=&cursor=` → 一覧（R13 の項目。コメントと質問は先頭 80 字）。
- `GET /v1/admin/feedback/{id}` → 報告 + そのターン（質問・回答・出典・ステップ・モデル・時間・トークン・`no_answer_reason`・スレッドの題）。
- `POST /v1/admin/feedback/{id}/resolve`・`/reopen` → 状態を変え、監査ログに残す。
- 診断用の JSON は詳細の応答から画面で組む（`report_version: 1`、利用者は表示名だけ、メールアドレスは入れない）。

### 画面
- 利用者側 `feedback-popover.tsx`: 送信ボタンの上に 1 行「送信すると、この回答の質問・回答・検索の過程が管理者に共有されます。」。理由に「エラー・回答が出ない」。
- `ErrorNotice`・`CancelledNotice`・回答なしの通知に「問題を報告」（plain の小さなボタン）。押すと同じ報告の欄を、理由 `error` を選んだ状態で開く。
- 管理側 `/admin/feedback`: 既存の管理ページ（`/admin/audit`）と同じ骨組み。左に一覧、行を押すと右（狭い幅では下）に詳細。
  - 詳細の上: 評価・理由の札・コメント全文・報告者・日時・状態、右上に「対応済みにする」/「未対応に戻す」と「診断用にコピー」。
  - その下: 質問 → 回答（`StaticAnswer`）→ 出典の一覧 → 「過程」（`ToolSteps` をそのまま使い、最初から開いておく。システムの処理も含む）→ 実行の情報（モデル・時間・トークン・回答なしの理由）。
  - 管理のナビに「フィードバック」を足し、未対応の件数を小さく出す。

## 文言（`web/src/i18n/locales/ja/`）

| 鍵 | 文 |
|---|---|
| followupsTitle | 続けて聞く |
| moreActions | その他 |
| saveMarkdown / saveHtml | Markdown で保存 / HTML で書き出す |
| tableMatched | 該当 {n} 行 / 全 {m} 行 |
| tableAllAggregates | すべての集計 |
| feedbackShareNote | 送信すると、この回答の質問・回答・検索の過程が管理者に共有されます。 |
| reasonError | エラー・回答が出ない |
| reportProblem | 問題を報告 |
| systemKinds.followups | 続けて聞く質問の作成 |
| admin: feedbackTitle | フィードバック |
| admin: statusOpen / statusResolved | 未対応 / 対応済み |
| admin: resolve / reopen | 対応済みにする / 未対応に戻す |
| admin: copyDiagnostics / copied | 診断用にコピー / コピーしました |
| admin: process / runInfo | 過程 / 実行の情報 |
| admin: empty | 報告はまだありません。 |

## T23・T24（2026-11-13 追補）

- T19 の「検索で確かめる」と「内容の語がすべて既出」の規則は外した（部品名が入れば検索のスコアは高く、資料に無いことを尋ねる候補を見分けられなかった。語の照合は、回答が質問を言い直すため誤って落とした）。
- 出力の形: `{"questions": [{"q": "質問", "evidence": "抜粋からそのまま写した語句（8〜40 字）"}]}`。`check_candidates` が NFKC・空白（と数字の 3 桁区切りのカンマ）を除いて照合する: ①これまでの質問と同じ文 → `same_question` ②根拠が渡した抜粋のどれにも無い → `no_evidence` ③根拠が今と直近 3 ターンの回答の文にある、または根拠の中の数字・英数字の型番（2 字以上・数字を含む）がすべて回答にある → `already_answered`。
- 抜粋は 1 件 400 字・最大 8 件・全体 3200 字。
- output: `evidence: [{question, evidence}]`（残した候補）・`dropped: [{question, reason, evidence}]`。
- 届け方（T24）: runner は `_persist` の後に `run.completed`（`suggestions: []`・`followups_pending: true`）を送り、`_deliver_followups` で候補を作って `followups`（`{message_id, suggestions}`）を送る。保存済みのメッセージの `suggestions` を更新し、`followups` のステップを `steps` の末尾に足す。ストリームは `followups_pending` の完了では閉じず、`followups` で閉じる（`events.closes_stream`）。候補を作らない条件のときは `followups_pending: false` で、完了で閉じる。`duration_ms` は完了の時点で止める（`_Turn.stop`）。


## T25・T26（2026-11-14 追補）

- 打ち切り（T25）: `RunnerDeps.followups_timeout_sec`（`Settings.followups_timeout_sec`、`ARAG_FOLLOWUPS_TIMEOUT_SEC`、既定 5.0）を `suggest(limit_sec=...)` に渡す。記録の input に `timeout_sec`。
- 同時実行の枠（T26）: 調べた結果、run の行は `_persist` で `completed` になるので、`uq_runs_active_thread` は完了の時点で外れ、次の質問（`create_run`）は弾かれない。画面も `run.completed`（`endsRun`）で入力を戻している。一方 `Runner` は `execute_run` のタスクが終わるまで `running` に数えていたため、候補の作成（最大で打ち切りの秒数）のあいだ枠を 1 つ占め、`run_concurrency` が埋まるとほかの run の claim が遅れた。`execute_run(..., on_answered=cb)` を足し、`run.completed` を送った直後に呼ぶ。`Runner` はその時点でタスクを `running` から `trailing` に移して起こし、次の run を claim する。停止（`run` の終わり）では `running` と `trailing` の両方を待つ。
