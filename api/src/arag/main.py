"""FastAPI アプリのファクトリ。"""

from fastapi import FastAPI

from arag import health
from arag.health import Check
from arag.logging import configure_logging
from arag.middleware import RequestIdMiddleware
from arag.settings import Settings


def create_app(settings: Settings | None = None, checks: list[Check] | None = None) -> FastAPI:
    """依存（設定・readiness チェック）を注入できるようにして、テストで外部サービスを不要にする。"""
    settings = settings or Settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="ARag API", version="0.1.0")
    app.state.settings = settings
    app.state.checks = checks if checks is not None else health.build_checks(settings)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health.router)
    return app
