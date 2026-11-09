# 013 タスク

- [x] A1 SecretBox（暗号化・複数鍵・不正な鍵）— R1・R2
- [x] A2 テーブルと migration 0004
- [x] A3 目録の合成 load_catalog と ModelSpec.api_key — R5
- [x] A4 管理 API（接続・モデル・並べ替え・確認・監査）— R2〜R4・R6・R7
- [x] A5 /v1/models・/v1/runs・ワーカーを load_catalog に切り替え
- [x] B1 画面 /admin/models — R8
- [x] C1 ブラウザで確認（ダミーのキーで登録・使用中の接続の削除拒否・確認の失敗表示・外す・削除、375px。会話が DB 経由の目録で答えること）

## メモ

- 本物のキー（DeepSeek など）の登録は利用者が画面から行う。
- `ARAG_SECRET_KEY` を失うと登録済みのキーは復号できない（その接続のモデルは「キーが無い・読めない」になる）。入れ替えるときは新しい鍵を先頭に足し、キーを登録し直してから古い鍵を外す。
- `ARAG_UTILITY_MODEL` は目録の id を指すので、DB のモデルも指定できる。
- 評価（`arag.eval`）は従来どおり `.env` の目録だけを見る。
