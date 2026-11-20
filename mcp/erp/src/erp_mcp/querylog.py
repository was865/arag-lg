"""呼び出しごとの問い合わせの記録（specs/036 R3〜R5）。

1 回のツールの呼び出しで、バックエンドが発行した問い合わせ（SQLite の SQL・Odoo の RPC）を集め、
trace の queries として返す。技術者が画面で写して流し直せるようにする。合言葉・pw は入れない。
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

MAX_QUERIES = 30
MAX_TEXT = 4000


class QueryLog:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []
        self.dropped = 0

    def add(self, lang: str, text: str, ms: float | None = None, rows: int | None = None) -> None:
        if len(self.items) >= MAX_QUERIES:
            self.dropped += 1
            return
        self.items.append({"lang": lang, "text": text[:MAX_TEXT], "ms": ms, "rows": rows})

    def dump(self) -> dict[str, Any]:
        out: dict[str, Any] = {"queries": self.items}
        if self.dropped:
            out["queries_dropped"] = self.dropped
        return out


_LOG: ContextVar[QueryLog | None] = ContextVar("erp_query_log", default=None)


@contextmanager
def collect() -> Iterator[QueryLog]:
    """この中で発行した問い合わせを集める（asyncio のタスクを分けても同じ入れ物に入る）。"""
    log = QueryLog()
    token = _LOG.set(log)
    try:
        yield log
    finally:
        _LOG.reset(token)


def add(lang: str, text: str, ms: float | None = None, rows: int | None = None) -> None:
    log = _LOG.get()
    if log is not None:
        log.add(lang, text, ms, rows)


def sql_trace(statement: str) -> None:
    """sqlite3 の set_trace_callback に渡す（値を埋め込んだ文が来る）。"""
    add("sql", statement.strip())


def since(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)
