# 010 メンバー管理 — タスク

- [x] A1 権限の規則（純粋関数とテスト）— R4, R5
- [x] A2 管理エンドポイントの直接呼び出しを止める — R7
- [x] A3 Route Handler（一覧・招待・役割・停止/再開）— R1, R3, R6, R8
- [x] B1 メンバー管理画面と入口 — R1, R2
- [x] C1 ブラウザで確認（招待メール・役割の変更・停止でログアウト・直接呼び出しの 403・member では開けない）

## 実装メモ

- `/api/auth/admin/*` の直接呼び出しは `hooks.before` で 403（`ctx.request` があるときだけ。サーバ内の `auth.api.*` は通る）。
- 招待は乱数のパスワードで作り、メール確認済みにして、`redirectTo=/reset-password?invite=1` のパスワード設定メールを送る。`sendResetPassword` は URL の `invite=1` で招待メールに切り替える。
- member が `/admin/members` を開くと、Suspense の中の `redirect()` なのでストリーム内のリダイレクト（200 + meta refresh）になる。画面は描かれず、一覧の API は 403。
- C1: 招待（Mailpit に「ARag への招待」、リンクで「ARag へようこそ」）、役割の変更、admin になった利用者からの owner 停止・管理者招待・別 Origin が 403、停止でセッション失効とログイン拒否（BANNED_USER）、再開、直接呼び出し 403 を確認。
- 確認用の利用者 `member1@arag.test`（パスワードは `.env` の `ARAG_TEST_MEMBER_PASSWORD`）を作った。
