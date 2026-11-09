# 024 部門とナレッジベースの利用範囲 — 設計

## 置き場所

- 部門・共有リストは API の DB（`app` スキーマ）に置き、利用者は **user_id だけ**で持つ。
- 名前・メールは Better Auth の `auth.user` にある。API はこれを読まない（テスト DB に無く、表の持ち主も Web）。
  名前の解決と人の検索は Web の `/api/people`（`authPool` で `auth.user` を読む。ログインしていれば誰でも。停止中の人は出さない）。

## 表

- `departments(id, name UNIQUE, created_at)` — 削除は物理削除。その部門を指す共有リストの行も消す（監査に残す）。
- `department_members(department_id FK CASCADE, user_id, role member|manager)`、主キーは `(department_id, user_id)`。
- `kb_shares(id, kb_id FK CASCADE, subject_type everyone|department|user, subject_id, role viewer|editor|manager, created_by, created_at)`、
  `subject_id` は everyone のとき空文字。`(kb_id, subject_type, subject_id)` で一意。

移行（0006）: 生きている全社 KB に「全員: 閲覧」。管理は、今の admin（`auth.user` があれば）と、その KB に文書を上げたことのある人
（これまで全社 KB に書けたのは admin だけなので、その時点の admin）に付ける。今の見え方・書き方を変えない。

## 判定（`kb/access.py`・`kb/permissions.py`）

- `Access`: Principal・所属部門・部門管理者である部門・`kb_roles`（共有 KB → いちばん強い役割）。1 要求で 2 回の SQL。
  `get_ctx` が作り `ctx.access` に持つ。エージェントの検索範囲（`resolve_scope`）は中で作る。
- 個人 KB: 持ち主は「管理」、他人は無し（今と同じ）。
- 共有 KB: `kb_roles` の役割。admin でも役割が無ければ中身は読めない（Q1 案 A）。
- 管理操作（共有リスト・名前変更・アーカイブ・削除・復元）: 共有 KB の「管理」か admin。
- 完全削除（purge）: 共有 KB の「管理」と、書ける admin はいつでも。アップロードした本人は 24 時間以内（今と同じ）。
- SQL の絞り込み（一覧・統計・概要・ジョブの可視性）は「個人 KB の持ち主」か「`kb_roles` の id」で作る。

## API

- 部門: `GET/POST /v1/departments`、`PATCH/DELETE /v1/departments/{id}`（admin）、
  `GET /v1/departments/{id}/members`、`PUT/DELETE /v1/departments/{id}/members/{user_id}`
  （admin は役割も、部門管理者は「メンバー」の追加・削除だけ）。
- 共有リスト: `GET /v1/kbs/{id}/shares`（読める人と admin。部門の行には部門の user_id を添える）、
  `PUT /v1/kbs/{id}/shares`（リスト全体を置き換え。差分を監査に残す。全員は閲覧だけ・管理が 1 行以上）。
- KB の作成: admin か部門管理者。`department_id` を渡すと既定が「その部門: 閲覧」。部門管理者は自分の部門だけ。
- `KbOut` に `role`・`can_manage`・`shared_with_everyone` を足す。`GET /v1/kbs?manageable=true` は admin に全共有 KB を返す（読めない KB も、名前と共有リストの管理のため）。
- 人の理由: `GET /v1/admin/users/{user_id}/access`（admin）— その人の共有 KB ごとの役割と理由（どの行から来たか）。

## 共有スレッド（R16）

共有ページの引用は、見る人（ログインしていなければ「全員: 閲覧」の KB だけ）が読めない文書なら、本文・文書名・見出しを伏せる。

## 画面

- ライブラリの見出しに共有の要約と「共有」ボタン → 共有パネル（人と部門の検索・役割・外す・狭めるときの確認）。
- 管理コンソールに「部門」タブ（作成・名前・メンバー・部門管理者）と「ナレッジベース」タブ（全共有 KB と共有の要約）。
- メンバーの行から「見られるナレッジベース」（R13）。
- サイドバーの KB 行: 全員に公開でなければ鍵。
