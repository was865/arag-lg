# 013 設計

## 暗号化

- `arag/secrets.py` の `SecretBox`。`cryptography.fernet.MultiFernet`（`pyjwt[crypto]` 経由で既に入っている。Apache-2.0/BSD）。
- `Settings.secret_key: SecretStr`（`ARAG_SECRET_KEY`）。空・不正なら `SecretBox.from_setting()` は None。
- 鍵の作り方は `.env.example` に書く: `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`。

## テーブル（app スキーマ、migration 0004）

- `llm_credentials`: id uuid PK, provider str32, label str100, secret_enc text NULL, key_hint str8 NULL, base_url str500 default '', created_by str64, created_at, updated_at
- `llm_models`: id str64 PK, label str100, model str200, credential_id uuid NULL FK→llm_credentials（RESTRICT）, kwargs jsonb, tags jsonb, enabled bool, position int, created_at, updated_at

## 目録

- `ModelSpec` に `api_key`（repr しない）を足し、`chat_model(..., api_key=)` に渡す。
- `arag/agent/catalog.py` の `load_catalog(session, settings) -> ModelCatalog` が R5 の合成をする。
- `GET /v1/models` と `POST /v1/runs` は `load_catalog` を使う。ワーカーの `resolve_models` も実行ごとに読む（`resolve_models` は同期・非同期どちらも受ける）。

## API（`arag/llm_admin_router.py`）

| メソッド | パス | 内容 |
|---|---|---|
| GET | /v1/admin/llm | `{encryption_ready, providers, credentials[], models[]}`（models は合成後の並び。`source: db/env`, `available`, `is_default`） |
| POST | /v1/admin/llm/credentials | 作成 201 |
| PATCH | /v1/admin/llm/credentials/{id} | label・base_url・api_key（入れ替え） |
| DELETE | /v1/admin/llm/credentials/{id} | 使用中は 409 |
| POST | /v1/admin/llm/models | 作成 201（id 重複は 409） |
| PATCH | /v1/admin/llm/models/{id} | 部分更新 |
| DELETE | /v1/admin/llm/models/{id} | 204 |
| PUT | /v1/admin/llm/models/order | `{ids}` の順に position を振り直す |
| POST | /v1/admin/llm/models/{id}/test | `{ok, latency_ms, error}`（20 秒で打ち切り） |

`.env` 由来のモデルを画面で変えたいときは、同じ id で DB に作れば上書きになる（「目録に取り込む」ボタン）。

## 画面

`/admin/models`。`AdminHeader` に「モデル」タブ。接続とモデルはそれぞれダイアログで編集する。
