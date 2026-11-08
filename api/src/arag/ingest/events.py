"""入庫進捗の通知（Redis Pub/Sub `ingest:job:{id}`。R29）。

DB の ingest_jobs が正。通知は「変わった」ことを早く知らせるための補助。
"""

import json
from typing import Any, Protocol

from redis.asyncio import Redis

TERMINAL = frozenset({"ready", "error", "cancelled"})


def channel(job_id: str) -> str:
    return f"ingest:job:{job_id}"


class Publisher(Protocol):
    async def publish(self, job_id: str, event: dict[str, Any]) -> None: ...


class RedisPublisher:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def publish(self, job_id: str, event: dict[str, Any]) -> None:
        await self.redis.publish(channel(job_id), json.dumps(event, ensure_ascii=False, default=str))


class NoopPublisher:
    async def publish(self, job_id: str, event: dict[str, Any]) -> None:
        return None
