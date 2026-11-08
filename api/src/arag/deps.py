"""ルーターが使う共通の依存関数。"""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from arag.settings import Settings
from arag.storage import Storage


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_storage(request: Request) -> Storage:
    storage: Storage = request.app.state.storage
    return storage


def request_id_of(request: Request) -> str | None:
    return request.headers.get("x-request-id")
