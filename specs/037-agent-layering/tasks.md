# 037 — タスク

- [x] T1 依存の向き: `secret_box`・`user_departments`・検索の計測の口を移し、`test_layering.py` を足す（R1〜R4）
- [x] T2 ツールの結果の構造: `ToolOutput`、ツールの artifact、要約・primer・省略の確認を構造で判断（R5〜R7）
- [x] T3 確認の規則の登録: `review_rules.py`・`Draft`・`review_counts`（R8〜R10）
- [x] T4 文書の読み出しの口: `DocumentStore`・`SqlDocumentStore`（R11）
- [x] T5 runner: 使っていない import を外し、実行文脈の組み立てを分ける（R12）
- [x] T6 `make lint test`・結合テスト・harukaze_mix（69 題）で確かめる（2026-11-21、`eval/.reports/hm-gemma4-12b-037`）
  - 034-on2 と比べ、引用再現率 0.986 は同じ。事実網羅 1.000 → 0.978 の差は 2 題で、どちらも整理によるものではない:
    hm54 は「5キット」を「5 kits」と書いた表記の差。hm58（資料に無い題）は、モデルが課題の管理を
    「不良率」で引き、Q-003 の経過（10月の不良率 0.4%）を出典付きで答えた（前回は別の語で引いて 0 行）
- [ ] T7 （後）今の値を問う語を登録の情報へ（R13）
- [x] T8 `domain/`・`adapters/` への物理的な移動と検査（R14）、検索の口から session を外す（R15）
