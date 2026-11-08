"""結合テスト用の DB（compose の postgres に `arag_test` を作り、Alembic で head まで上げる）。"""

import contextlib
import os
import subprocess
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from arag.db.engine import make_engine, make_sessionmaker
from arag.db.models import Base
from arag.main import create_app
from arag.settings import Settings

if TYPE_CHECKING:
    from arag.ingest.index import QdrantIndex

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


class RecordingSync:
    """payload 同期の呼び出しを記録する偽物。"""

    def __init__(self) -> None:
        self.calls: list[set[str]] = []

    async def sync(self, content_hashes: Iterable[str]) -> None:
        self.calls.append(set(content_hashes))


@pytest.fixture
def payload_sync() -> RecordingSync:
    return RecordingSync()


@pytest.fixture
def storage_root(tmp_path: Path) -> str:
    return str(tmp_path / "storage")


@pytest.fixture
async def make_client(
    engine: AsyncEngine,
    database_url: str,
    storage_root: str,
    payload_sync: RecordingSync,
) -> AsyncIterator[Callable[..., Awaitable[httpx.AsyncClient]]]:
    """設定を変えたクライアントを作る（終了時に片付ける）。"""
    stack = contextlib.AsyncExitStack()

    async def make(index: "QdrantIndex | None" = None, **overrides: object) -> httpx.AsyncClient:
        settings = Settings(
            database_url=database_url,
            storage_dir=storage_root,
            auth_mode="dev",
            **overrides,  # type: ignore[arg-type]
        )
        # index を渡すと API も同じ索引を使う（完全削除で点が消えることを確かめる）
        app = create_app(settings=settings, checks=[], payload_sync=payload_sync, index=index)
        c = await stack.enter_async_context(
            httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=30)
        )
        stack.push_async_callback(app.state.engine.dispose)
        stack.push_async_callback(app.state.redis.aclose)
        return c

    async with stack:
        yield make


@pytest.fixture
async def client(make_client: Callable[..., Awaitable[httpx.AsyncClient]]) -> httpx.AsyncClient:
    return await make_client()


def as_user(user_id: str, role: str = "member") -> dict[str, str]:
    return {"X-Dev-User-Id": user_id, "X-Dev-Role": role}


ADMIN = as_user("admin1", "admin")
ALICE = as_user("alice")
BOB = as_user("bob")


@pytest.fixture
async def qdrant_index() -> AsyncIterator["QdrantIndex"]:
    from qdrant_client import AsyncQdrantClient

    from arag.ingest.index import QdrantIndex

    client = AsyncQdrantClient(url=Settings().qdrant_url, timeout=5)
    try:
        await client.get_collections()
    except Exception as e:
        pytest.skip(f"qdrant に接続できません（make up-infra）: {e}")
    index = QdrantIndex(client, alias=f"test_{uuid.uuid4().hex[:8]}")
    yield index
    await client.delete_collection(index.collection)
    await client.close()
