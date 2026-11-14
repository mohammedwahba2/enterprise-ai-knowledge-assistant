"""The ingestion pipeline: download -> (convert) -> parse -> classify -> chunk -> embed -> persist.

Runs in the worker as the restricted `worker_rw` role. Every step is idempotent: re-running a
document replaces its pages and chunks in one transaction, so a crash can never leave a mix.
"""

import asyncio
import tempfile
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.embeddings.base import (
    Embedder,
    EmbedderUnavailableError,
    EmbeddingFailedError,
    embed_in_batches,
)
from app.infrastructure.storage.s3 import ObjectMissingError, ObjectStore, StorageUnavailableError
from app.modules.documents import validation
from app.modules.documents.models import Document
from app.modules.processing import parsers
from app.modules.processing.arabic import clean_extracted, detect_lang
from app.modules.processing.chunker import Page, chunk_pages
from app.modules.processing.classify import PageState, classify_page, decide
from app.modules.processing.indexing import embedding_text
from app.modules.processing.models import Chunk, DocumentPage, IngestionJob
from app.modules.processing.parsers import OfficeConverter, ProcessingError, RawPage

_log = structlog.get_logger("pipeline")
Publish = Callable[[uuid.UUID, uuid.UUID, str, str | None], Awaitable[None]]
ACTIVE = ("uploaded", "parsing", "chunking", "embedding")
# Short English descriptions stored beside the stable code (the UI translates from the code).
OUTCOME_DETAIL = {
    "EMPTY_DOCUMENT": "The document contains no text.",
    "NO_TEXT_LAYER": "The pages are images without a text layer (scanned); OCR is not enabled.",
    "GARBLED_TEXT": "The text could not be decoded (broken or missing font mapping).",
    "PARTIAL_TEXT": "Some pages have no readable text and are excluded.",
}
EMBEDDER_UNAVAILABLE_DETAIL = "The embedding service was unavailable."
EMBEDDING_FAILED_DETAIL = "The embedding model returned an unusable answer."


@dataclass
class Deps:
    sessions: async_sessionmaker[AsyncSession]
    store: ObjectStore
    converter: OfficeConverter
    publish: Publish
    embedder: Embedder
    embedding_batch_size: int = 16


async def _emit(
    deps: Deps, org_id: uuid.UUID, doc_id: uuid.UUID, status: str, code: str | None
) -> None:
    """Progress events are optional: a failing publisher must never fail the job."""
    try:
        await deps.publish(org_id, doc_id, status, code)
    except Exception:
        _log.warning("publish_failed", document_id=str(doc_id), exc_info=True)


async def _set_stage(
    deps: Deps, doc_id: uuid.UUID, job_id: uuid.UUID, org_id: uuid.UUID, status: str
) -> None:
    async with deps.sessions() as s:
        doc = await s.get(Document, doc_id)
        job = await s.get(IngestionJob, job_id)
        if doc is None or job is None:
            return
        doc.status = status
        job.stage = status
        await s.commit()
    await _emit(deps, org_id, doc_id, status, None)


async def process_document(deps: Deps, document_id: uuid.UUID, org_id: uuid.UUID) -> str:
    """Process one document: 'processed', 'failed' or 'skipped'. Bad input never raises."""
    async with deps.sessions() as s:
        doc = await s.scalar(
            select(Document)
            .where(
                Document.id == document_id,
                Document.organization_id == org_id,
                Document.deleted_at.is_(None),
            )
            .with_for_update(skip_locked=True)
        )
        if doc is None or doc.status not in ACTIVE:
            return "skipped"
        attempt = (
            await s.scalar(
                select(func.count())
                .select_from(IngestionJob)
                .where(IngestionJob.document_id == doc.id)
            )
            or 0
        ) + 1
        job = IngestionJob(
            organization_id=doc.organization_id, document_id=doc.id,
            collection_id=doc.collection_id,
            stage="parsing", attempt=attempt, status="running",
        )  # fmt: skip
        s.add(job)
        doc.status = "parsing"
        doc.error_code = None
        doc.error_detail = None
        await s.commit()
        job_id, mime, key, collection_id = job.id, doc.mime_type, doc.storage_key, doc.collection_id
        title = doc.title
    await _emit(deps, org_id, document_id, "parsing", None)

    try:
        with tempfile.TemporaryDirectory(prefix="ingest-") as tmp:
            raw_pages, pagination, viewer_key = await _extract(
                deps, Path(tmp), document_id, org_id, key, mime
            )
            await _set_stage(deps, document_id, job_id, org_id, "chunking")
            result = await asyncio.to_thread(_analyse, raw_pages)
    except ProcessingError as exc:
        await _finish_failed(deps, document_id, org_id, job_id, exc.code, exc.detail)
        return "failed"
    except ObjectMissingError:
        await _finish_failed(
            deps, document_id, org_id, job_id, "FILE_MISSING", "The stored file is missing."
        )
        return "failed"
    except StorageUnavailableError:
        await _finish_failed(
            deps,
            document_id,
            org_id,
            job_id,
            "STORAGE_UNAVAILABLE",
            "File storage was unavailable.",
        )
        return "failed"
    except Exception:
        _log.error("pipeline_unexpected_error", document_id=str(document_id), exc_info=True)
        await _finish_failed(
            deps, document_id, org_id, job_id, "PROCESSING_ERROR", "Processing failed unexpectedly."
        )
        return "failed"

    pages, chunks, outcome, language = result
    vectors: Sequence[list[float] | None] = []
    if chunks:
        # Embedding runs outside any database transaction (it can take minutes) and before the
        # final write, so a document is never "ready" without vectors and never half-indexed.
        await _set_stage(deps, document_id, job_id, org_id, "embedding")
        try:
            vectors = await embed_in_batches(
                deps.embedder,
                [embedding_text(title, c["heading_path"], c["content"]) for c in chunks],
                deps.embedding_batch_size,
            )
        except EmbedderUnavailableError:
            await _finish_failed(
                deps,
                document_id,
                org_id,
                job_id,
                "EMBEDDER_UNAVAILABLE",
                EMBEDDER_UNAVAILABLE_DETAIL,
            )
            return "failed"
        except EmbeddingFailedError:
            _log.error("embedding_failed", document_id=str(document_id), exc_info=True)
            await _finish_failed(
                deps, document_id, org_id, job_id, "EMBEDDING_FAILED", EMBEDDING_FAILED_DETAIL
            )
            return "failed"
    async with deps.sessions() as s:
        doc = await s.scalar(select(Document).where(Document.id == document_id).with_for_update())
        if (
            doc is None or doc.deleted_at is not None
        ):  # deleted while we were working: discard quietly
            await s.rollback()
            return "skipped"
        await s.execute(delete(DocumentPage).where(DocumentPage.document_id == doc.id))
        await s.execute(delete(Chunk).where(Chunk.document_id == doc.id))
        for page in pages:
            s.add(
                DocumentPage(
                    organization_id=org_id, document_id=doc.id, collection_id=collection_id, **page
                )
            )
        for chunk, vector in zip(chunks, vectors or [None] * len(chunks), strict=True):
            s.add(
                Chunk(
                    organization_id=org_id, document_id=doc.id, collection_id=collection_id,
                    embedding=vector,
                    embedding_model=deps.embedder.model if vector is not None else None,
                    **chunk,
                )
            )  # fmt: skip
        doc.status = outcome.status
        doc.error_code = outcome.error_code
        doc.error_detail = OUTCOME_DETAIL.get(outcome.error_code or "")
        doc.page_count = outcome.summary["total"]
        doc.page_summary = outcome.summary
        doc.language = language
        doc.pagination = pagination
        doc.viewer_key = viewer_key
        doc.processed_at = datetime.now(UTC)
        finished = await s.get(IngestionJob, job_id)
        if finished is not None:
            failed = outcome.status == "failed"  # e.g. a blank document
            finished.status = "failed" if failed else "succeeded"
            finished.error_code = outcome.error_code if failed else None
            finished.finished_at = datetime.now(UTC)
        await s.commit()
        final = (doc.status, doc.error_code)
    await _emit(deps, org_id, document_id, *final)
    _log.info(
        "document.processed", document_id=str(document_id), status=final[0], chunks=len(chunks)
    )
    return "processed"


async def _extract(
    deps: Deps, tmp: Path, document_id: uuid.UUID, org_id: uuid.UUID, key: str, mime: str
) -> tuple[list[RawPage], str, str | None]:
    source = tmp / "source"
    with source.open("wb") as fh:
        async for chunk in await deps.store.open_stream(key):
            fh.write(chunk)
    if mime == validation.PDF:
        return await asyncio.to_thread(parsers.parse_pdf, source), "native", None
    if mime in (validation.DOCX, validation.PPTX):
        suffix = ".docx" if mime == validation.DOCX else ".pptx"
        office = source.with_suffix(suffix)
        source.rename(office)
        pdf_path = await asyncio.to_thread(deps.converter.to_pdf, office)
        viewer_key = f"{key}.viewer.pdf"
        with pdf_path.open("rb") as fh:
            await deps.store.put(viewer_key, fh, validation.PDF)  # rendered pages = what users cite
        return await asyncio.to_thread(parsers.parse_pdf, pdf_path), "native", viewer_key
    return parsers.parse_text(source.read_bytes()), "virtual", None


def _analyse(raw_pages: list[RawPage]):  # type: ignore[no-untyped-def]
    """CPU-bound: clean, classify, decide, chunk -> (page rows, chunk rows, outcome, language)."""
    pages: list[dict[str, object]] = []
    usable: list[Page] = []
    states: list[tuple[int, PageState, int]] = []
    for raw in raw_pages:
        text = clean_extracted(raw.text)
        state = classify_page(text, raw.image_area_ratio)
        pages.append(
            {
                "page_number": raw.number,
                # unusable pages keep no text: garbled output must never reach retrieval
                "text": text if state is PageState.TEXT else "",
                "char_count": len(text) if state is PageState.TEXT else 0,
                "extraction_state": state.value,
                "image_area_ratio": raw.image_area_ratio,
            }
        )
        states.append((raw.number, state, len(text) if state is PageState.TEXT else 0))
        if state is PageState.TEXT and text:
            usable.append(Page(raw.number, text))
    outcome = decide(states)
    chunks = [
        {
            "chunk_index": c.index, "page_start": c.page_start, "page_end": c.page_end,
            "heading_path": c.heading_path, "content": c.content,
            "content_search": c.content_search,
            "token_count": c.token_count, "lang": c.lang,
        }
        for c in (chunk_pages(usable) if outcome.status in ("ready", "ready_partial") else [])
    ]  # fmt: skip
    sample = " ".join(p.text for p in usable[:40])[:50_000]
    language = detect_lang(sample) if usable else None
    return pages, chunks, outcome, language


async def _finish_failed(
    deps: Deps, document_id: uuid.UUID, org_id: uuid.UUID, job_id: uuid.UUID, code: str, detail: str
) -> None:
    async with deps.sessions() as s:
        doc = await s.scalar(select(Document).where(Document.id == document_id).with_for_update())
        if doc is not None and doc.deleted_at is None:
            await s.execute(delete(DocumentPage).where(DocumentPage.document_id == doc.id))
            await s.execute(delete(Chunk).where(Chunk.document_id == doc.id))
            doc.status = "failed"
            doc.error_code = code
            doc.error_detail = detail[:500]
            doc.page_count = None
            doc.page_summary = None
            doc.processed_at = datetime.now(UTC)
        job = await s.get(IngestionJob, job_id)
        if job is not None:
            job.status = "failed"
            job.error_code = code
            job.error_detail = detail[:500]
            job.finished_at = datetime.now(UTC)
        await s.commit()
    await _emit(deps, org_id, document_id, "failed", code)
    _log.warning("document.failed", document_id=str(document_id), code=code)
