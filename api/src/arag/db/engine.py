"""非同期エンジンとセッション。"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def sqlalchemy_url(database_url: str) -> str:
    """`postgresql://` を psycopg 3 ドライバ指定の URL にする。"""
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def make_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(sqlalchemy_url(database_url), pool_pre_ping=True)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def session_scope(maker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with maker() as session:
        yield session
