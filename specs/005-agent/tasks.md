# 005 エージェント（P3）— タスク

各タスクは先に失敗するテストを書いてから実装する。「Mac」は開発機、「Win」は GPU 機（TEI・docling-serve・vLLM）。

## A. 土台

- [x] A1 Mac: `arag.llm`（`chat_model` を入庫から移す）、`AgentCfg`（丸め）、モデル目録（`ARAG_CHAT_MODELS`・available・代替）— R24・R28・R29
- [x] A2 Mac: Alembic `0002_agent_threads_runs`（threads・messages・citations・runs・message_feedback、追加列）と ORM — R25
- [x] A3 Mac: `langgraph-checkpoint-postgres` の導入、スキーマ `lg` の `setup()`、licenses.md — R13

## B. エージェント

- [x] B1 Mac: `CitationRegistry`・`normalize_markers`・資料タグの整形と無害化 — R15・R16・R18
- [x] B2 Mac: ツール 5 種（範囲・権限・出典番号）— R14（integration）
- [x] B3 Mac: CRAG（rerank スコア判定 + 書き換え + 再検索、子ステップ）— R17
- [x] B4 Mac: middleware: Step・Citation・Cancel・FinalAnswer、要約、代替モデル — R18・R20〜R22
- [x] B5 Mac: システムプロンプト（日本語、引用必須・不明時の扱い・資料の隔離・回答言語）と回答不能の理由 — R16・R23
- [ ] B6 Mac: 根拠検証・訂正（任意）— R19

## C. run とストリーム

- [x] C1 Mac: イベント型（pydantic → OpenAPI）、`EventSink`（Redis Stream、delta のまとめ書き、TTL）— R10
- [x] C2 Mac: runner（取得・心拍・取りこぼし回収・同時数・取消・保存）— R2・R12・R25
- [x] C3 Mac: API: スレッド CRUD・run 作成（409・新規スレッド）・分岐・active-run・SSE（Last-Event-ID・410・心拍）・取消・`/v1/models` — R1〜R9・R11・R26・R27
- [x] C4 Mac: レート制限・月次上限・監査 — R30〜R32
- [x] C5 Mac+Win: compose に runner を追加し、vLLM（Qwen3-8B・tool calling）で実機確認

## D. UI

- [x] D1 Mac: 旧版の視覚資産（globals.css・フォント・アイコン）と UI 依存の移植、licenses
- [x] D2 Mac: API 中継（Route Handler、SSE をバッファしない）と開発用ヘッダ
- [x] D3 Mac: run のデータ層（EventSource → reducer → `Turn`）と vitest
- [x] D4 Mac: チャット画面（Composer・Messages・ToolSteps・AnswerFooter・引用・右パネル）— R34
- [x] D5 Mac: サイドバー（スレッド一覧・新規・切替・名前変更・ピン・削除）— R36
- [x] D6 Mac: 再接続（active-run・Last-Event-ID）・取消・再生成・質問の編集 — R35

## E. 評価

- [ ] E1 Mac: `python -m arag.eval answer`（引用再現率・精度・事実網羅・ツール数・トークン・時間・回答不能率）— R33
- [ ] E2 Mac: 評価者（忠実度）と人手ラベルの一致確認
- [ ] E3 Mac+Win: `agentic_rag_demo_ext` で旧版基準と比較、`grade_threshold`・`verify` の既定を決めて report.md に
