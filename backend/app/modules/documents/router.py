import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Path, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from starlette.status import HTTP_202_ACCEPTED

from app.core.errors import AppError
from app.infrastructure.storage.s3 import ObjectMissingError, ObjectStore, StorageUnavailableError
from app.modules.documents import events, service, validation
from app.modules.documents.schemas import (
    CollectionMemberOut,
    CollectionOut,
    CreateCollectionRequest,
    DocumentOut,
    DocumentPage,
    PageInfo,
    PageText,
    SetMembersRequest,
    StatusSummary,
    UpdateCollectionRequest,
    UploadResult,
)
from app.modules.identity.deps import (
    SettingsDep,
    csrf_guard,
    no_store,
    origin_guard,
)
from app.modules.tenancy.deps import Tenant

_guards = [Depends(no_store), Depends(origin_guard), Depends(csrf_guard)]
router = APIRouter(prefix="/orgs", tags=["documents"], dependencies=_guards)


def store_dep(request: Request) -> ObjectStore:
    return request.app.state.store  # type: ignore[no-any-return]


Store = Annotated[ObjectStore, Depends(store_dep)]


# ------------------------------------------------------------ collections


@router.get("/{org_id}/collections", response_model=list[CollectionOut])
async def list_collections(org_id: uuid.UUID, ctx: Tenant) -> list[CollectionOut]:
    return await service.list_collections(ctx)


@router.post("/{org_id}/collections", status_code=201, response_model=CollectionOut)
async def create_collection(
    org_id: uuid.UUID, body: CreateCollectionRequest, ctx: Tenant
) -> CollectionOut:
    return await service.create_collection(ctx, body.name, body.description, body.visibility)


@router.patch("/{org_id}/collections/{collection_id}", response_model=CollectionOut)
async def update_collection(
    org_id: uuid.UUID, collection_id: uuid.UUID, body: UpdateCollectionRequest, ctx: Tenant
) -> CollectionOut:
    return await service.update_collection(
        ctx, collection_id, body.name, body.description, body.visibility
    )


@router.delete("/{org_id}/collections/{collection_id}", status_code=204)
async def delete_collection(
    org_id: uuid.UUID, collection_id: uuid.UUID, ctx: Tenant, store: Store
) -> None:
    await service.delete_collection(ctx, store, collection_id)


@router.get(
    "/{org_id}/collections/{collection_id}/members", response_model=list[CollectionMemberOut]
)
async def list_collection_members(
    org_id: uuid.UUID, collection_id: uuid.UUID, ctx: Tenant
) -> list[CollectionMemberOut]:
    return await service.list_collection_members(ctx, collection_id)


@router.put(
    "/{org_id}/collections/{collection_id}/members", response_model=list[CollectionMemberOut]
)
async def set_collection_members(
    org_id: uuid.UUID, collection_id: uuid.UUID, body: SetMembersRequest, ctx: Tenant
) -> list[CollectionMemberOut]:
    return await service.set_collection_members(ctx, collection_id, body.user_ids)


# ------------------------------------------------------------ documents


@router.post("/{org_id}/documents", response_model=list[UploadResult])
async def upload_documents(
    org_id: uuid.UUID,
    request: Request,
    ctx: Tenant,
    store: Store,
    settings: SettingsDep,
    collection_id: Annotated[uuid.UUID, Form()],
    files: Annotated[list[UploadFile], File()],
) -> list[UploadResult]:
    return await service.upload_documents(
        ctx, store, settings, request.app.state.enqueue, collection_id, files
    )


@router.get("/{org_id}/documents", response_model=DocumentPage)
async def list_documents(
    org_id: uuid.UUID,
    ctx: Tenant,
    collection_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status: Annotated[str | None, Query(max_length=24)] = None,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> DocumentPage:
    return await service.list_documents(
        ctx, collection_id=collection_id, q=q, status=status, cursor=cursor, limit=limit
    )


@router.get("/{org_id}/documents/summary", response_model=StatusSummary)
async def documents_summary(org_id: uuid.UUID, ctx: Tenant) -> StatusSummary:
    return await service.status_summary(ctx)


@router.get("/{org_id}/documents/events")
async def document_events(org_id: uuid.UUID, request: Request, ctx: Tenant) -> StreamingResponse:
    """Server-sent events with document progress. Every event is re-authorised for this caller."""
    session_id = request.state.session_id
    stream = events.stream_events(
        request.app.state.sessionmaker,
        request.app.state.redis,
        user_id=ctx.user.id,
        org_id=ctx.org_id,
        session_id=session_id,
        is_disconnected=request.is_disconnected,
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{org_id}/documents/{document_id}", response_model=DocumentOut)
async def get_document(org_id: uuid.UUID, document_id: uuid.UUID, ctx: Tenant) -> DocumentOut:
    return await service.get_document(ctx, document_id)


@router.delete("/{org_id}/documents/{document_id}", status_code=204)
async def delete_document(
    org_id: uuid.UUID, document_id: uuid.UUID, ctx: Tenant, store: Store
) -> None:
    await service.delete_document(ctx, store, document_id)


@router.get("/{org_id}/documents/{document_id}/file")
async def download_document(
    org_id: uuid.UUID,
    document_id: uuid.UUID,
    ctx: Tenant,
    store: Store,
    download: bool = False,
) -> StreamingResponse:
    """Streams the original file. Authorization is re-checked on EVERY request (no bearer URLs).

    Only PDFs may render inline, and then inside a sandbox; everything else is a download.
    """
    doc = await service.get_file_info(ctx, document_id)
    try:
        body = await store.open_stream(doc.storage_key)
    except ObjectMissingError:
        raise AppError(404, "NOT_FOUND", "Not Found") from None
    except StorageUnavailableError:
        raise service._storage_unavailable() from None
    inline = doc.mime_type == validation.PDF and not download
    media_type = doc.mime_type if doc.mime_type != validation.MD else "text/plain; charset=utf-8"
    return StreamingResponse(
        body,
        media_type=media_type,
        headers={
            "Content-Disposition": validation.content_disposition(doc.original_filename, inline),
            "Content-Length": str(doc.size_bytes),
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'",
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/{org_id}/documents/{document_id}/pages", response_model=list[PageInfo])
async def list_pages(org_id: uuid.UUID, document_id: uuid.UUID, ctx: Tenant) -> list[PageInfo]:
    return await service.list_pages(ctx, document_id)


@router.get("/{org_id}/documents/{document_id}/pages/{page_number}", response_model=PageText)
async def get_page(
    org_id: uuid.UUID, document_id: uuid.UUID, page_number: Annotated[int, Path(ge=1)], ctx: Tenant
) -> PageText:
    return await service.get_page(ctx, document_id, page_number)


@router.post("/{org_id}/documents/{document_id}/reprocess", status_code=HTTP_202_ACCEPTED)
async def reprocess_document(
    org_id: uuid.UUID, document_id: uuid.UUID, request: Request, ctx: Tenant
) -> dict[str, str]:
    await service.reprocess_document(ctx, request.app.state.enqueue, document_id)
    return {"status": "queued"}
