"""checkpoint をスキーマ lg に作り、スレッドの状態を保存・削除できる（specs/005-agent A3）。"""

from typing import TypedDict

import psycopg
import pytest
from langgraph.graph import END, START, StateGraph

from arag.agent.adapters.checkpoint import delete_thread, open_checkpointer

pytestmark = pytest.mark.integration


class S(TypedDict):
    n: int


async def test_checkpoint_in_lg_schema(database_url: str) -> None:
    g = StateGraph(S)
    g.add_node("inc", lambda s: {"n": s["n"] + 1})
    g.add_edge(START, "inc")
    g.add_edge("inc", END)
    async with open_checkpointer(database_url, max_size=2) as saver:
        app = g.compile(checkpointer=saver)
        cfg = {"configurable": {"thread_id": "t-1"}}
        assert (await app.ainvoke({"n": 1}, cfg))["n"] == 2
        assert (await app.aget_state(cfg)).values["n"] == 2  # type: ignore[arg-type]
        await delete_thread(saver, "t-1")
        assert (await app.aget_state(cfg)).values == {}  # type: ignore[arg-type]
    with psycopg.connect(database_url) as conn:
        row = conn.execute(
            "SELECT count(*) FROM information_schema.tables"
            " WHERE table_schema = 'lg' AND table_name = 'checkpoints'"
        ).fetchone()
        assert row is not None and row[0] == 1
