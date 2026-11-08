"""Qdrant Query API の要求を組み立てる純関数（specs/004-retrieval design §3）。"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from qdrant_client import models

from arag.ingest.index import DENSE, SPARSE
from arag.ingest.sparse import SparseVector
from arag.search.config import SearchConfig
from arag.search.schemas import Mode

# 本文は Postgres から取るので payload は最小限
PAYLOAD_FIELDS = ["content_hash", "section_id", "document_ids"]


def build_filter(
    kb_ids: Sequence[str], document_ids: Sequence[str] | None, block_types: Sequence[str] | None
) -> models.Filter:
    must: list[models.Condition] = [
        models.FieldCondition(key="kb_ids", match=models.MatchAny(any=list(kb_ids)))
    ]
    if document_ids is not None:
        must.append(models.FieldCondition(key="document_ids", match=models.MatchAny(any=list(document_ids))))
    if block_types:
        must.append(models.FieldCondition(key="block_type", match=models.MatchAny(any=list(block_types))))
    return models.Filter(must=must)


def _sparse(v: SparseVector) -> models.SparseVector:
    return models.SparseVector(indices=v.indices, values=v.values)


@dataclass(frozen=True, slots=True)
class QdrantQuery:
    """query_points / QueryRequest に渡す引数（limit は呼び出し側）。"""

    query: Any
    using: str | None = None
    prefetch: list[models.Prefetch] | None = None
    filter: models.Filter | None = None

    def request(self, limit: int) -> models.QueryRequest:
        return models.QueryRequest(
            query=self.query,
            using=self.using,
            prefetch=self.prefetch,
            filter=self.filter,
            limit=limit,
            with_payload=PAYLOAD_FIELDS,
        )


def build_query(
    mode: Mode,
    dense: list[float] | None,
    sparse: SparseVector | None,
    flt: models.Filter,
    candidate_k: int,
    cfg: SearchConfig,
) -> QdrantQuery:
    if mode == "dense":
        assert dense is not None
        return QdrantQuery(query=dense, using=DENSE, filter=flt)
    if mode == "keyword":
        assert sparse is not None
        return QdrantQuery(query=_sparse(sparse), using=SPARSE, filter=flt)
    assert dense is not None and sparse is not None
    prefetch = [
        models.Prefetch(query=dense, using=DENSE, limit=candidate_k, filter=flt),
        models.Prefetch(query=_sparse(sparse), using=SPARSE, limit=candidate_k, filter=flt),
    ]
    fusion: Any = (
        models.FusionQuery(fusion=models.Fusion.DBSF)
        if cfg.fusion == "dbsf"
        else models.RrfQuery(rrf=models.Rrf(k=cfg.rrf_k, weights=list(cfg.weights)))
    )
    return QdrantQuery(query=fusion, prefetch=prefetch)
