"""環境変数（ARAG_*）から読む設定。"""

from typing import Literal

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
    docling_ocr_lang: str = "ja,en"
    docling_timeout_sec: float = 900.0
    upload_max_mb: int = 200
    chunk_max_tokens: int = 512
    section_max_tokens: int = 2000
    section_level: int = 2
    embed_tokenizer: str = "BAAI/bge-m3"
    embed_model: str = "BAAI/bge-m3"
    embed_batch_size: int = 32
    context_model: str = ""
    context_concurrency: int = 8
    vlm_model: str = ""
    sudachi_mode: Literal["A", "B", "C"] = "B"
    bm25_avgdl: float = 200.0
    qdrant_collection: str = "chunks"
    ingest_max_retries: int = 3
    ingest_concurrency: int = 2
    trash_retention_days: int = 30
    http_timeout_sec: float = 60.0
