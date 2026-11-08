"""環境変数（ARAG_*）から読む設定。"""

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
