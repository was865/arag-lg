# 008 スレッドの共有 — 設計

- DB: `app.threads` に `visibility varchar(16) not null default 'private'`（check 制約）と `share_token varchar(32) unique null`。マイグレーション 0003。
- API（`agent/router.py`）:
  - `ThreadOut` に `visibility`・`share_token`。`ThreadPatch` に `visibility`。トークンは `secrets.token_urlsafe(16)`（22 文字・128 bit）。
  - `GET /v1/shared/{token}` → `SharedThreadOut {title, visibility, messages: [{query, answer, created_at, sources: [{n, title}]}]}`。完了・取り消し以外のメッセージは除く。
  - 認証は任意: `optional_principal`（ヘッダが無い・不正なら None）。
- Web:
  - `lib/auth/guard.ts`: `/s/` をログイン不要に。
  - `lib/api/proxy-env.ts`: `serverApiHeaders(headers)`（あればセッションの JWT、dev なら利用者ヘッダ）。
  - `app/s/[token]/page.tsx`（サーバで API を呼ぶ）＋ `components/share/shared-thread.tsx`。`robots: noindex`。
  - `components/chat/share-dialog.tsx` とチャットヘッダのボタン。`lib/share.ts`（`shareUrl`・出典の並べ方）にテスト。
