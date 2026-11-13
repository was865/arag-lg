# 028 会話の動線 — タスク

先に失敗するテストを書く。API を変えたら `make gen`。画面は 3100 で確かめる（`runner`・`api`・`web` を作り直す）。

## A. 続けて聞く（先に出す）
- [x] T1 `followups.py`: `suggest` と解析（重複・元の質問・40 字超を落とす、最大 3、JSON でなければ失敗）。偽モデルのテスト
- [x] T2 プロンプト `agent_followups.md`（R2）
- [x] T3 runner: 回答の確定後に呼ぶ・3 秒で打ち切る・R3 の条件では呼ばない・`system`（`followups`）を記録・`ARAG_FOLLOWUPS`（R4・R5・R7）
- [x] T4 `run.completed` と `messages.suggestions`（migration）・スレッドの詳細に含める・`make gen`
- [x] T5 画面: `followups.tsx`・`Turn.suggestions`・最後のターンだけ出す・押すと送る・`systemKinds.followups` の表示（R6）。vitest
- [x] T6 実際の Gemma で 3 つの質問（表の集計・版の比較・英語）を流し、候補の質と言語、かかった時間を報告する
- [x] T6b 候補を資料で答えられる質問だけにする（R2a）: 検索に出た資料の抜粋を渡し、件数と字数を記録する。実際の Gemma で 3 題を流して確かめる

## B. 回答の下の操作・表の集計
- [x] T7 footer を 5 つにし、「その他」に保存 2 つと時間・トークンを入れる。「出典 n 件」の札を外す（R8・R9）。使わなくなった props・文言・テストを消す
- [x] T8 表の集計: ステップの `output` に構造を足す（モデルに渡す文は変えない）
- [x] T9 表の集計の表示（R10）。古い記録はそのまま出る

## C. 技術者への報告
- [x] T10 `message_feedback.status` などの migration・理由 `error`
- [x] T11 管理者の API 4 つ（一覧・詳細・resolve・reopen）と監査ログ。管理者でなければ 403（R13〜R15・R17）
- [x] T12 利用者側: 報告の欄の 1 行と理由、通知の「問題を報告」（R11・R12）
- [ ] T13 `/admin/feedback` の一覧・詳細・状態の変更・診断用にコピー・ナビの件数（R13〜R16）
- [ ] T14 `specs/README.md` に 028 を足し、`specs/000-overview` の機能・画面・API の一覧を合わせる
