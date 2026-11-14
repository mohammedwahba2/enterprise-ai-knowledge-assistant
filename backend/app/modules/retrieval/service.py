"""Permission-prefiltered hybrid retrieval (PLAN section 7.2).

Order of operations, and why:
1. Authorize the caller and compute the collections they may access (application layer).
2. Every candidate query is filtered IN SQL by organization, accessible collections, live
   (not soft-deleted) documents. PostgreSQL row-level security applies the same rule again
   independently (the session is scoped to this user and organization).
3. Only then are the two legs fused. Nothing the caller may not see is ever scored, ranked,
   returned, logged or cached.
"""

import re
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import Float, func, literal_column, select, text
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import Settings
from app.core.errors import AppError
from app.infrastructure.embeddings.base import Embedder, EmbedderError
from app.modules.access import policies
from app.modules.access.policies import Action
from app.modules.documents.models import Collection, Document
from app.modules.documents.service import accessible_collection_ids
from app.modules.identity.rate_limit import RateLimiter
from app.modules.processing.arabic import fold_digits, search_normalize
from app.modules.processing.models import Chunk
from app.modules.retrieval.fusion import rrf
from app.modules.retrieval.schemas import (
    DebugHit,
    DebugResponse,
    SearchHit,
    SearchRequest,
    SearchResponse,
)
from app.modules.tenancy.deps import TenantCtx

_log = structlog.get_logger("retrieval")
_WORD = re.compile(r"\w+", re.UNICODE)
MAX_QUERY_WORDS = 40


def lexical_words(query: str) -> list[str]:
    """Search-normalized, tsquery-safe words: the same normalization the index was built with."""
    return _WORD.findall(search_normalize(query))[:MAX_QUERY_WORDS]


async def _rate_limit(limiter: RateLimiter, ctx: TenantCtx, settings: Settings) -> None:
    decision = await limiter.hit_and_check(
        f"search:{ctx.user.id}", settings.search_rate_per_minute, 60
    )
    if not decision.allowed:
        raise AppError(
            429, "RATE_LIMITED", "Too many searches. Try again shortly.",
            headers={"Retry-After": str(decision.retry_after)}, retry_after=decision.retry_after,
        )  # fmt: skip


def _scope(ctx: TenantCtx, requested: Sequence[uuid.UUID] | None) -> list[ColumnElement[bool]]:
    clauses: list[ColumnElement[bool]] = [
        Chunk.organization_id == ctx.org_id,
        Chunk.collection_id.in_(accessible_collection_ids(ctx)),
        Document.deleted_at.is_(None),
    ]
    if requested:
        clauses.append(Chunk.collection_id.in_(list(requested)))
    return clauses


async def _vector_leg(
    ctx: TenantCtx,
    embedder: Embedder,
    query: str,
    scope: list[ColumnElement[bool]],
    candidates: int,
    settings: Settings,
) -> list[tuple[uuid.UUID, float]]:
    """(chunk id, cosine similarity) best first. Raises EmbedderError if the model is down."""
    (vector,) = await embedder.embed([fold_digits(query)])  # identical digits at index and query
    distance = Chunk.embedding.op("<=>", return_type=Float)(vector)
    # Iterative scans keep a filtered HNSW search from returning fewer than `candidates` rows when
    # most of the nearest vectors belong to collections this caller cannot access.
    await ctx.db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    await ctx.db.execute(text(f"SET LOCAL hnsw.ef_search = {int(settings.hnsw_ef_search)}"))
    await ctx.db.execute(text(f"SET LOCAL hnsw.max_scan_tuples = {int(settings.hnsw_max_scan)}"))
    rows = (
        await ctx.db.execute(
            select(Chunk.id, distance.label("distance"))
            .join(Document, Document.id == Chunk.document_id)
            .where(*scope, Chunk.embedding_model == embedder.model)  # never mix models
            .order_by(distance)
            .limit(candidates)
        )
    ).all()
    # relaxed_order may return nearly-sorted rows: sort explicitly, deterministically
    ranked = sorted(((r.id, 1.0 - float(r.distance)) for r in rows), key=lambda t: (-t[1], t[0]))
    return ranked[:candidates]


async def _lexical_leg(
    ctx: TenantCtx, words: list[str], scope: list[ColumnElement[bool]], candidates: int
) -> list[tuple[uuid.UUID, float]]:
    if not words:
        return []
    joined = " | ".join(words)
    tsv: ColumnElement[Any] = literal_column("chunks.content_tsv")
    # `content_tsv` was built per chunk language (arabic / english / both): run the query through
    # both configs so a chunk matches under whichever it was indexed with.
    tsq = func.to_tsquery(literal_column("'arabic'::regconfig"), joined).op("||")(
        func.to_tsquery(literal_column("'english'::regconfig"), joined)
    )
    rank = func.ts_rank_cd(tsv, tsq)
    rows = (
        await ctx.db.execute(
            select(Chunk.id, rank.label("rank"))
            .join(Document, Document.id == Chunk.document_id)
            .where(*scope, tsv.op("@@")(tsq))
            .order_by(rank.desc(), Chunk.document_id, Chunk.chunk_index)
            .limit(candidates)
        )
    ).all()
    return [(r.id, float(r.rank)) for r in rows]


@dataclass
class _Outcome:
    """Everything one retrieval produced; the two public entry points shape it differently."""

    fused: list[tuple[uuid.UUID, float]]
    details: dict[uuid.UUID, tuple[Chunk, str, str]]
    vector_hits: list[tuple[uuid.UUID, float]]
    fts_hits: list[tuple[uuid.UUID, float]]
    words: list[str]
    degraded: bool
    t_vector: float
    t_fts: float
    started: float


async def _run(
    ctx: TenantCtx,
    embedder: Embedder,
    limiter: RateLimiter,
    settings: Settings,
    request: SearchRequest,
    action: Action,
) -> _Outcome:
    policies.require(ctx.role, action)
    await _rate_limit(limiter, ctx, settings)
    return await _core(ctx, embedder, settings, request)


async def _core(
    ctx: TenantCtx, embedder: Embedder, settings: Settings, request: SearchRequest
) -> _Outcome:
    started = time.perf_counter()
    scope = _scope(ctx, request.collection_ids)
    n = settings.retrieval_candidates

    words = lexical_words(request.query)
    degraded = False
    t0 = time.perf_counter()
    try:
        vector_hits = await _vector_leg(ctx, embedder, request.query, scope, n, settings)
    except EmbedderError:
        # The embedding service is down: answer from the lexical leg alone and say so.
        vector_hits, degraded = [], True
        _log.warning("search_degraded", reason="embedder_unavailable")
    t_vector = time.perf_counter() - t0
    t0 = time.perf_counter()
    fts_hits = await _lexical_leg(ctx, words, scope, n)
    t_fts = time.perf_counter() - t0

    vector_ids = [c for c, _ in vector_hits]
    rankings = {f"vector#{i}": vector_ids for i in range(settings.rrf_vector_weight)}
    rankings["fts"] = [c for c, _ in fts_hits]
    fused = rrf(rankings, k=settings.rrf_k)[: request.limit]
    ids = [cid for cid, _ in fused]
    details: dict[uuid.UUID, tuple[Chunk, str, str]] = {}
    if ids:
        # Detail rows re-apply the same scope: defense in depth against any id leaking through.
        rows = (
            await ctx.db.execute(
                select(Chunk, Document.title, Collection.name)
                .join(Document, Document.id == Chunk.document_id)
                .join(Collection, Collection.id == Chunk.collection_id)
                .where(*scope, Chunk.id.in_(ids))
            )
        ).all()
        details = {row[0].id: (row[0], row[1], row[2]) for row in rows}
    # counts only: the query text is user content and is never logged
    _log.info(
        "search", results=len(details), vector=len(vector_hits), fts=len(fts_hits),
        degraded=degraded, query_chars=len(request.query),
    )  # fmt: skip
    return _Outcome(
        fused, details, vector_hits, fts_hits, words, degraded, t_vector, t_fts, started
    )


def _common(chunk: Chunk, title: str, collection: str, similarity: float | None, score: float):  # type: ignore[no-untyped-def]
    return {
        "chunk_id": chunk.id, "document_id": chunk.document_id, "document_title": title,
        "collection_id": chunk.collection_id, "collection_name": collection,
        "page_start": chunk.page_start, "page_end": chunk.page_end,
        "heading_path": chunk.heading_path, "content": chunk.content, "lang": chunk.lang,
        "similarity": similarity, "score": score,
    }  # fmt: skip


async def search(
    ctx: TenantCtx,
    embedder: Embedder,
    limiter: RateLimiter,
    settings: Settings,
    request: SearchRequest,
) -> SearchResponse:
    out = await _run(ctx, embedder, limiter, settings, request, Action.DOCUMENT_VIEW)
    similarity = dict(out.vector_hits)
    hits = [
        SearchHit.model_validate(_common(*out.details[cid], similarity.get(cid), score))
        for cid, score in out.fused
        if cid in out.details
    ]
    return SearchResponse(hits=hits, degraded=out.degraded)


async def search_debug(
    ctx: TenantCtx,
    embedder: Embedder,
    limiter: RateLimiter,
    settings: Settings,
    request: SearchRequest,
) -> DebugResponse:
    out = await _run(ctx, embedder, limiter, settings, request, Action.RETRIEVAL_DEBUG)
    similarity = dict(out.vector_hits)
    vector_rank = {cid: i for i, (cid, _) in enumerate(out.vector_hits, start=1)}
    fts_rank = {cid: i for i, (cid, _) in enumerate(out.fts_hits, start=1)}
    fts_score = dict(out.fts_hits)
    hits = [
        DebugHit.model_validate(
            {
                **_common(*out.details[cid], similarity.get(cid), score),
                "vector_rank": vector_rank.get(cid),
                "vector_score": similarity.get(cid),
                "fts_rank": fts_rank.get(cid),
                "fts_score": fts_score.get(cid),
            }
        )
        for cid, score in out.fused
        if cid in out.details
    ]
    accessible_count = int(
        await ctx.db.scalar(
            select(func.count()).select_from(accessible_collection_ids(ctx).subquery())
        )
        or 0
    )
    return DebugResponse(
        hits=hits,
        degraded=out.degraded,
        embedding_model=embedder.model,
        accessible_collections=accessible_count,
        vector_candidates=len(out.vector_hits),
        fts_candidates=len(out.fts_hits),
        lexical_query=" | ".join(out.words),
        timings_ms={
            "vector": round(out.t_vector * 1000, 1),
            "fts": round(out.t_fts * 1000, 1),
            "total": round((time.perf_counter() - out.started) * 1000, 1),
        },
    )


@dataclass(frozen=True)
class RankedChunk:
    """One retrieved passage with everything the answer pipeline needs (and nothing hidden)."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    collection_id: uuid.UUID
    document_title: str
    collection_name: str
    page_start: int
    page_end: int
    heading_path: str
    content: str
    similarity: float | None
    fts_score: float | None
    vector_rank: int | None
    fts_rank: int | None
    fused: float


@dataclass(frozen=True)
class Evidence:
    chunks: list[RankedChunk]
    degraded: bool


async def retrieve_evidence(
    ctx: TenantCtx,
    embedder: Embedder,
    settings: Settings,
    request: SearchRequest,
) -> Evidence:
    """Permission-prefiltered evidence for answering (same filters as search; no search rate limit,
    the caller applies its own)."""
    policies.require(ctx.role, Action.DOCUMENT_VIEW)
    out = await _core(ctx, embedder, settings, request)
    vector_rank = {cid: i for i, (cid, _) in enumerate(out.vector_hits, start=1)}
    fts_rank = {cid: i for i, (cid, _) in enumerate(out.fts_hits, start=1)}
    similarity = dict(out.vector_hits)
    fts_score = dict(out.fts_hits)
    chunks = [
        RankedChunk(
            chunk_id=cid,
            document_id=out.details[cid][0].document_id,
            collection_id=out.details[cid][0].collection_id,
            document_title=out.details[cid][1],
            collection_name=out.details[cid][2],
            page_start=out.details[cid][0].page_start,
            page_end=out.details[cid][0].page_end,
            heading_path=out.details[cid][0].heading_path,
            content=out.details[cid][0].content,
            similarity=similarity.get(cid),
            fts_score=fts_score.get(cid),
            vector_rank=vector_rank.get(cid),
            fts_rank=fts_rank.get(cid),
            fused=score,
        )
        for cid, score in out.fused
        if cid in out.details
    ]
    return Evidence(chunks=chunks, degraded=out.degraded)
