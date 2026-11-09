# 016 タスク

- [x] A1 OpenAI 互換の埋め込みクライアント（バッチ・再試行・順序・鍵）— R1
- [x] A2 Cohere 互換の並べ替えクライアント（results/data・順序・鍵）— R2
- [x] A3 役割ごとの組み立て（入庫・検索・readiness・構成ログ）— R1・R2・R3・R5
- [x] B1 compose（GPU 機の profile・図の説明用 vLLM・環境変数の受け渡し）と `.env` の例 — R4・R6
- [x] B2 確認（単体テスト・現在の構成で入庫と検索が今までどおり動く）

## 確認メモ（2026-11-09）

- 現在の構成（TEI・docling・vLLM は GPU 機、図の説明は DeepSeek）で readiness が全 ok、検索で rerank が効くことを確認。
- 外部 API の埋め込み・rerank は単体テスト（要求の形・鍵・順序・再試行）のみ。実際の API キーでの確認は未実施。
- 図の説明用 vLLM（`--profile vlm`）は GPU 機で未起動。VRAM の同居と出力の質は GPU 機で確かめる。
