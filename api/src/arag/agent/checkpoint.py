"""LangGraph の checkpoint（Postgres、スキーマ lg。specs/000-overview/data-model.md §1）。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

SCHEMA = "lg"


def _psycopg_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


@asynccontextmanager
async def open_checkpointer(database_url: str, *, max_size: int = 10) -> AsyncIterator[AsyncPostgresSaver]:
    url = _psycopg_url(database_url)
    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as conn:
        await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    async with AsyncConnectionPool(
        url,
        min_size=1,
        max_size=max_size,
        open=False,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
            "options": f"-c search_path={SCHEMA}",
        },
    ) as pool:
        saver = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
        await saver.setup()
        yield saver


async def delete_thread(saver: AsyncPostgresSaver, thread_id: str) -> None:
    await saver.adelete_thread(thread_id)
