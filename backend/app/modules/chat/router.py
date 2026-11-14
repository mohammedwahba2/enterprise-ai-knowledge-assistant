import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.infrastructure.embeddings.base import Embedder
from app.infrastructure.llm.base import ChatModel
from app.modules.chat import service
from app.modules.chat.queue import GenerationQueue
from app.modules.chat.schemas import (
    AskRequest,
    ConversationDetail,
    ConversationOut,
    CreateConversationRequest,
)
from app.modules.identity.deps import SettingsDep, csrf_guard, limiter_dep, no_store, origin_guard
from app.modules.identity.rate_limit import RateLimiter
from app.modules.tenancy.deps import Tenant

_guards = [Depends(no_store), Depends(origin_guard), Depends(csrf_guard)]
router = APIRouter(prefix="/orgs", tags=["chat"], dependencies=_guards)


def deps_dep(
    request: Request, limiter: Annotated[RateLimiter, Depends(limiter_dep)], settings: SettingsDep
) -> service.ChatDeps:
    state = request.app.state
    return service.ChatDeps(
        chat=state.chat,
        embedder=state.embedder,
        limiter=limiter,
        settings=settings,
        queue=state.generation_queue,
        sessions=state.sessionmaker,
    )


Deps = Annotated[service.ChatDeps, Depends(deps_dep)]


@router.post("/{org_id}/conversations", status_code=201, response_model=ConversationOut)
async def create_conversation(
    org_id: uuid.UUID, body: CreateConversationRequest, ctx: Tenant
) -> ConversationOut:
    return await service.create_conversation(ctx, body.title)


@router.get("/{org_id}/conversations", response_model=list[ConversationOut])
async def list_conversations(org_id: uuid.UUID, ctx: Tenant) -> list[ConversationOut]:
    return await service.list_conversations(ctx)


@router.get("/{org_id}/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    org_id: uuid.UUID, conversation_id: uuid.UUID, ctx: Tenant
) -> ConversationDetail:
    return await service.get_conversation(ctx, conversation_id)


@router.delete("/{org_id}/conversations/{conversation_id}", status_code=204)
async def delete_conversation(org_id: uuid.UUID, conversation_id: uuid.UUID, ctx: Tenant) -> None:
    await service.delete_conversation(ctx, conversation_id)


def _sse(events: AsyncIterator[dict[str, Any]]) -> AsyncIterator[str]:
    async def frames() -> AsyncIterator[str]:
        async for event in events:
            payload = json.dumps(event["data"], ensure_ascii=False)
            yield f"event: {event['event']}\ndata: {payload}\n\n"

    return frames()


@router.post("/{org_id}/conversations/{conversation_id}/messages")
async def ask(
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    body: AskRequest,
    ctx: Tenant,
    deps: Deps,
) -> StreamingResponse:
    """Ask a question; the answer streams as server-sent events (see `service` for the protocol).

    Everything that can be refused (permissions, rate limit, a full queue) is refused HERE, as an
    ordinary HTTP error, before the stream starts."""
    started = await service.start_message(ctx, deps, conversation_id, body)
    return StreamingResponse(
        _sse(service.generate(deps, started)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )


__all__ = ["ChatModel", "Embedder", "GenerationQueue", "router"]
