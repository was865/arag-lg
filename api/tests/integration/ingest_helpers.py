"""入庫の結合テスト用の偽依存。"""

import hashlib
from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from arag.ingest.index import QdrantIndex
from arag.ingest.pipeline import IngestDeps
from arag.storage import LocalStorage

from ..docling_fixtures import CharTokenizer


class FakeEmbedder:
    model = "fake-embed"

    def __init__(self, fail_times: int = 0) -> None:
        self.fail_times = fail_times
        self.calls = 0

    async def dimension(self) -> int:
        return 4

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        if self.calls <= self.fail_times:
            from arag.ingest.embedder import EmbedError

            raise EmbedError("偽の失敗")
        out = []
        for t in texts:
            d = hashlib.sha256(t.encode()).digest()
            out.append([d[0] / 255 + 0.01, d[1] / 255, d[2] / 255, d[3] / 255])
        return out


class RecordingPublisher:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish(self, job_id: str, event: dict[str, Any]) -> None:
        self.events.append(event)


def make_deps(
    sessionmaker: async_sessionmaker[AsyncSession],
    storage_root: str,
    index: QdrantIndex,
    **kw: Any,
) -> IngestDeps:
    return IngestDeps(
        sessionmaker=sessionmaker,
        storage=LocalStorage(storage_root),
        tokenizer=CharTokenizer(max_tokens=120),
        embedder=kw.pop("embedder", FakeEmbedder()),
        index=index,
        publisher=kw.pop("publisher", RecordingPublisher()),
        **kw,
    )
