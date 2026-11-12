# 026 タスク

- [x] T1 `understand.py`: 整理のプロンプトと JSON の読み取り（失敗時の既定）— R1〜R4
- [x] T2 `primer.py`: 最初の検索（並行・重複の省略・雑談は渡さない）とステップ — R5〜R9・R18
- [x] T3 `middleware.py`: 検索結果を添える・ツールの強制を消す — R10・R11
- [x] T4 `table.py` と `table_query` ツール — R12・R13
- [x] T5 `numbers.py`: 数字の取り出しと照合 — R15
- [x] T6 差し戻し（gap / table / numbers）と数字の照合の記録 — R14・R16・R17・R18
- [x] T7 プロンプト（`agent_system.md`・`agent_understand.md`）
- [x] T8 runner・評価: 回答不能の分類と、ツール数の数え方
- [x] T9 画面: understand・自動の札・table_query・review の種類・数字の注意・段階の表示 — R19・R20
- [ ] T10 実機（3100）で確かめ、harukaze_mix で Qwen3-8B と Gemma 4 12B を比べる — R21

## 現状（2026-11-12）

- T1〜T8（後端）は実装済み。api のテスト 472 件が通る。runner は作り直し済み。
- 実機（Qwen3-8B、7 題だけ）: hm17（在庫 < 発注点）は table_query で正答。事実網羅 7/7。
- 残り:
  - T9 画面（`web/src/components/chat/tool-steps.tsx`・`agent-activity.tsx`・`web/src/lib/chat/evidence.ts`・`web/src/i18n/locales/ja/chat.ts`・`web/src/lib/types.ts`）。
    新しいステップ: `understand`（output: kind・queries・table・error）、`search` の `input.by == "system"`、
    `table_query`（input: source・where・compute、output.result は Markdown の表）、
    `review` の `input.kind`（gap / table / numbers）、`system` の `number_check`（output.unverified）。
  - T10 harukaze_mix 69 題を Qwen3-8B と Gemma 4 12B で回し、変更前（eval/.reports/hm-qwen3-8b・hm-gemma4-12b）と比べる。
  - 気になる点: hm62-turn（追質問）で引用が付かなかった。hm56-noans は 3.7 秒（差し戻しが 1 回入る）。

## 再評価（2026-11-13、Qwen3-8B、harukaze_mix 69 題。変更前 → 変更後）

| 指標 | 前 | 後 |
|---|---|---|
| 事実網羅 | 0.920 | 0.928 |
| 引用再現率 | 0.957 | 0.928 |
| 引用精度 | 0.850 | 0.914 |
| 回答不能率 | 0.014 | **0.116** |
| 誤りの値 | 1 | 0 |
| p50 / p95 (ms) | 1217 / 2561 | 1447 / 3414 |

- 良くなった 14 題（hm17 表の比較、版の違い、資料に無い質問など）、悪くなった 8 題
  （hm04・hm21・hm23・hm30・hm54・hm62・hm09・hm67）。
- 回答不能率の上昇が R21 の門に反する。原因の調査が要る（差し戻しの誤検知か、整理したクエリか）。未着手。
