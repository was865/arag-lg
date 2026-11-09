# 013 LLM の接続（API キー）とモデル目録 — 要件

P5 管理。owner・admin が画面から LLM の API キーを登録し、会話で選べるモデルを並べ替え・有効化できるようにする。
これまでの `.env`（`ARAG_CHAT_MODELS` と各社の `*_API_KEY`）は残し、画面で登録したものを優先する。

## 要件

- R1 **暗号化して保存する。** API キーは `ARAG_SECRET_KEY`（Fernet 鍵。カンマ区切りで複数並べると先頭で暗号化し、全部で復号＝鍵の入れ替え）で暗号化して DB に保存する。平文は DB・ログ・監査ログ・API の応答のどこにも出さない。応答には末尾 4 文字（`key_hint`）だけを返す。
- R2 **鍵が無いときは登録できない。** `ARAG_SECRET_KEY` が無い・不正なら、接続の登録と鍵の更新は 503 `secret_key_missing`。一覧は `encryption_ready: false` を返し、画面は設定方法を案内する。
- R3 **接続（credential）。** provider は `openai` / `anthropic` / `deepseek` / `google_genai` / `openai_compatible`。`openai_compatible` は `base_url` 必須・キーは任意（vLLM など）。他は `base_url` 任意・キー必須。名前（label）と base_url は後から変えられ、キーは入れ替えのみ（読み出し不可）。モデルが使っている接続は消せない（409 `credential_in_use`）。
- R4 **モデル目録。** モデルは `id`（英小文字・数字・`-`・`_`、64 文字まで）、表示名、`<provider>:<model名>`、接続（任意）、追加引数（JSON オブジェクト）、タグ、有効・無効、並び順を持つ。接続を指定するとき、`model` の接頭辞は接続の provider と一致すること（`openai_compatible` は `openai:`）。違えば 422。
- R5 **目録の合成。** 会話で使う目録は「DB の有効なモデル（並び順どおり）」の後に「`.env` のモデルのうち DB に同じ id が無いもの」を並べる。DB で無効にした id は `.env` にあっても出さない。DB のモデルは、接続があれば復号できたときだけ利用可、接続が無ければ従来どおり環境の鍵で判定する。先頭の利用可能なものが既定。目録は要求ごと・実行ごとに DB から読むので、変更は再起動なしで次の質問から効く。
- R6 **接続の確認。** モデルごとに「接続を確認」で短い問い合わせを 1 回送り、成功・失敗と所要時間を返す（失敗理由はキーを含めない）。
- R7 **権限と監査。** すべて owner・admin のみ（他は 403）。`llm.credential.create/update/delete`、`llm.model.create/update/delete/reorder` を監査ログに残す（detail にキーは入れない。鍵を入れ替えたかどうかだけ）。
- R8 **画面。** 管理画面に「モデル」タブ。接続の一覧（provider・名前・末尾 4 文字・base_url）と追加・編集・削除、モデル目録の一覧（並べ替え・有効切替・既定の表示・`.env` 由来は読み取り専用で表示）と追加・編集・削除・接続の確認。
