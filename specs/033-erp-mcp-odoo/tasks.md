# 033 — タスク

状態: 承認済み（2026-11-20）。各項目は先に失敗するテストを書く。034 の A（模擬器）と並べて進める。

## A. 土台

- [ ] T1 採否の記録（Odoo を外部の評価・デモ用のシステムとして使う。`decisions.md`・`licenses.md`） — R26
- [ ] T2 compose の profile `erp`（`odoo:18`・`odoo-db`・`erp-mcp`）と `make up-erp`・`make erp-reset` — R23
- [ ] T3 `mcp/erp/` の骨格（uv の別プロジェクト・Dockerfile・FastMCP・JWT の確認（`kid`）・監査の行ログ） — R1・R8・R11

## B. アダプタとツール

- [ ] T4 `ErpBackend` の端口と mock アダプタ（032 の SQLite を読む）。契約のテスト — R6
- [ ] T5 Odoo のアダプタ（JSON-RPC・domain の組み立て・ページ送り・`too_many`・項目の対応の YAML） — R4・R5・R7
- [ ] T6 ツール 6 つ（§3.1）と説明。出力の形（`next_cursor`・`trace`） — R2・R3
- [ ] T7 部門 → ERP の利用者・伏せる列・`forbidden` — R9・R10
- [ ] T8 接続の使い回し・同時数の上限・止める仕組み・10 秒の使い回し・`/health`。ARag の `mcp/client.py` の接続の使い回し — R12〜R15

## C. 画面

- [ ] T9 取得の時点の経過（`ago()`）— R16
- [ ] T10 「最新にする」（api の口・前の値との差・`mcp_refresh` の記録） — R17
- [ ] T11 問い合わせ中の経過の秒と、終わった後の件数・所要時間 — R18
- [ ] T12 接続の状態（redis・`/v1/systems/status`・入力欄の札） — R19
- [ ] T13 時点の比較の表 — R20
- [ ] T14 管理画面の呼び出しの数字 — R21

## D. 評価とデモ

- [ ] T15 harukaze_systems を Odoo のアダプタで流す（違う題は理由を題集に書く） — R24
- [ ] T16 `docs/demo-erp.md` の台本と、3100 で一度通す — R25
- [ ] T17 書き戻しの設計を別の仕様の草案にする — R22
