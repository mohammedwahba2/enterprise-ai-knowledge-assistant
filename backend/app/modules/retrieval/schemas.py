import uuid

from pydantic import BaseModel, Field, field_validator


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    # optional narrowing; collections the caller cannot access are silently ignored
    collection_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)
    limit: int = Field(default=8, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value.strip()


class SearchHit(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    collection_id: uuid.UUID
    collection_name: str
    page_start: int
    page_end: int
    heading_path: str
    content: str
    lang: str
    similarity: float | None  # cosine similarity to the query (None: not in the vector leg)
    score: float  # fused (RRF) score; for ordering, not a probability


class SearchResponse(BaseModel):
    hits: list[SearchHit]
    # True when the embedding service was unavailable and only full-text results are returned
    degraded: bool = False


class DebugHit(SearchHit):
    vector_rank: int | None
    vector_score: float | None
    fts_rank: int | None
    fts_score: float | None


class DebugResponse(BaseModel):
    hits: list[DebugHit]
    degraded: bool
    embedding_model: str
    accessible_collections: int
    vector_candidates: int
    fts_candidates: int
    lexical_query: str
    timings_ms: dict[str, float]
