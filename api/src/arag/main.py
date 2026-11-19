"""FastAPI アプリのファクトリ。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from qdrant_client import AsyncQdrantClient

from arag import analytics_router, audit_router, feedback_admin_router, health, llm_admin_router
from arag.agent import router as router_agent
from arag.agent.openapi import install_event_schemas
from arag.agent.stream import redis_client
from arag.db.engine import make_engine, make_sessionmaker
from arag.errors import install_error_handlers
from arag.health import Check
from arag.ingest.events import Publisher, RedisPublisher
from arag.ingest.index import QdrantIndex, QdrantPayloadSync
from arag.ingest.pipeline import Index
from arag.kb import router_access, router_documents, router_folders, router_kbs, router_uploads
from arag.kb.sync import PayloadSync
from arag.logging import configure_logging, get_logger
from arag.mcp import live_router as mcp_live_router
from arag.mcp import router as mcp_router
from arag.middleware import RequestIdMiddleware
from arag.search import router as router_search
from arag.search.service import SearchDeps, build_search_deps
from arag.settings import Settings
from arag.storage import LocalStorage


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await app.state.redis.aclose()
    client = getattr(app.state.index, "client", None)
    if client is not None:
        await client.close()
    await app.state.engine.dispose()


def create_app(
    settings: Settings | None = None,
    checks: list[Check] | None = None,
    payload_sync: PayloadSync | None = None,
    publisher: Publisher | None = None,
    index: Index | None = None,
    search_deps: SearchDeps | None = None,
) -> FastAPI:
    """依存（設定・readiness チェック）を注入できるようにして、テストで外部サービスを不要にする。"""
    settings = settings or Settings()
    configure_logging(settings.log_level)
    from arag.inference import describe_inference

    get_logger("arag.main").info("inference_config", **describe_inference(settings))
    app = FastAPI(title="ARag API", version="0.1.0", lifespan=_lifespan)
    app.state.settings = settings
    app.state.checks = checks if checks is not None else health.build_checks(settings)
    # エンジン作成だけでは接続しない（DB が落ちていても起動・/healthz は通る）
    app.state.engine = make_engine(settings.database_url)
    app.state.sessionmaker = make_sessionmaker(app.state.engine)
    app.state.storage = LocalStorage(settings.storage_dir)
    # Qdrant クライアントも作るだけでは接続しない
    app.state.index = index or QdrantIndex(
        AsyncQdrantClient(url=settings.qdrant_url), settings.qdrant_collection
    )
    if payload_sync is None:
        payload_sync = QdrantPayloadSync(app.state.index, app.state.sessionmaker)
    app.state.payload_sync = payload_sync
    client = getattr(app.state.index, "client", None) or AsyncQdrantClient(url=settings.qdrant_url)
    app.state.search_deps = search_deps or build_search_deps(settings, client)
    # from_url は接続しない（初回コマンド時に接続）
    app.state.redis = redis_client(settings.redis_url)
    app.state.publisher = publisher or RedisPublisher(app.state.redis)
    install_error_handlers(app)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health.router)
    app.include_router(router_kbs.router)
    app.include_router(router_access.router)
    app.include_router(router_folders.router)
    app.include_router(router_uploads.router)
    app.include_router(router_documents.router)
    app.include_router(router_search.router)
    app.include_router(router_agent.router)
    app.include_router(audit_router.router)
    app.include_router(feedback_admin_router.router)
    app.include_router(analytics_router.router)
    app.include_router(llm_admin_router.router)
    app.include_router(mcp_router.router)
    app.include_router(mcp_live_router.router)
    install_event_schemas(app)
    return app
