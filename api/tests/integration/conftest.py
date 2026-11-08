"""結合テスト用の DB（compose の postgres に `arag_test` を作り、Alembic で head まで上げる）。"""

import os
import subprocess
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from arag.db.engine import make_engine, make_sessionmaker
from arag.db.models import Base
from arag.settings import Settings

API_DIR = Path(__file__).resolve().parents[2]
TEST_DB = "arag_test"


def _admin_url() -> str:
    return Settings().database_url


def _test_url() -> str:
    base = _admin_url().rsplit("/", 1)[0]
    return f"{base}/{TEST_DB}"


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    try:
        with psycopg.connect(_admin_url(), autocommit=True, connect_timeout=3) as conn:
            exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)).fetchone()
            if not exists:
                conn.execute(f'CREATE DATABASE "{TEST_DB}"')
    except psycopg.OperationalError as e:
        pytest.skip(f"postgres に接続できません（make up-infra）: {e}")
    env = {**os.environ, "ARAG_DATABASE_URL": _test_url()}
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"], cwd=API_DIR, env=env, check=True, capture_output=True
    )
    yield _test_url()


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    eng = make_engine(database_url)
    # テストごとに app スキーマの全表を空にする
    tables = ", ".join(f"app.{t.name}" for t in Base.metadata.sorted_tables)
    async with eng.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    yield eng
    await eng.dispose()


@pytest.fixture
def sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return make_sessionmaker(engine)
