# 006 認証（P4）— 設計

## 1. 構成

```
ブラウザ ── Cookie(better-auth.session_token) ──▶ Next 16
  /login, /reset-password                      ├ src/proxy.ts         未ログインの画面アクセスを /login へ（Cookie の有無だけ見る楽観チェック）
  authClient（better-auth/react）              ├ /api/auth/[...all]   Better Auth（toNextJsHandler）
                                               └ /api/v1/[...path]    getSession → JWT（キャッシュ）→ Bearer で Python へ
Python ── JWKS（http://web:3000/api/auth/jwks）をキャッシュして EdDSA 検証
```

## 2. Web（Next）

- `src/lib/auth/server.ts`: `betterAuth({...})`
  - `database`: `pg.Pool`（`ARAG_AUTH_DATABASE_URL`、`search_path=auth`）。
  - `emailAndPassword`: `enabled`、`minPasswordLength: 8`、`requireEmailVerification: false`（ソフトゲート。R6・R7）、`sendResetPassword`、`revokeSessionsOnPasswordReset: true`。
  - `emailVerification`: `sendOnSignUp: true`、`autoSignInAfterVerification: true`、`sendVerificationEmail`。
  - `session`: `expiresIn: 30 日`、`updateAge: 1 日`。
  - `rateLimit`: `enabled: true`、memory、`customRules`（sign-in / sign-up / request-password-reset / send-verification-email）。
  - `plugins`: `admin({ defaultRole: "member", adminRoles: ["owner", "admin"] })`、`jwt({ jwt: { issuer, audience: "arag-api", expirationTime: "15m", definePayload } })`、`nextCookies()`。
  - `databaseHooks.user.create.before`: 利用者が 0 人なら `role: "owner"`。
  - `trustedOrigins`: `BETTER_AUTH_URL`。
- `src/lib/auth/mail.ts`: nodemailer（`ARAG_SMTP_URL`、`ARAG_MAIL_FROM`）。未設定ならログ出力。件名・本文は日本語。
- `src/lib/auth/migrate.ts` + `src/instrumentation.ts`: 起動時に `CREATE SCHEMA IF NOT EXISTS auth` → `getMigrations(options).runMigrations()`。
- `src/lib/auth/token-cache.ts`: セッション ID → `{jwt, exp}`。期限 60 秒前で取り直す。上限 1,000 件（古いものから捨てる）。純粋関数部分をテストする。
- `src/lib/api/proxy.ts`: `ProxyOptions.authorize(request) → {headers} | Response`。dev（`ARAG_DEV_USER_ID` 明示）は従来どおり利用者ヘッダ。jwt は session → token。Origin 検査（R14）。
- `src/proxy.ts`（Next 16 の旧 middleware）: `getSessionCookie` が無ければ `/login?next=` へ。`/login`・`/reset-password`・`/api/auth/*`・静的ファイルは対象外。
- 画面:
  - `/login`: ログイン・登録・再設定申請の 3 モード（1 枚のカード）。
  - `/reset-password?token=`: 新しいパスワードの設定。
  - 確認リンクの戻り先は `/?verified=1`（失敗時 `/?error=...`）。ChatApp がトーストで知らせる。
  - 未確認の帯（`UnverifiedBanner`）: ChatApp の上部。再送ボタン。
  - アカウント（`AccountModal`）: サイドバーの利用者メニューから。表示名・パスワード変更・端末一覧。
- `ChatApp` は `DEV_USER` の代わりに `authClient.useSession()` の利用者を使う。ログアウトで `/login` へ。

## 3. Python（FastAPI）

- `arag/auth/jwt.py`:
  - `JwksCache(url, fetch, min_refetch=30s)`: `key(kid)`。未知の kid で取り直し（30 秒に 1 回まで）。
  - `principal_from_jwt(token, cache, issuer, audience) -> Principal`。PyJWT（`algorithms=["EdDSA"]`）。
- `arag/auth/principal.py`: `auth_mode == "jwt"` で `Authorization: Bearer` を検証。
- 設定: `ARAG_AUTH_JWKS_URL`、`ARAG_AUTH_ISSUER`、`ARAG_AUTH_AUDIENCE=arag-api`。
- run の作成（`POST /v1/runs`、`POST /v1/threads/{id}/runs`）で `email_verified` を確認（R7）。アップロードは既存のとおり。

## 4. compose

- `mailpit`（axllent/mailpit、MIT）: SMTP 1025、UI 8025。
- `web`: `BETTER_AUTH_URL=http://localhost:3100`、`BETTER_AUTH_SECRET`（`.env`）、`ARAG_AUTH_DATABASE_URL`、`ARAG_SMTP_URL=smtp://mailpit:1025`。
- `api`: `ARAG_AUTH_MODE=${ARAG_AUTH_MODE:-jwt}`、`ARAG_AUTH_JWKS_URL=http://web:3000/api/auth/jwks`。評価（`arag.eval`）は API を直接叩くので、`ARAG_AUTH_MODE=dev` で起動したときだけ使える。

## 5. 依存

| 側 | 依存 | 版 | ライセンス |
|---|---|---|---|
| web | better-auth | 1.7.18 | MIT |
| web | pg | 8.23.1 | MIT |
| web | nodemailer | 10.4.0 | MIT-0 |
| api | PyJWT[crypto] | 2.x | MIT（cryptography: Apache-2.0 / BSD） |
| compose | axllent/mailpit | v1 | MIT |
