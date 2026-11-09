# 006 認証（P4）— タスク

## A. Python

- [x] A1 JWKS キャッシュ（未知 kid で取り直し・30 秒に 1 回まで）— R15
- [x] A2 JWT → Principal（署名・iss・aud・exp・ロールの正規化）— R15, R16
- [x] A3 `auth_mode=jwt` で Bearer を検証、dev ヘッダは無視 — R15, R17
- [x] A4 未確認の利用者は run を作れない（403 `email_unverified`）— R7

## B. Web（サーバ）

- [x] B1 Better Auth 設定（pg・admin・jwt・レート制限・最初の利用者は owner）— R1〜R5
- [x] B2 メール送信（SMTP / 未設定ならログ）— R6, R9, R10
- [x] B3 起動時の認証表マイグレーション — R19
- [x] B4 JWT キャッシュ — R13
- [x] B5 中継: セッション → Bearer、未ログイン 401、Origin 検査、dev は明示時のみ — R13, R14, R17
- [x] B6 `proxy.ts`: 未ログインは /login?next=、ログイン済みの /login はアプリへ — R12

## C. Web（画面）

- [x] C1 /login（ログイン・登録・再設定申請）— R1〜R4, R9
- [x] C2 /reset-password — R9
- [x] C3 未確認の帯・再送、確認完了のトースト — R6, R8
- [x] C4 利用者メニュー（ログアウト）・セッションの利用者を表示 — R2
- [x] C5 アカウント（表示名・パスワード変更・端末一覧）— R11

## D. 結合

- [x] D1 compose（mailpit・環境変数）・licenses.md — R10, R18
- [x] D2 ブラウザで登録 → メール確認 → 質問 → ライブラリ → ログアウト

## 実装メモ

- 2026-11-09 ブラウザ（compose・Mailpit）で確認: 未ログインは /login?next= へ、登録 → 未確認の帯と質問の 403 → 確認リンク → 質問 202 → アカウント画面 → ログアウト（API は 401）→ 誤パスワードの文言 → 再設定申請（中立の応答）→ 再設定リンク → 新しいパスワードでログイン → ログイン試行のレート制限（429）。
- JWKS の取得中に同時に来た要求が 401 になる競合を見つけて直した（取得を共有する。`test_concurrent_requests_share_one_fetch`）。
- 評価（`python -m arag.eval`）と `arag.cli ingest-dir` は開発用ヘッダで API を直接叩く。本番の api（JWT）は変えず、`make eval-api` で評価用の api-eval（compose profile `eval`、`ARAG_AUTH_MODE=dev`、127.0.0.1:8101 のみ）を立てて使う。終わったら `make eval-api-down`。繋がらない・401 のときは起動方法を示して止まる（2026-11-09）。
- 認証前に dev 利用者（`dev`）で作った個人 KB・スレッドは、新しい利用者からは見えない（利用者 ID が違う）。組織 KB は owner / admin から見える。
