# 035 ERP への書き戻し — 設計（草案）

- 流れ: エージェントの回答の後処理が提案（JSON）を作る → 画面の確認の札 → api `POST /v1/actions/erp/{kind}`
  （利用者の身元で）→ erp-mcp の書き込みの口 → Odoo の `write`（`purchase.order.line.date_planned`）。
- 楽観的な確かめ: 提案に `write_date` と今の値を持たせ、書く前に読み直して一致を確かめる（R6）。
- 権限: erp-mcp の users.yaml に `write: [date_planned]` を足した利用者（erp-kobai）だけ。Odoo の側でも購買の権限が要る。
- 監査: erp-mcp の audit.jsonl に `action` の行（before・after・trace）。ARag はステップ `erp_write`（`record_system`）。
- 元に戻す: 監査の行の before を、同じ確かめをして書く（1 回だけ）。
