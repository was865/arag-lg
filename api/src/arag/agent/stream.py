"""run のイベントの中継（Redis Stream）と取消フラグ（specs/005-agent design §4）。"""

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from redis.asyncio import Redis

from arag.agent.events import RUN_EVENT, TERMINAL

MAXLEN = 5000
FLUSH_CHARS = 64
FLUSH_SEC = 0.05
# XREAD で待つ時間（この間に何も無ければ心拍を返す）
READ_BLOCK_MS = 15_000


def redis_client(url: str) -> Redis:
    """中継用の Redis クライアント。

    redis-py 8 は読み取りタイムアウトの既定が 5 秒で、XREAD の待ち（READ_BLOCK_MS）より短い。
    そのままだとモデルが 5 秒以上イベントを出さないだけで読み取りが失敗し SSE が切れるので、待ちより長くする。
    """
    return Redis.from_url(url, decode_responses=True, socket_timeout=READ_BLOCK_MS / 1000 + 10)


def events_key(run_id: str) -> str:
    return f"run:{run_id}:events"


def cancel_key(run_id: str) -> str:
    return f"run:{run_id}:cancel"


class EventSink:
    """イベントを検証して Redis Stream に書く。回答の差分はまとめ書きする。"""

    def __init__(self, redis: Redis, run_id: str, *, ttl_sec: int = 3600) -> None:
        self.redis = redis
        self.key = events_key(run_id)
        self.ttl = ttl_sec
        self._buf = ""
        self._buf_t = 0.0
        self.closed = False

    async def _xadd(self, ev: dict[str, Any]) -> None:
        data = RUN_EVENT.validate_python(ev).model_dump(mode="json")
        await self.redis.xadd(
            self.key,
            {"type": data["type"], "data": json.dumps(data, ensure_ascii=False)},
            maxlen=MAXLEN,
            approximate=True,
        )

    async def flush(self) -> None:
        if self._buf:
            text, self._buf = self._buf, ""
            await self._xadd({"type": "answer.delta", "text": text})

    async def emit(self, ev: dict[str, Any]) -> None:
        if self.closed:
            return
        if ev.get("type") == "answer.delta":
            if not self._buf:
                self._buf_t = time.monotonic()
            self._buf += ev["text"]
            if len(self._buf) >= FLUSH_CHARS or time.monotonic() - self._buf_t >= FLUSH_SEC:
                await self.flush()
            return
        if ev.get("type") == "answer.reset":
            self._buf = ""
        else:
            await self.flush()
        await self._xadd(ev)
        if ev.get("type") in TERMINAL:
            self.closed = True
            await self.redis.expire(self.key, self.ttl)


async def read_events(
    redis: Redis, run_id: str, last_id: str = "0", *, block_ms: int = READ_BLOCK_MS
) -> AsyncIterator[tuple[str, str, str] | None]:
    """(id, type, data) を順に返す。block_ms の間に何も無ければ None（心拍用）。終了イベントで止まる。"""
    key = events_key(run_id)
    while True:
        resp: Any = await redis.xread({key: last_id}, count=200, block=block_ms)
        if not resp:
            yield None
            continue
        for _key, entries in resp:
            for entry_id, fields in entries:
                last_id = entry_id if isinstance(entry_id, str) else entry_id.decode()
                typ, data = fields["type"], fields["data"]
                yield last_id, typ, data
                if typ in TERMINAL:
                    return


async def request_cancel(redis: Redis, run_id: str, *, ttl_sec: int = 3600) -> None:
    await redis.set(cancel_key(run_id), "1", ex=ttl_sec)


async def is_cancelled(redis: Redis, run_id: str) -> bool:
    return bool(await redis.exists(cancel_key(run_id)))


async def stream_exists(redis: Redis, run_id: str) -> bool:
    return bool(await redis.exists(events_key(run_id)))
