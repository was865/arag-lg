"""FastAPI アプリのファクトリ。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from arag import health
from arag.db.engine import make_engine, make_sessionmaker
from arag.errors import install_error_handlers
from arag.health import Check
from arag.kb import router_folders, router_kbs
from arag.kb.sync import NoopPayloadSync, PayloadSync
from arag.logging import configure_logging
from arag.middleware import RequestIdMiddleware
from arag.settings import Settings
from arag.storage import LocalStorage


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await app.state.engine.dispose()


def create_app(
    settings: Settings | None = None,
    checks: list[Check] | None = None,
    payload_sync: PayloadSync | None = None,
) -> FastAPI:
    """依存（設定・readiness チェック）を注入できるようにして、テストで外部サービスを不要にする。"""
    settings = settings or Settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="ARag API", version="0.1.0", lifespan=_lifespan)
    app.state.settings = settings
    app.state.checks = checks if checks is not None else health.build_checks(settings)
    # エンジン作成だけでは接続しない（DB が落ちていても起動・/healthz は通る）
    app.state.engine = make_engine(settings.database_url)
    app.state.sessionmaker = make_sessionmaker(app.state.engine)
    app.state.storage = LocalStorage(settings.storage_dir)
    app.state.payload_sync = payload_sync or NoopPayloadSync()
    install_error_handlers(app)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health.router)
    app.include_router(router_kbs.router)
    app.include_router(router_folders.router)
    return app
