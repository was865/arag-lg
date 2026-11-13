# 028 会話の動線 — 設計

## 判断: 過程の共有は「共有」ではなく「フィードバック」に載せる

- 共有リンク（specs/008）は読む人のためのもので、`public` にできる。ステップには検索語・資料の本文の一部・内部の判断が入るので、リンクに載せると外へ出る。R5 の「ステップは返さない」は変えない。
- フィードバックは既に回答（`message_id`）に結び付いていて、理由とコメントを持つ。ステップは回答と一緒に保存してある。足りないのは「管理者が読む場所」だけなので、そこを作る。
- 利用者の手間は増やさない: 「良くない」→ 理由 → 送信、の今の流れのまま。過程は自動で付く（付くことは明示する）。

## 1. 続けて聞く

- 場所: `runner` が回答を確定した後、`run.completed` を送る前。`api/src/arag/agent/followups.py`（新規）に `async suggest(model, question, answer, titles) -> Followups(questions, error, ms)`。
- プロンプト `prompts/agent_followups.md`: JSON `{"questions": ["…", "…"]}` だけを出させる。入力は質問・回答（先頭 1500 字）・引用した資料の題名。資料の本文は渡さない（題名だけで足りる。指示の混入も避ける）。
- 解析は `understand.parse` と同じ流儀（コードブロックの記号を外す・配列でなければ失敗）。重複と元の質問と同じ文を落とし、40 字を超えるもの（半角は 0.5 字と数える。実際の Gemma で英語の候補が 50〜74 文字になり全部落ちたため）は捨て、最大 3 個。
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
