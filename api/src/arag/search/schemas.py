"""検索の入出力（specs/004-retrieval R1・R13〜R16）。"""

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Mode = Literal["hybrid", "dense", "keyword"]
BlockType = Literal["text", "table", "figure", "code", "formula", "list"]
QUERY_MAX_CHARS = 1000


class SearchRequest(BaseModel):
    query: str
    kb_ids: list[uuid.UUID] | None = None
    document_ids: list[uuid.UUID] | None = None
    include_archived: bool = False
    block_types: list[BlockType] | None = None
    mode: Mode = "hybrid"
    top_k: int = Field(6, ge=1, le=50)
    candidate_k: int = Field(50, ge=1, le=200)
    include_section: bool = False
    must_contain: list[str] | None = Field(None, max_length=10)
    debug: bool = False

    @field_validator("query")
    @classmethod
    def _query(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("検索語を入力してください")
        if len(v) > QUERY_MAX_CHARS:
            raise ValueError(f"検索語は {QUERY_MAX_CHARS} 文字以内にしてください")
        return v

    @field_validator("must_contain")
    @classmethod
    def _must(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        terms = [t.strip() for t in v if t.strip()]
        return terms or None

    @model_validator(mode="after")
    def _k(self) -> "SearchRequest":
        if self.candidate_k < self.top_k:
            raise ValueError("candidate_k は top_k 以上にしてください")
        return self


class SearchHit(BaseModel):
    rank: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    kb_id: uuid.UUID
    section_id: uuid.UUID
    heading_path: str
    page_start: int | None
    page_end: int | None
    block_type: str
    text: str
    context: str
    boxes: list[dict[str, Any]]
    score: float
    fused_score: float
    # include_section 時、同じセクションの最初の結果だけに入る（R14）
    section_text: str | None = None


class PathHit(BaseModel):
    chunk_id: uuid.UUID
    score: float


class StageTiming(BaseModel):
    name: Literal["scope", "embed", "query", "hydrate", "rerank", "section"]
    ms: int
    count: int | None = None


class SearchTrace(BaseModel):
    stages: list[StageTiming] = Field(default_factory=list)
    dense: list[PathHit] | None = None
    sparse: list[PathHit] | None = None


class SearchResult(BaseModel):
    hits: list[SearchHit]
    trace: SearchTrace
    degraded: list[Literal["dense", "rerank"]] = Field(default_factory=list)
