"""Embedding text, and re-indexing chunks whose vector is missing or from another model."""

import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy import exists, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.embeddings.base import (
    Embedder,
    EmbedderError,
    embed_in_batches,
)
from app.modules.documents.models import Document
from app.modules.processing.arabic import fold_digits
from app.modules.processing.models import Chunk

_log = structlog.get_logger("indexing")
INDEXED_STATUSES = ("ready", "ready_partial")


def embedding_text(title: str, heading_path: str, content: str) -> str:
    """What the model sees for a chunk: the document title and heading trail give a short passage
    its context ("Annual leave > Carry-over") without changing the stored, quoted content."""
    head = f"{title} > {heading_path}" if heading_path else title
    return fold_digits(f"{head}\n{content}")


def _is_stale(model: str):  # type: ignore[no-untyped-def]
    return or_(Chunk.embedding_model.is_(None), Chunk.embedding_model != model)


@dataclass
class ReindexResult:
    documents: int = 0
    chunks: int = 0
    stopped: str | None = None  # why the run ended early (embedder trouble), else None


async def reindex_stale(
    sessions: async_sessionmaker[AsyncSession],
    embedder: Embedder,
    batch_size: int,
    *,
    org_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    max_documents: int = 100,
) -> ReindexResult:
    """Re-embed chunks that are not embedded by the CURRENT model. Safe to run any time and to
    repeat: a chunk that is already current is never touched, so a second run does nothing and an
    interrupted run resumes where it stopped. Document status is not changed."""
    result = ReindexResult()
    async with sessions() as s:
        stmt = (
            select(Document.id, Document.title)
            .where(
                Document.deleted_at.is_(None),
                Document.status.in_(INDEXED_STATUSES),
                exists().where(Chunk.document_id == Document.id, _is_stale(embedder.model)),
            )
            .order_by(Document.created_at)
            .limit(max_documents)
        )
        if org_id is not None:
            stmt = stmt.where(Document.organization_id == org_id)
        if document_id is not None:
            stmt = stmt.where(Document.id == document_id)
        targets = (await s.execute(stmt)).all()
    for doc_id, title in targets:
        async with sessions() as s:
            rows = (
                await s.execute(
                    select(Chunk.id, Chunk.heading_path, Chunk.content)
                    .where(Chunk.document_id == doc_id, _is_stale(embedder.model))
                    .order_by(Chunk.chunk_index)
                )
            ).all()
        if not rows:
            continue
        try:
            vectors = await embed_in_batches(
                embedder,
                [embedding_text(title, r.heading_path, r.content) for r in rows],
                batch_size,
            )
        except EmbedderError as exc:
            result.stopped = type(exc).__name__
            _log.warning("reindex.stopped", document_id=str(doc_id), reason=result.stopped)
            return result
        async with sessions() as s:
            # Lock the document so a concurrent re-process (which replaces its chunks) is not raced.
            locked = await s.scalar(
                select(Document.id).where(Document.id == doc_id).with_for_update(skip_locked=True)
            )
            if locked is None:
                continue
            for row, vector in zip(rows, vectors, strict=True):
                await s.execute(
                    update(Chunk)
                    .where(Chunk.id == row.id)
                    .values(embedding=vector, embedding_model=embedder.model)
                )
            await s.commit()
        result.documents += 1
        result.chunks += len(rows)
    _log.info("reindex.done", documents=result.documents, chunks=result.chunks)
    return result
