# 010 メンバー管理 — 設計

- `lib/admin/members.ts`（純粋関数・テスト対象）: `memberActionError(actor, target, action)` が R5 の規則を判定し、拒否なら日本語の理由を返す。`memberStatus(user)`。
- `lib/auth/server.ts`: `hooks.before` で `ctx.request` がある（= HTTP 経由の）`/admin/*` を 403 にする。サーバ内の `auth.api.*` 呼び出し（request 無し）は通る。
  招待のパスワード設定メールは `redirectTo` に `invite=1` を付けて区別し、件名と本文を変える。
- Route Handler:
  - `GET /api/admin/members`（`auth.api.listUsers`、最大 500 件・検索は名前とメール）
  - `POST /api/admin/members`（招待: `createUser` → `setRole` → `requestPasswordReset`）
  - `PATCH /api/admin/members/[id]`（`{role}` / `{banned}`。停止は `banUser`（セッション失効を含む）、再開は `unbanUser`）
  - すべて `requireAdmin()`（セッションの役割が owner・admin でなければ 403）と `memberActionError` を通す。Origin を確かめる。
- 画面: `app/admin/members/page.tsx`（サーバで役割を確かめる）＋ `components/admin/members-view.tsx`。
