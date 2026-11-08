"""環境変数（ARAG_*）から読む設定。"""

from typing import Any, Literal

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
    ready_timeout_sec: float = 2.0
    log_level: str = "INFO"

    # --- P1 入庫（specs/003-ingestion/design.md §6）---
    # dev: X-Dev-User-Id / X-Dev-Role ヘッダで利用者を指定（P4 で jwt を追加）
    auth_mode: Literal["dev", "jwt"] = "dev"
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
    rerank_input: Literal["context+text", "text"] = "context+text"
    rerank_timeout_sec: float = 10.0
    ingest_max_retries: int = 3
    ingest_concurrency: int = 2
    trash_retention_days: int = 30
    http_timeout_sec: float = 60.0
