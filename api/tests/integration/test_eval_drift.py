"""variant 用コレクションと DB の子チャンクのずれ検出（再索引で子チャンク ID が変わった後の誤計測を防ぐ）。"""

import uuid

import pytest
from qdrant_client.models import SparseVector

from arag.eval.variants import collection_drift
from arag.ingest.index import IndexPoint, QdrantIndex

pytestmark = pytest.mark.integration


async def test_collection_drift_counts_missing_and_stale(qdrant_index: QdrantIndex) -> None:
    await qdrant_index.ensure_collection(4)
    kb, other = str(uuid.uuid4()), str(uuid.uuid4())
    ids = [uuid.uuid4() for _ in range(3)]

    def pt(i: uuid.UUID, kb_id: str) -> IndexPoint:
        return IndexPoint(
            i, [0.1, 0.2, 0.3, 0.4], SparseVector(indices=[1], values=[1.0]), {"kb_ids": [kb_id]}
        )

    await qdrant_index.upsert([pt(ids[0], kb), pt(ids[1], kb), pt(uuid.uuid4(), other)])
    # DB: ids[0] と ids[2]。Qdrant（この KB）: ids[0] と ids[1] → 欠け 1・古い 1。他の KB の点は数えない
    missing, stale = await collection_drift(qdrant_index.client, qdrant_index.alias, kb, {ids[0], ids[2]})
    assert (missing, stale) == (1, 1)
    assert await collection_drift(qdrant_index.client, qdrant_index.alias, kb, {ids[0], ids[1]}) == (0, 0)
