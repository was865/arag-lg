"""文書の追加・移動・削除・復元のたびに Qdrant の payload（document_ids / kb_ids）を合わせる（R23）。

実体は ingest/index.py。KB・フォルダ API はこのプロトコルだけに依存する。
"""

from collections.abc import Iterable
from typing import Protocol


class PayloadSync(Protocol):
    async def sync(self, content_hashes: Iterable[str]) -> None: ...


class NoopPayloadSync:
    async def sync(self, content_hashes: Iterable[str]) -> None:
        return None
