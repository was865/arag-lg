"""質問に添えた画像を読み取ってから答える（specs/017-query-image A4）。"""

import uuid
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.agent.query_image import image_key
from arag.agent.runner import claim, execute_run
from arag.agent.service import RunRequest, create_run
from arag.db.models import Message
from arag.storage import LocalStorage

from ..agent_fakes import FakeToolModel, script
from .test_agent_runner import ALICE, events, make_deps, redis  # noqa: F401

pytestmark = pytest.mark.integration


class FakeReader:
    def __init__(self, text: str | None = "銘板 MX-17・赤ランプ点灯") -> None:
        self.text = text
        self.calls: list[tuple[bytes, str]] = []

    async def read(self, image: bytes, question: str) -> str:
        self.calls.append((image, question))
        if self.text is None:
            raise RuntimeError("vlm down")
        return self.text


async def _start_with_image(sm: async_sessionmaker[AsyncSession], storage: LocalStorage) -> Any:
    image_id = uuid.uuid4().hex
    key = image_key("alice", image_id)
    await storage.put(key, b"\xff\xd8\xff-jpeg")
    async with sm() as s:
        _th, run = await create_run(
            s,
            ALICE,
            None,
            RunRequest(query="この設備は止めるべき?"),
            "fake",
            image={"id": image_id, "key": key, "width": 10, "height": 8},
        )
        await s.commit()
    async with sm() as s:
        assert await claim(s, "test") == run.id
    return run


def _human_text(model: FakeToolModel) -> str:
    return "\n".join(m.text for m in model.calls[0] if m.type == "human")


async def test_reads_image_before_answering(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,  # noqa: F811
    storage_root: str,
) -> None:
    storage = LocalStorage(storage_root)
    reader = FakeReader()
    model = FakeToolModel(messages=script(AIMessage(content="停止してください。")))
    deps = make_deps(sessionmaker, redis, model, storage=storage, image_reader=reader)
    run = await _start_with_image(sessionmaker, storage)
    assert await execute_run(deps, run.id) == "completed"

    assert reader.calls == [(b"\xff\xd8\xff-jpeg", "この設備は止めるべき?")]
    assert "<image_description>\n銘板 MX-17・赤ランプ点灯\n</image_description>" in _human_text(model)
    steps = [e["step"] for e in await events(redis, run.id) if e["type"] == "step"]
    read = [s for s in steps if s["name"] == "read_image"]
    assert read[0]["status"] == "running" and read[-1]["status"] == "done"
    assert read[-1]["output"] == {"description": "銘板 MX-17・赤ランプ点灯"}
    async with sessionmaker() as s:
        msg = await s.get(Message, run.message_id)
        assert msg is not None
        assert msg.query == "この設備は止めるべき?"  # 表示用の質問文は元のまま
        assert msg.request["image"]["description"] == "銘板 MX-17・赤ランプ点灯"
        assert any(st["name"] == "read_image" for st in msg.steps)


@pytest.mark.parametrize("reader", [FakeReader(None), None])
async def test_continues_when_image_unreadable(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,  # noqa: F811
    storage_root: str,
    reader: FakeReader | None,
) -> None:
    storage = LocalStorage(storage_root)
    model = FakeToolModel(messages=script(AIMessage(content="文字だけで答えます。")))
    deps = make_deps(sessionmaker, redis, model, storage=storage, image_reader=reader)
    run = await _start_with_image(sessionmaker, storage)
    assert await execute_run(deps, run.id) == "completed"
    assert "（添付画像は読み取れませんでした）" in _human_text(model)
    steps = [e["step"] for e in await events(redis, run.id) if e["type"] == "step"]
    assert [s["status"] for s in steps if s["name"] == "read_image"][-1] == "error"
    async with sessionmaker() as s:
        msg = await s.get(Message, run.message_id)
        assert msg is not None and msg.request["image"].get("description") is None
