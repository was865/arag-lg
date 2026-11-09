"""環境変数（ARAG_*）から読む設定。"""

from typing import Any, Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 既定値は compose.yaml のホスト側ポート（旧版 a-rag と衝突しない番号）に合わせる
    model_config = SettingsConfigDict(env_prefix="ARAG_", env_file=("../.env", ".env"), extra="ignore")

    database_url: str = "postgresql://arag:arag@localhost:5433/arag"
    qdrant_url: str = "http://localhost:6343"
    redis_url: str = "redis://localhost:6380/0"
    # 空文字は「未設定」= readiness で skipped（GPU 機が止まっていても開発を続けられる）
    tei_embed_url: str = ""
    tei_rerank_url: str = ""
    # --- 推論の部品（specs/016-inference-modules）---
    # 埋め込み: tei（自前）か openai（OpenAI 互換 /embeddings）。URL 未設定なら tei_embed_url を使う
    embed_provider: Literal["tei", "openai"] = "tei"
    embed_url: str = ""
    embed_api_key: SecretStr = SecretStr("")
    embed_dimensions: int = 0  # 0 はモデルの既定（API が対応するときだけ送る）
    # 並べ替え: tei（自前）か cohere（Cohere 互換 /rerank）。URL 未設定なら tei_rerank_url を使う
    rerank_provider: Literal["tei", "cohere"] = "tei"
    rerank_url: str = ""
    rerank_api_key: SecretStr = SecretStr("")
    ready_timeout_sec: float = 2.0
    log_level: str = "INFO"

    # --- P1 入庫（specs/003-ingestion/design.md §6）---
    # dev: X-Dev-User-Id / X-Dev-Role ヘッダで利用者を指定（開発・評価用）
    # jwt: Better Auth の JWT を JWKS で検証する（specs/006-auth）
    auth_mode: Literal["dev", "jwt"] = "dev"
    auth_jwks_url: str = "http://localhost:3100/api/auth/jwks"
    auth_issuer: str = "http://localhost:3100"
    auth_audience: str = "arag-api"
    storage_dir: str = "./.data/storage"
    docling_url: str = ""
    docling_page_window: int = 20
    # 空なら docling-serve の既定（RapidOCR・PP-OCRv5 多言語。日本語も読める）。
    # RapidOCR は 1 言語のみ（例 "iso:ja"）。"ja,en" のような複数指定は変換が失敗する
    docling_ocr_lang: str = ""
    docling_timeout_sec: float = 900.0
    upload_max_mb: int = 200
    chunk_max_tokens: int = 512
    section_max_tokens: int = 2000
    section_level: int = 2
    embed_tokenizer: str = "BAAI/bge-m3"
    embed_model: str = "BAAI/bge-m3"
    # モデル別の接頭辞（ruri-v3: "検索文書: " / "検索クエリ: "）
    embed_document_prefix: str = ""
    embed_query_prefix: str = ""
    embed_batch_size: int = 32
    context_model: str = ""
    context_concurrency: int = 8
    # 自前の OpenAI 互換サーバ（vLLM 等）。context_model は "openai:<served-model-name>" にする
    context_base_url: str = ""
    # init_chat_model への追加引数（JSON）。例: {"temperature": 0, "extra_body": {...}}
    context_model_kwargs: dict[str, Any] = {}
    # 全文を渡す上限（超えたら該当 ±2 セクション）。文脈長の短い自前モデルでは下げる
    context_max_document_tokens: int = 60_000
    vlm_model: str = ""
    # 自前の OpenAI 互換サーバ（vLLM の Qwen2.5-VL 等）。vlm_model は "openai:<served-model-name>" にする
    vlm_base_url: str = ""
    vlm_model_kwargs: dict[str, Any] = {}
    # 質問に添える画像（specs/017）。保存前に長辺をこの値まで縮め、受け付ける元の大きさの上限
    query_image_max_px: int = 1280
    query_image_max_bytes: int = 8_000_000
    sudachi_mode: Literal["A", "B", "C"] = "B"
    bm25_avgdl: float = 200.0
    # 英語の語幹化（Snowball）。既定は off（specs/004-retrieval §10 の評価で決める）
    sparse_en_stem: bool = False
    qdrant_collection: str = "chunks"
    # 検索（specs/004-retrieval §7）
    search_fusion: Literal["rrf", "dbsf"] = "rrf"
    search_rrf_k: int = 60
    search_weights: str = "1,1"  # dense,sparse
    rerank_enabled: bool = True
    rerank_input: Literal["heading+context+text", "context+text", "text"] = "heading+context+text"
    rerank_timeout_sec: float = 10.0
    # rerank のモデル名。TEI では記録用（載せているモデル）、API では要求に入れる（specs/004 report §4・016）
    rerank_model: str = "cl-nagoya/ruri-v3-reranker-310m"
    # rerank 入力（文脈 + 本文）の文字数上限。長い英語文書で所要時間が延びるのを抑える（0 は上限なし）
    rerank_max_chars: int = 0
    ingest_max_retries: int = 3
    ingest_concurrency: int = 2
    trash_retention_days: int = 30
    http_timeout_sec: float = 60.0

    # --- P3 エージェント（specs/005-agent/design.md §9）---
    # モデル目録（JSON）: [{id, label, model, base_url?, kwargs?, tags?}]。先頭の利用可能なものが既定
    chat_models: list[dict[str, Any]] = []
    # 書き換え・要約用（目録の id。空なら会話モデルと同じ）
    utility_model: str = ""
    # 画面で登録する API キーの暗号化鍵（Fernet。カンマ区切りで入れ替え。specs/013-llm-keys）
    secret_key: SecretStr = SecretStr("")
    # Web の中継と共有する合言葉。合うときだけ利用者の IP（X-ARag-Client-IP）を監査ログに使う
    forward_secret: SecretStr = SecretStr("")
    run_concurrency: int = 8
    run_heartbeat_sec: float = 10.0
    run_stale_sec: float = 60.0
    run_events_ttl_sec: int = 3600
    rate_limit_runs_per_min: int = 20
    monthly_token_limit: int = 0  # 0 は無制限
