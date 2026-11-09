# 021 回答評価で誤りの値を見る — 設計

- `Case.wrong_facts: list[KeyFact]`（key_facts と同じ形。項目の表記のどれかが答えに出たら誤り）。照合は key_facts と同じ `canon()`。
- `CaseResult.wrong_checked`（wrong_facts のある題か）と `wrong_facts_found`（出た誤りの値。項目ごとに最初に当たった表記）。
- 集計の `wrong_fact_rate`（表では「誤りの記述」）は、wrong_facts のある題だけの平均。無ければ「—」。報告の末尾に「## 誤りの記述」で題と値を並べる。
- 書くのは、正しい答えが触れる理由の無い値だけにする（旧版の値のように、比べて書くのが自然な値は書かない）。
  - hm22: 600分（表全体の合計）
  - hm37: 7.5 kW（HP-320 の電動機出力。問いは HP-300）
  - hm38: 86 kg（HP-300 の質量。問いは HP-320）
