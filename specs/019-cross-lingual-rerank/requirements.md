# 019 日英をまたぐ検索 — 要件

## 背景

harukaze_mix の hm48（「ペナン工場でポンプを分解したとき、作業の記録にはどの様式を使いますか？」）で、
答えのある英語の手順書 e01 ではなく、同じ話題の日本語の手順書 w03 を引いて誤答した。

- エージェントは「ペナン工場 分解記録 作業様式」のような語の並びで検索する。e01 は 2 位・並べ替えの得点 0.003 で、低関連の注意が付き、書き直した問いでは候補から落ちた。
- e01 の該当チャンク（「Record the job on form PN-QF-12 …」）の本文には「Penang」が無い。地名は見出し「HP-300 Pump Overhaul Procedure — Penang Plant > 2. Records」にだけある。
- 並べ替え（ruri reranker）には文脈 + 本文だけを渡しており、見出しは渡していなかった。

## 要件

- R1 並べ替えの入力に見出しパスを含められるようにする（`rerank_input = "heading+context+text"`）。
- R2 検索評価（harukaze_mix・agentic_rag_demo・agentic_rag_demo_ext・jqara・beir_scifact）で、既定の構成より悪くならないなら既定にする。
- R3 hm48 の回答評価が通ること。
