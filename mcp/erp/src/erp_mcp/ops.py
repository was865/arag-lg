"""運用の振る舞い（specs/033 R12・R13）: 待ち時間の上限・同時数の上限・続けて失敗したら止める・短い使い回し。"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from erp_mcp.model import ErpUnavailable


@dataclass
class Breaker:
    """続けて threshold 回失敗したら cool_s 秒止める。止めている間はすぐ ErpUnavailable。"""

    threshold: int = 3
    cool_s: float = 30
    failures: int = 0
    open_until: float = 0.0
    clock: Callable[[], float] = time.monotonic

    def check(self) -> None:
        if self.open_until and self.clock() < self.open_until:
            left = int(self.open_until - self.clock()) + 1
            raise ErpUnavailable(f"ERP が続けて応答しないため、呼び出しを止めています（あと約 {left} 秒）")
        if self.open_until:
            self.open_until = 0.0  # 半開き: 1 回だけ通して確かめる
            self.failures = self.threshold - 1

    def ok(self) -> None:
        self.failures = 0

    def fail(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.open_until = self.clock() + self.cool_s

    @property
    def state(self) -> str:
        return "open" if self.open_until and self.clock() < self.open_until else "closed"


@dataclass
class TtlCache:
    ttl_s: float = 10
    clock: Callable[[], float] = time.monotonic
    data: dict[str, tuple[float, Any]] = field(default_factory=dict)

    def get(self, key: str) -> Any | None:
        hit = self.data.get(key)
        if hit is None:
            return None
        at, value = hit
        if self.clock() - at > self.ttl_s:
            self.data.pop(key, None)
            return None
        return value

    def put(self, key: str, value: Any) -> None:
        if len(self.data) > 512:
            now = self.clock()
            self.data = {k: v for k, v in self.data.items() if now - v[0] <= self.ttl_s}
        self.data[key] = (self.clock(), value)


class Guard:
    """ERP への 1 回の呼び出しを、止める仕組み・同時数・待ち時間で包む。"""

    def __init__(self, *, timeout_s: float = 8, concurrency: int = 4, breaker: Breaker | None = None) -> None:
        self.timeout_s = timeout_s
        self.sem = asyncio.Semaphore(concurrency)
        self.breaker = breaker or Breaker()

    async def run[T](self, work: Callable[[], Awaitable[T]]) -> T:
        self.breaker.check()
        async with self.sem:
            try:
                out = await asyncio.wait_for(work(), timeout=self.timeout_s)
            except TimeoutError as e:
                self.breaker.fail()
                raise ErpUnavailable(f"ERP が {self.timeout_s:g} 秒以内に応答しません") from e
            except ErpUnavailable:
                self.breaker.fail()
                raise
        self.breaker.ok()
        return out
