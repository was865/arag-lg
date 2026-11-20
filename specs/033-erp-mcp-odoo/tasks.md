# 033 — タスク

状態: 実装済み（2026-11-20）。T15 の Odoo での評価の結果は eval/.reports に置く。

## A. 土台

- [x] T1 採否の記録（Odoo を外部の評価・デモ用のシステムとして使う。`decisions.md`・`licenses.md`） — R26
- [x] T2 compose の profile `erp`（`odoo:18`・`odoo-db`・`erp-mcp`）と `make up-erp`・`make erp-reset` — R23
- [x] T3 `mcp/erp/` の骨格（uv の別プロジェクト・Dockerfile・FastMCP・JWT の確認（`kid`）・監査の行ログ） — R1・R8・R11

## B. アダプタとツール

- [x] T4 `ErpBackend` の端口と mock アダプタ（032 の SQLite を読む）。契約のテスト — R6
- [x] T5 Odoo のアダプタ（JSON-RPC・domain の組み立て・ページ送り・`too_many`・項目の対応の YAML） — R4・R5・R7
- [x] T6 ツール 7 つ（§3.1。`list_below_reorder` は評価のあとで足した）と説明。出力の形（`next_cursor`・`trace`） — R2・R3
- [x] T7 部門 → ERP の利用者・伏せる列・`forbidden` — R9・R10
- [x] T8 接続の使い回し・同時数の上限・止める仕組み・10 秒の使い回し・`/health`。ARag の `mcp/client.py` の接続の使い回し — R12〜R15

## C. 画面

- [x] T9 取得の時点の経過（`ago()`）— R16
- [x] T10 「最新にする」（api の口・前の値との差・`mcp_refresh` の記録） — R17
- [x] T11 問い合わせ中の経過の秒と、終わった後の件数・所要時間 — R18
- [x] T12 接続の状態（redis・`/v1/systems/status`・入力欄の札） — R19
- [x] T13 時点の比較の表 — R20
- [x] T14 管理画面の呼び出しの数字 — R21

## D. 評価とデモ

- [x] T15 harukaze_plant を mock と Odoo のアダプタで流す（値の違う題は無かった。design §11） — R24
- [x] T16 `docs/demo-erp.md` の台本と、3100 で一度通す — R25
- [x] T17 書き戻しの設計を別の仕様の草案にする — R22
- [x] T18 複数のシステムを使い切る試走で見えた穴を埋める（design §12）: 呼んでいないツールの差し戻し（system_missed）、
  `list_below_reorder` の `without_orders`・不足の大きい順 — R2・R25
