"""run のイベント中継（Redis Stream）と取消フラグ（specs/005-agent C1、R7・R8・R10・R12）。"""

import json
import uuid
from collections.abc import AsyncIterator

import pytest
from pydantic import ValidationError
from redis.asyncio import Redis

from arag.agent.adapters.redis_stream import (
    EventSink,
    is_cancelled,
    read_events,
    request_cancel,
    stream_exists,
)
from arag.settings import Settings

pytestmark = pytest.mark.integration


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    r = Redis.from_url(Settings().redis_url, decode_responses=True)
    try:
        await r.ping()
    except Exception as e:
        pytest.skip(f"redis に接続できません: {e}")
    yield r
    await r.aclose()


async def _all(redis: Redis, run_id: str, last: str = "0") -> list[tuple[str, str, dict]]:  # type: ignore[type-arg]
    out = []
    async for item in read_events(redis, run_id, last, block_ms=200):
        if item is None:
            break
        out.append((item[0], item[1], json.loads(item[2])))
    return out


async def test_sink_batches_deltas_resumes_and_expires(redis: Redis) -> None:
    rid = str(uuid.uuid4())
    sink = EventSink(redis, rid, ttl_sec=60)
    await sink.emit(
        {"type": "run.started", "run_id": rid, "thread_id": "t", "message_id": "m", "model_id": "x"}
    )
    for ch in "こんにちは":
        await sink.emit({"type": "answer.delta", "text": ch})
    await sink.emit({"type": "answer.reset"})  # 未送信の差分は捨てる
    for ch in "回答です":
        await sink.emit({"type": "answer.delta", "text": ch})
    step = {"id": "c1", "name": "search", "label": "検索", "status": "running"}
    await sink.emit({"type": "step", "step": step})  # 差分を先に書き出す
    await sink.emit(
        {
            "type": "run.completed",
            "message_id": "m",
            "answer": "回答です",
            "tokens_in": 1,
            "tokens_out": 2,
            "duration_ms": 3,
            "citation_map": {"1": {"source_id": "d", "section_id": "c"}},
            "sources": [],
        }
    )
    await sink.emit({"type": "answer.delta", "text": "閉じた後は無視"})
    evs = await _all(redis, rid)
    types = [t for _, t, _ in evs]
    # 差分はまとめ書きで、reset 前の未送信分は書かれない
    assert types == ["run.started", "answer.reset", "answer.delta", "step", "run.completed"]
    assert evs[2][2]["text"] == "回答です"
    assert evs[3][2]["step"]["parent_id"] is None  # 既定値も入る
    # Last-Event-ID から再開
    resumed = await _all(redis, rid, evs[2][0])
    assert [t for _, t, _ in resumed] == ["step", "run.completed"]
    assert 0 < await redis.ttl(f"run:{rid}:events") <= 60
    assert await stream_exists(redis, rid)


async def test_invalid_event_is_rejected(redis: Redis) -> None:
    sink = EventSink(redis, str(uuid.uuid4()))
    with pytest.raises(ValidationError):
        await sink.emit({"type": "run.failed", "code": "x"})


async def test_cancel_flag(redis: Redis) -> None:
    rid = str(uuid.uuid4())
    assert not await is_cancelled(redis, rid)
    await request_cancel(redis, rid, ttl_sec=60)
    assert await is_cancelled(redis, rid)
