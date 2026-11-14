import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.infrastructure.embeddings.base import Embedder
from app.modules.identity.deps import SettingsDep, csrf_guard, limiter_dep, no_store, origin_guard
from app.modules.identity.rate_limit import RateLimiter
from app.modules.retrieval import service
from app.modules.retrieval.schemas import DebugResponse, SearchRequest, SearchResponse
from app.modules.tenancy.deps import Tenant

_guards = [Depends(no_store), Depends(origin_guard), Depends(csrf_guard)]
router = APIRouter(prefix="/orgs", tags=["retrieval"], dependencies=_guards)


def embedder_dep(request: Request) -> Embedder:
    return request.app.state.embedder  # type: ignore[no-any-return]


EmbedderDep = Annotated[Embedder, Depends(embedder_dep)]
Limiter = Annotated[RateLimiter, Depends(limiter_dep)]


@router.post("/{org_id}/search", response_model=SearchResponse)
async def search(
    org_id: uuid.UUID,
    body: SearchRequest,
    ctx: Tenant,
    embedder: EmbedderDep,
    limiter: Limiter,
    settings: SettingsDep,
) -> SearchResponse:
    return await service.search(ctx, embedder, limiter, settings, body)


@router.post("/{org_id}/search/debug", response_model=DebugResponse)
async def search_debug(
    org_id: uuid.UUID,
    body: SearchRequest,
    ctx: Tenant,
    embedder: EmbedderDep,
    limiter: Limiter,
    settings: SettingsDep,
) -> DebugResponse:
    """Per-leg ranks and scores for administrators (retrieval tuning and support)."""
    return await service.search_debug(ctx, embedder, limiter, settings, body)
