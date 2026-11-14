"""Grounded answering: retrieve -> gate -> prompt -> stream -> verify -> persist.

The answer is produced inside a generator that opens its OWN short database sessions (each scoped
to the user and organization, so row-level security applies throughout): the request's session
must not be held open for the length of a generation.

Event protocol (SSE `event:` names):
  meta       {conversation_id, message_id, user_message_id}
  queued     {position}                          waiting for the model (bounded queue)
  retrieval  {sources: [...]}                    the sources the model is shown, numbered
  delta      {text, provisional: true}           text as generated, NOT yet verified
  final      {text, citations, partially_supported, ...}   the verified answer: AUTHORITATIVE,
                                                 replaces everything streamed as `delta`
  refused    {reason, text, related: [...]}      no grounded answer (gate, NO_ANSWER, unverifiable)
  error      {code}                              generation failed
  done       {message_id, status}                always last
"""

import asyncio
import math
import time
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import AppError
from app.db.tenant import TenantScope, bind_scope
from app.infrastructure.embeddings.base import Embedder, EmbedderError
from app.infrastructure.llm.base import ChatModel, LlmError, LlmUnavailableError
from app.modules.access import policies
from app.modules.access.policies import Action, Role
from app.modules.chat import gate, prompt, verify
from app.modules.chat.models import Conversation, Message, MessageCitation, RetrievalLog
from app.modules.chat.queue import GenerationQueue
from app.modules.chat.schemas import (
    AskRequest,
    CitationOut,
    ConversationDetail,
    ConversationOut,
    MessageOut,
)
from app.modules.documents import validation
from app.modules.documents.models import Document
from app.modules.documents.service import accessible_collection_ids
from app.modules.identity.models import User
from app.modules.identity.rate_limit import RateLimiter
from app.modules.processing.arabic import fold_digits
from app.modules.retrieval.schemas import SearchRequest
from app.modules.retrieval.service import Evidence, RankedChunk, retrieve_evidence
from app.modules.tenancy.deps import TenantCtx

_log = structlog.get_logger("chat")
QUOTE_CHARS = 1200
RELATED_LIMIT = 3
REFUSAL_TEXT = {
    "en": "I couldn't find this in your documents.",
    "ar": "لم أجد هذا في مستنداتك.",
}


@dataclass
class ChatDeps:
    chat: ChatModel
    embedder: Embedder
    limiter: RateLimiter
    settings: Settings
    queue: GenerationQueue
    sessions: async_sessionmaker[AsyncSession]


@dataclass(frozen=True)
class Started:
    """Everything the generator needs, captured while the request context was still alive."""

    conversation_id: uuid.UUID
    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID
    user_id: uuid.UUID
    org_id: uuid.UUID
    role: Role
    question: str
    language: str
    collection_ids: tuple[uuid.UUID, ...] | None


# ------------------------------------------------------------------ conversations


async def _owned_conversation(ctx: TenantCtx, conversation_id: uuid.UUID) -> Conversation:
    """The caller's own conversation. Someone else's and a nonexistent one look identical (404)."""
    row = await ctx.db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.organization_id == ctx.org_id,
            Conversation.user_id == ctx.user.id,
        )
    )
    if row is None:
        raise validation.not_found()
    return row


async def create_conversation(ctx: TenantCtx, title: str) -> ConversationOut:
    policies.require(ctx.role, Action.DOCUMENT_VIEW)
    row = Conversation(organization_id=ctx.org_id, user_id=ctx.user.id, title=title.strip())
    ctx.db.add(row)
    await ctx.db.commit()
    return ConversationOut.model_validate(row, from_attributes=True)


async def list_conversations(ctx: TenantCtx) -> list[ConversationOut]:
    policies.require(ctx.role, Action.DOCUMENT_VIEW)
    rows = await ctx.db.scalars(
        select(Conversation)
        .where(Conversation.organization_id == ctx.org_id, Conversation.user_id == ctx.user.id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(100)
    )
    return [ConversationOut.model_validate(r, from_attributes=True) for r in rows]


async def delete_conversation(ctx: TenantCtx, conversation_id: uuid.UUID) -> None:
    policies.require(ctx.role, Action.DOCUMENT_VIEW)
    await _owned_conversation(ctx, conversation_id)
    await ctx.db.execute(delete(Conversation).where(Conversation.id == conversation_id))
    await ctx.db.commit()


async def get_conversation(ctx: TenantCtx, conversation_id: uuid.UUID) -> ConversationDetail:
    """The conversation with its messages. Citations are re-checked against the reader's CURRENT
    access on every read: a citation to a document they can no longer see is redacted."""
    policies.require(ctx.role, Action.DOCUMENT_VIEW)
    conversation = await _owned_conversation(ctx, conversation_id)
    messages = list(
        await ctx.db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at, Message.role.desc())
        )
    )
    citations = (
        list(
            await ctx.db.scalars(
                select(MessageCitation)
                .where(MessageCitation.message_id.in_([m.id for m in messages]))
                .order_by(MessageCitation.message_id, MessageCitation.marker)
            )
        )
        if messages
        else []
    )
    document_ids = {c.document_id for c in citations if c.document_id is not None}
    readable: set[uuid.UUID] = set()
    if document_ids:
        readable = set(
            await ctx.db.scalars(
                select(Document.id).where(
                    Document.id.in_(document_ids),
                    Document.organization_id == ctx.org_id,
                    Document.deleted_at.is_(None),
                    Document.collection_id.in_(accessible_collection_ids(ctx)),
                )
            )
        )
    by_message: dict[uuid.UUID, list[CitationOut]] = {}
    for c in citations:
        ok = c.document_id in readable
        by_message.setdefault(c.message_id, []).append(
            CitationOut(
                marker=c.marker,
                available=ok,
                document_id=c.document_id if ok else None,
                document_title=c.document_title if ok else None,
                page_start=c.page_start if ok else None,
                page_end=c.page_end if ok else None,
                quote=c.quote if ok else None,
                support_score=c.support_score,
            )
        )
    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                status=m.status,
                refusal_reason=m.refusal_reason,
                error_code=m.error_code,
                language=m.language,
                partially_supported=m.partially_supported,
                created_at=m.created_at,
                citations=by_message.get(m.id, []),
            )
            for m in messages
        ],
    )


# ------------------------------------------------------------------ asking


async def start_message(
    ctx: TenantCtx, deps: ChatDeps, conversation_id: uuid.UUID, body: AskRequest
) -> Started:
    """Validate, rate-limit and record the question; the answer itself is `generate`."""
    policies.require(ctx.role, Action.DOCUMENT_VIEW)
    conversation = await _owned_conversation(ctx, conversation_id)
    decision = await deps.limiter.hit_and_check(
        f"chat:{ctx.user.id}", deps.settings.chat_rate_per_minute, 60
    )
    if not decision.allowed:
        raise AppError(
            429,
            "RATE_LIMITED",
            "Too many questions. Try again shortly.",
            headers={"Retry-After": str(decision.retry_after)},
            retry_after=decision.retry_after,
        )
    if deps.queue.is_full():
        raise AppError(
            503,
            "BUSY",
            "The assistant is busy. Try again in a moment.",
            headers={"Retry-After": "10"},
        )
    language = body.language or prompt.answer_language(body.content, ctx.user.locale)
    user_message = Message(
        conversation_id=conversation.id,
        organization_id=ctx.org_id,
        user_id=ctx.user.id,
        role="user",
        content=body.content,
        status="complete",
        language=language,
    )
    assistant = Message(
        conversation_id=conversation.id,
        organization_id=ctx.org_id,
        user_id=ctx.user.id,
        role="assistant",
        content="",
        status="streaming",
        language=language,
    )
    ctx.db.add_all([user_message, assistant])
    if not conversation.title:
        conversation.title = body.content[:60]
    conversation.updated_at = func.now()
    await ctx.db.commit()
    return Started(
        conversation_id=conversation.id,
        user_message_id=user_message.id,
        assistant_message_id=assistant.id,
        user_id=ctx.user.id,
        org_id=ctx.org_id,
        role=ctx.role,
        question=body.content,
        language=language,
        collection_ids=tuple(body.collection_ids) if body.collection_ids else None,
    )


@asynccontextmanager
async def _scoped(deps: ChatDeps, started: Started) -> AsyncIterator[AsyncSession]:
    async with deps.sessions() as session:
        bind_scope(session, TenantScope(user_id=started.user_id, org_id=started.org_id))
        yield session


def _event(name: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"event": name, "data": data}


def _related(chunks: Sequence[RankedChunk]) -> list[dict[str, Any]]:
    seen: set[uuid.UUID] = set()
    out: list[dict[str, Any]] = []
    for c in chunks:
        if c.document_id in seen:
            continue
        seen.add(c.document_id)
        out.append(
            {
                "document_id": str(c.document_id),
                "document_title": c.document_title,
                "page_start": c.page_start,
                "page_end": c.page_end,
                "similarity": c.similarity,
            }
        )
        if len(out) == RELATED_LIMIT:
            break
    return out


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def _similarity_fn(embedder: Embedder):  # type: ignore[no-untyped-def]
    async def similarity(left: Sequence[str], right: Sequence[str]) -> list[float]:
        try:
            vectors = await embedder.embed([fold_digits(t) for t in [*left, *right]])
        except EmbedderError:
            return [0.0] * len(left)  # no semantic rescue when the embedder is down
        n = len(left)
        return [_cosine(vectors[i], vectors[n + i]) for i in range(n)]

    return similarity


async def _finish(
    deps: ChatDeps,
    started: Started,
    *,
    status: str,
    content: str,
    refusal_reason: str | None = None,
    error_code: str | None = None,
    partially_supported: bool = False,
    params: dict[str, Any] | None = None,
    metrics: dict[str, int | None] | None = None,
    evidence: Sequence[RankedChunk] = (),
    cited: dict[int, tuple[RankedChunk, float]] | None = None,
) -> None:
    """Persist the outcome of one answer in a single transaction."""
    metrics = metrics or {}
    cited = cited or {}
    async with _scoped(deps, started) as db:
        await db.execute(
            update(Message)
            .where(Message.id == started.assistant_message_id)
            .values(
                status=status,
                content=content,
                refusal_reason=refusal_reason,
                error_code=error_code,
                partially_supported=partially_supported,
                model=deps.chat.model,
                retrieval_params=params,
                **metrics,
            )
        )
        cited_chunks = {chunk.chunk_id for chunk, _ in cited.values()}
        for marker, (chunk, score) in sorted(cited.items()):
            db.add(
                MessageCitation(
                    message_id=started.assistant_message_id,
                    organization_id=started.org_id,
                    user_id=started.user_id,
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    collection_id=chunk.collection_id,
                    document_title=chunk.document_title,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    quote=chunk.content[:QUOTE_CHARS],
                    marker=marker,
                    support_score=score,
                )
            )
        for rank, chunk in enumerate(evidence, start=1):
            db.add(
                RetrievalLog(
                    message_id=started.assistant_message_id,
                    organization_id=started.org_id,
                    user_id=started.user_id,
                    chunk_id=chunk.chunk_id,
                    rank=rank,
                    vector_score=chunk.similarity,
                    fts_score=chunk.fts_score,
                    fused_score=chunk.fused,
                    used=chunk.chunk_id in cited_chunks,
                )
            )
        await db.commit()


async def generate(deps: ChatDeps, started: Started) -> AsyncGenerator[dict[str, Any], None]:
    """Run one answer and yield protocol events. Never raises: failures become `error` events."""
    settings = deps.settings
    t0 = time.perf_counter()
    yield _event(
        "meta",
        {
            "conversation_id": str(started.conversation_id),
            "message_id": str(started.assistant_message_id),
            "user_message_id": str(started.user_message_id),
        },
    )
    finished = False
    partial = ""
    try:
        # 1. retrieve (permission-prefiltered; the same filters as search)
        async with _scoped(deps, started) as db:
            user = await db.get(User, started.user_id)
            if user is None:
                raise LlmError("The user no longer exists.")  # cannot happen inside a session
            ctx = TenantCtx(db=db, user=user, org_id=started.org_id, role=started.role)
            request = SearchRequest(
                query=started.question,
                collection_ids=list(started.collection_ids or []) or None,
                limit=settings.answer_context_chunks + 4,
            )
            evidence: Evidence = await retrieve_evidence(ctx, deps.embedder, settings, request)
        window = evidence.chunks[: settings.answer_context_chunks]

        # 2. gate: weak evidence is refused WITHOUT calling the model
        decision = gate.decide(
            [gate.Evidence(str(c.chunk_id), c.similarity, c.fts_score) for c in window], settings
        )
        params: dict[str, Any] = {
            "gate": {"passed": decision.passed, "mode": decision.mode, "best": decision.best},
            "degraded": evidence.degraded,
            "retrieved": len(evidence.chunks),
        }
        if not decision.passed:
            text = REFUSAL_TEXT[started.language]
            latency = int((time.perf_counter() - t0) * 1000)
            await _finish(
                deps,
                started,
                status="refused",
                content=text,
                refusal_reason="NOT_FOUND",
                params=params,
                metrics={"latency_ms": latency},
                evidence=evidence.chunks,
            )
            finished = True
            yield _event(
                "refused", {"reason": "NOT_FOUND", "text": text, "related": _related(window)}
            )
            yield _event(
                "done", {"message_id": str(started.assistant_message_id), "status": "refused"}
            )
            return

        # 3. prompt (budgeted against the explicit context window)
        built = prompt.build_prompt(
            started.question,
            [prompt.Source(c.document_title, c.page_start, c.page_end, c.content) for c in window],
            language=started.language,
            num_ctx=deps.chat.num_ctx,
            max_output_tokens=settings.llm_max_output_tokens,
            max_sources=settings.answer_context_chunks,
        )
        used = window[: built.used]
        params["prompt"] = {
            "sources": built.used,
            "dropped": built.dropped,
            "estimated": built.estimated_tokens,
        }
        yield _event(
            "retrieval",
            {
                "sources": [
                    {
                        "marker": i,
                        "document_id": str(c.document_id),
                        "document_title": c.document_title,
                        "collection_name": c.collection_name,
                        "page_start": c.page_start,
                        "page_end": c.page_end,
                        "similarity": c.similarity,
                    }
                    for i, c in enumerate(used, start=1)
                ]
            },
        )

        # 4. generate (one run at a time; others wait visibly, within a bounded queue)
        if deps.queue.would_wait():
            yield _event("queued", {"position": deps.queue.waiting + 1})
        await deps.queue.acquire()
        buffer = ""
        emitting = False
        no_answer = False
        first_token_ms: int | None = None
        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        stream = deps.chat.stream(built.messages, max_tokens=settings.llm_max_output_tokens)
        try:
            async for chunk in stream:
                if chunk.done:
                    prompt_tokens, completion_tokens = chunk.prompt_tokens, chunk.completion_tokens
                if not chunk.text:
                    continue
                buffer += chunk.text
                partial = buffer
                if first_token_ms is None:
                    first_token_ms = int((time.perf_counter() - t0) * 1000)
                if not emitting:
                    probe = buffer.lstrip()
                    if len(probe) < len(prompt.NO_ANSWER) and prompt.NO_ANSWER.startswith(probe):
                        continue  # might still turn into NO_ANSWER: do not show it yet
                    if probe.startswith(prompt.NO_ANSWER):
                        no_answer = True
                        break
                    emitting = True
                    yield _event("delta", {"text": buffer, "provisional": True})
                else:
                    yield _event("delta", {"text": chunk.text, "provisional": True})
        finally:
            deps.queue.release()
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                await aclose()  # stop the model run at once (NO_ANSWER seen, or the client left)
        latency = int((time.perf_counter() - t0) * 1000)
        metrics: dict[str, int | None] = {
            "latency_ms": latency,
            "first_token_ms": first_token_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }

        # 5. the server's own prompt size is the truth: a full window means silent truncation
        if prompt_tokens is not None and prompt_tokens >= deps.chat.num_ctx - 8:
            _log.error("prompt_truncated", prompt_tokens=prompt_tokens, num_ctx=deps.chat.num_ctx)
            await _finish(
                deps,
                started,
                status="error",
                content="",
                error_code="PROMPT_TRUNCATED",
                params=params,
                metrics=metrics,
                evidence=evidence.chunks,
            )
            finished = True
            yield _event("error", {"code": "PROMPT_TRUNCATED"})
            yield _event(
                "done", {"message_id": str(started.assistant_message_id), "status": "error"}
            )
            return

        # 6. NO_ANSWER, or verify the citations of what was generated
        refusal: str | None = "NO_ANSWER" if (no_answer or not buffer.strip()) else None
        result: verify.Verification | None = None
        if refusal is None:
            result = await verify.verify(
                buffer,
                [verify.SourceText(i, c.content) for i, c in enumerate(used, start=1)],
                min_lexical=settings.verify_min_lexical,
                min_similarity=settings.verify_min_similarity,
                similarity=_similarity_fn(deps.embedder),
            )
            if not result.has_support:
                refusal = "UNSUPPORTED"  # an answer with no verifiable citation is not an answer
        if refusal is not None:
            text = REFUSAL_TEXT[started.language]
            params["raw_answer_chars"] = len(buffer)
            await _finish(
                deps,
                started,
                status="refused",
                content=text,
                refusal_reason=refusal,
                params=params,
                metrics=metrics,
                evidence=evidence.chunks,
            )
            finished = True
            yield _event("refused", {"reason": refusal, "text": text, "related": _related(window)})
            yield _event(
                "done", {"message_id": str(started.assistant_message_id), "status": "refused"}
            )
            return

        if result is None:  # unreachable: a refusal was decided above
            raise LlmError("No verification result.")
        cited = {c.marker: (used[c.marker - 1], c.support) for c in result.citations}
        params["verification"] = {
            "invalid_markers": result.invalid_markers,
            "unsupported_sentences": len(result.unsupported_sentences),
            "uncited_unsupported": len(result.uncited_unsupported),
        }
        await _finish(
            deps,
            started,
            status="complete",
            content=result.text,
            partially_supported=result.partially_supported,
            params=params,
            metrics=metrics,
            evidence=evidence.chunks,
            cited=cited,
        )
        finished = True
        yield _event(
            "final",
            {
                "text": result.text,
                "partially_supported": result.partially_supported,
                "language": started.language,
                "model": deps.chat.model,
                "latency_ms": latency,
                "first_token_ms": first_token_ms,
                "citations": [
                    {
                        "marker": marker,
                        "document_id": str(chunk.document_id),
                        "document_title": chunk.document_title,
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                        "quote": chunk.content[:QUOTE_CHARS],
                        "support_score": score,
                        "available": True,
                    }
                    for marker, (chunk, score) in sorted(cited.items())
                ],
            },
        )
        yield _event(
            "done", {"message_id": str(started.assistant_message_id), "status": "complete"}
        )
    except asyncio.CancelledError:
        # the client went away: do not leave the message "streaming" forever
        await _fail(deps, started, "CLIENT_DISCONNECTED", partial)
        raise
    except LlmUnavailableError:
        await _fail(deps, started, "LLM_UNAVAILABLE", partial)
        yield _event("error", {"code": "LLM_UNAVAILABLE"})
        yield _event("done", {"message_id": str(started.assistant_message_id), "status": "error"})
    except (LlmError, prompt.PromptTooLargeError):
        _log.error("generation_failed", exc_info=True)
        await _fail(deps, started, "GENERATION_FAILED", partial)
        yield _event("error", {"code": "GENERATION_FAILED"})
        yield _event("done", {"message_id": str(started.assistant_message_id), "status": "error"})
    except Exception:
        _log.error("answer_pipeline_failed", exc_info=True)
        await _fail(deps, started, "INTERNAL_ERROR", partial)
        yield _event("error", {"code": "INTERNAL_ERROR"})
        yield _event("done", {"message_id": str(started.assistant_message_id), "status": "error"})
    finally:
        if not finished:
            await _fail(deps, started, "INTERRUPTED", partial)


async def _fail(deps: ChatDeps, started: Started, code: str, partial: str) -> None:
    """Mark the assistant message failed (idempotent: only a message still streaming changes)."""
    try:
        async with _scoped(deps, started) as db:
            await db.execute(
                update(Message)
                .where(Message.id == started.assistant_message_id, Message.status == "streaming")
                .values(
                    status="error", error_code=code, content=partial[:4000], model=deps.chat.model
                )
            )
            await db.commit()
    except Exception:
        _log.error("fail_marking_failed", exc_info=True)
