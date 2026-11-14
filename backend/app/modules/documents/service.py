import base64
import binascii
import hashlib
import tempfile
import uuid
from datetime import UTC, datetime
from typing import IO, Any

import structlog
from fastapi import UploadFile
from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.errors import AppError
from app.db.base import new_id
from app.infrastructure.storage.s3 import ObjectStore, StorageUnavailableError
from app.modules.access import policies
from app.modules.access.policies import Action, Role
from app.modules.documents import validation
from app.modules.documents.models import Collection, CollectionMember, Document
from app.modules.documents.schemas import (
    CollectionMemberOut,
    CollectionOut,
    DocumentOut,
    DocumentPage,
    PageInfo,
    PageText,
    StatusSummary,
    UploadResult,
)
from app.modules.identity.models import User
from app.modules.processing.models import DocumentPage as PageRow
from app.modules.processing.queue import Enqueue
from app.modules.tenancy.deps import TenantCtx
from app.modules.tenancy.models import Membership

_log = structlog.get_logger("documents")
READ_CHUNK = 1024 * 1024
SPOOL_MEMORY = 8 * 1024 * 1024


def _storage_unavailable() -> AppError:
    return AppError(
        503, "STORAGE_UNAVAILABLE", "File storage is temporarily unavailable",
        headers={"Retry-After": "5"},
    )  # fmt: skip


# =============================================================== collections


def _accessible_ids(ctx: TenantCtx) -> Select[Any]:
    """Ids of the collections this caller may access, computed explicitly in the application.

    This is the application layer of document permissions; PostgreSQL RLS enforces the same rule
    independently (`app_can_access_collection`), so either layer alone keeps restricted
    collections away from unlisted members.
    """
    stmt = select(Collection.id).where(Collection.organization_id == ctx.org_id)
    if ctx.role not in (Role.OWNER, Role.ADMIN):
        listed = select(CollectionMember.collection_id).where(
            CollectionMember.user_id == ctx.user.id
        )
        stmt = stmt.where(or_(Collection.visibility == "org", Collection.id.in_(listed)))
    return stmt


async def _collection(ctx: TenantCtx, collection_id: uuid.UUID) -> Collection:
    """A collection the caller may access. Inaccessible and nonexistent look identical (404)."""
    row = await ctx.db.scalar(
        select(Collection).where(
            Collection.id == collection_id,
            Collection.organization_id == ctx.org_id,
            Collection.id.in_(_accessible_ids(ctx)),
        )
    )
    if row is None:
        raise validation.not_found()
    return row


async def list_collections(ctx: TenantCtx) -> list[CollectionOut]:
    policies.require(ctx.role, Action.DOCUMENT_VIEW)
    cols = (
        await ctx.db.scalars(
            select(Collection)
            .where(
                Collection.organization_id == ctx.org_id, Collection.id.in_(_accessible_ids(ctx))
            )
            .order_by(func.lower(Collection.name))
        )
    ).all()
    doc_counts = dict(
        (
            await ctx.db.execute(
                select(Document.collection_id, func.count())
                .where(Document.organization_id == ctx.org_id, Document.deleted_at.is_(None))
                .group_by(Document.collection_id)
            )
        ).all()
    )  # fmt: skip
    is_admin = policies.can(ctx.role, Action.COLLECTION_MANAGE)
    member_counts: dict[uuid.UUID, int] = {}
    if is_admin:
        member_counts = dict(
            (
                await ctx.db.execute(
                    select(CollectionMember.collection_id, func.count())
                    .where(CollectionMember.organization_id == ctx.org_id)
                    .group_by(CollectionMember.collection_id)
                )
            ).all()
        )  # fmt: skip
    can_upload = policies.can(ctx.role, Action.DOCUMENT_UPLOAD)
    return [
        CollectionOut(
            id=c.id, name=c.name, description=c.description,
            visibility=c.visibility,  # type: ignore[arg-type]
            document_count=doc_counts.get(c.id, 0),
            member_count=member_counts.get(c.id, 0) if is_admin else None,
            can_upload=can_upload,
        )
        for c in cols
    ]  # fmt: skip


async def _collection_out(ctx: TenantCtx, c: Collection) -> CollectionOut:
    for item in await list_collections(ctx):
        if item.id == c.id:
            return item
    raise validation.not_found()


async def create_collection(
    ctx: TenantCtx, name: str, description: str, visibility: str
) -> CollectionOut:
    policies.require(ctx.role, Action.COLLECTION_MANAGE)
    col = Collection(
        organization_id=ctx.org_id, name=name, description=description,
        visibility=visibility, created_by=ctx.user.id,
    )  # fmt: skip
    ctx.db.add(col)
    try:
        await ctx.db.flush()
    except IntegrityError:
        await ctx.db.rollback()
        raise AppError(409, "NAME_TAKEN", "A collection with that name already exists") from None
    await ctx.db.commit()
    _log.info(
        "collection.created",
        org_id=str(ctx.org_id),
        collection_id=str(col.id),
        visibility=visibility,
    )
    return await _collection_out(ctx, col)


async def update_collection(
    ctx: TenantCtx,
    collection_id: uuid.UUID,
    name: str | None,
    description: str | None,
    visibility: str | None,
) -> CollectionOut:
    policies.require(ctx.role, Action.COLLECTION_MANAGE)
    col = await _collection(ctx, collection_id)
    if name is not None:
        col.name = name
    if description is not None:
        col.description = description
    if visibility is not None and visibility != col.visibility:
        if (
            visibility == "org"
        ):  # opening a collection up: forget its old ACL so it cannot silently return
            await ctx.db.execute(
                delete(CollectionMember).where(CollectionMember.collection_id == col.id)
            )
        col.visibility = visibility
        _log.warning(
            "collection.visibility_changed", org_id=str(ctx.org_id), actor=str(ctx.user.id),
            collection_id=str(col.id), visibility=visibility,
        )  # fmt: skip
    try:
        await ctx.db.commit()
    except IntegrityError:
        await ctx.db.rollback()
        raise AppError(409, "NAME_TAKEN", "A collection with that name already exists") from None
    return await _collection_out(ctx, col)


async def delete_collection(ctx: TenantCtx, store: ObjectStore, collection_id: uuid.UUID) -> None:
    policies.require(ctx.role, Action.COLLECTION_MANAGE)
    col = await _collection(ctx, collection_id)
    live = await ctx.db.scalar(
        select(func.count())
        .select_from(Document)
        .where(Document.collection_id == col.id, Document.deleted_at.is_(None))
    )
    if live:
        raise AppError(409, "COLLECTION_NOT_EMPTY", "Delete or move the documents first")
    leftovers = (
        await ctx.db.scalars(select(Document).where(Document.collection_id == col.id))
    ).all()  # soft-deleted rows still referencing it
    for doc in leftovers:
        if doc.purged_at is None:
            try:
                await store.delete(doc.storage_key)
            except StorageUnavailableError:
                raise _storage_unavailable() from None
    await ctx.db.execute(delete(Document).where(Document.collection_id == col.id))
    await ctx.db.delete(col)
    await ctx.db.commit()
    _log.warning(
        "collection.deleted",
        org_id=str(ctx.org_id),
        actor=str(ctx.user.id),
        collection_id=str(col.id),
    )


async def list_collection_members(
    ctx: TenantCtx, collection_id: uuid.UUID
) -> list[CollectionMemberOut]:
    policies.require(ctx.role, Action.COLLECTION_MANAGE)
    col = await _collection(ctx, collection_id)
    rows = await ctx.db.execute(
        select(User).join(CollectionMember, CollectionMember.user_id == User.id)
        .where(CollectionMember.collection_id == col.id)
        .order_by(User.display_name)
    )  # fmt: skip
    return [
        CollectionMemberOut(user_id=u.id, display_name=u.display_name, email=u.email)
        for u in rows.scalars()
    ]


async def set_collection_members(
    ctx: TenantCtx, collection_id: uuid.UUID, user_ids: list[uuid.UUID]
) -> list[CollectionMemberOut]:
    policies.require(ctx.role, Action.COLLECTION_MANAGE)
    col = await _collection(ctx, collection_id)
    if col.visibility != "restricted":
        raise AppError(409, "NOT_RESTRICTED", "Only restricted collections have a member list")
    wanted = set(user_ids)
    if wanted:
        found = set(
            (
                await ctx.db.scalars(
                    select(Membership.user_id).where(
                        Membership.organization_id == ctx.org_id, Membership.user_id.in_(wanted)
                    )
                )
            ).all()
        )
        if found != wanted:
            raise AppError(422, "NOT_ORG_MEMBER", "Every listed user must belong to this workspace")
    await ctx.db.execute(delete(CollectionMember).where(CollectionMember.collection_id == col.id))
    for uid in wanted:
        ctx.db.add(CollectionMember(collection_id=col.id, user_id=uid, organization_id=ctx.org_id))
    await ctx.db.commit()
    _log.info(
        "collection.members_set", org_id=str(ctx.org_id), actor=str(ctx.user.id), count=len(wanted)
    )
    return await list_collection_members(ctx, collection_id)


# =============================================================== documents


def _doc_out(doc: Document, collection_name: str, uploader: str | None) -> DocumentOut:
    return DocumentOut(
        id=doc.id, collection_id=doc.collection_id, collection_name=collection_name,
        title=doc.title, original_filename=doc.original_filename, mime_type=doc.mime_type,
        size_bytes=doc.size_bytes, status=doc.status, error_code=doc.error_code,
        page_count=doc.page_count, language=doc.language, page_summary=doc.page_summary,
        uploaded_by_name=uploader, created_at=doc.created_at,
    )  # fmt: skip


async def _spool(file: UploadFile, limit: int) -> tuple[IO[bytes], int, str]:
    """Copy the upload into a temp file while hashing; stop as soon as the limit is exceeded."""
    tmp = tempfile.SpooledTemporaryFile(max_size=SPOOL_MEMORY)  # noqa: SIM115 (closed by the caller)
    digest = hashlib.sha256()
    size = 0
    try:
        while chunk := await file.read(READ_CHUNK):
            size += len(chunk)
            if size > limit:
                raise validation.Rejected("FILE_TOO_LARGE")
            digest.update(chunk)
            tmp.write(chunk)
    except BaseException:
        tmp.close()
        raise
    if size == 0:
        tmp.close()
        raise validation.Rejected("EMPTY_FILE")
    tmp.seek(0)
    return tmp, size, digest.hexdigest()


async def upload_documents(
    ctx: TenantCtx,
    store: ObjectStore,
    settings: Settings,
    enqueue: Enqueue,
    collection_id: uuid.UUID,
    files: list[UploadFile],
) -> list[UploadResult]:
    policies.require(ctx.role, Action.DOCUMENT_UPLOAD)
    if not files:
        raise AppError(422, "NO_FILES", "Attach at least one file")
    if len(files) > settings.max_files_per_upload:
        raise AppError(
            422, "TOO_MANY_FILES", f"At most {settings.max_files_per_upload} files per upload"
        )
    collection = await _collection(ctx, collection_id)
    results: list[UploadResult] = []
    for upload in files:
        results.append(await _ingest_one(ctx, store, settings, enqueue, collection, upload))
    return results


async def _existing(ctx: TenantCtx, collection: Collection, sha256: str) -> Document | None:
    return await ctx.db.scalar(
        select(Document).where(
            Document.organization_id == ctx.org_id, Document.collection_id == collection.id,
            Document.sha256 == sha256, Document.deleted_at.is_(None),
        )
    )  # fmt: skip


async def _ingest_one(
    ctx: TenantCtx,
    store: ObjectStore,
    settings: Settings,
    enqueue: Enqueue,
    collection: Collection,
    upload: UploadFile,
) -> UploadResult:
    display = validation.sanitize_filename(upload.filename or "")
    try:
        tmp, size, sha256 = await _spool(upload, settings.max_upload_bytes)
    except validation.Rejected as r:
        return UploadResult(filename=display, outcome="rejected", error_code=r.code)
    try:
        try:
            sniffed = validation.sniff(tmp, display)
        except validation.Rejected as r:
            return UploadResult(filename=display, outcome="rejected", error_code=r.code)

        uploader = ctx.user.display_name
        dup = await _existing(ctx, collection, sha256)
        if dup is not None:
            return UploadResult(
                filename=display,
                outcome="duplicate",
                document=_doc_out(dup, collection.name, uploader),
            )

        doc_id = new_id()
        key = f"org/{ctx.org_id}/doc/{doc_id}"  # opaque: the filename never reaches storage
        try:
            await store.put(key, tmp, sniffed.mime)
        except StorageUnavailableError:
            raise _storage_unavailable() from None

        try:  # everything after the object is stored: any failure must remove the object again
            doc = Document(
                id=doc_id, organization_id=ctx.org_id, collection_id=collection.id,
                title=validation.title_from(display), original_filename=display,
                mime_type=sniffed.mime, size_bytes=size, sha256=sha256, storage_key=key,
                uploaded_by=ctx.user.id,
            )  # fmt: skip
            try:
                async with ctx.db.begin_nested():
                    ctx.db.add(doc)
                    await ctx.db.flush()
                await ctx.db.commit()
            except IntegrityError:
                # lost a race with an identical upload: keep theirs, drop our object
                await _discard(store, key)
                winner = await _existing(ctx, collection, sha256)
                if winner is None:
                    raise
                return UploadResult(
                    filename=display,
                    outcome="duplicate",
                    document=_doc_out(winner, collection.name, uploader),
                )
        except BaseException:
            await _discard(store, key)  # never leave an object without a row
            raise
        _log.info(
            "document.uploaded",
            org_id=str(ctx.org_id),
            document_id=str(doc.id),
            size=size,
            mime=sniffed.mime,
        )
        try:
            await enqueue(doc.id, ctx.org_id)  # processing starts in the background worker
        except Exception:  # the upload is stored; the sweeper re-queues anything that never started
            _log.error("enqueue_failed", document_id=str(doc.id), exc_info=True)
        return UploadResult(
            filename=display, outcome="created", document=_doc_out(doc, collection.name, uploader)
        )
    finally:
        tmp.close()


async def _discard(store: ObjectStore, key: str) -> None:
    try:
        await store.delete(key)
    except StorageUnavailableError:
        _log.error("orphan_object_left_behind", key=key)


def _encode_cursor(created_at: datetime, doc_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{created_at.isoformat()}|{doc_id}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts, ident = raw.split("|", 1)
        return datetime.fromisoformat(ts), uuid.UUID(ident)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise AppError(422, "INVALID_CURSOR", "Invalid pagination cursor") from None


def _like_escape(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


async def list_documents(
    ctx: TenantCtx, *, collection_id: uuid.UUID | None, q: str | None, status: str | None,
    cursor: str | None, limit: int,
) -> DocumentPage:  # fmt: skip
    policies.require(ctx.role, Action.DOCUMENT_VIEW)
    stmt = (
        select(Document, Collection.name, User.display_name)
        .join(Collection, Collection.id == Document.collection_id)
        .outerjoin(User, User.id == Document.uploaded_by)
        .where(
            Document.organization_id == ctx.org_id,
            Document.deleted_at.is_(None),
            Document.collection_id.in_(_accessible_ids(ctx)),
        )
    )
    if collection_id is not None:
        stmt = stmt.where(Document.collection_id == collection_id)
    if status:
        stmt = stmt.where(Document.status == status)
    if q and q.strip():
        pattern = f"%{_like_escape(q.strip())}%"
        stmt = stmt.where(
            or_(
                Document.title.ilike(pattern, escape="\\"),
                Document.original_filename.ilike(pattern, escape="\\"),
            )
        )
    if cursor:
        ts, ident = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(Document.created_at < ts, (Document.created_at == ts) & (Document.id < ident))
        )
    rows = (
        await ctx.db.execute(
            stmt.order_by(Document.created_at.desc(), Document.id.desc()).limit(limit + 1)
        )
    ).all()
    page = rows[:limit]
    next_cursor = (
        _encode_cursor(page[-1][0].created_at, page[-1][0].id)
        if len(rows) > limit and page
        else None
    )
    return DocumentPage(items=[_doc_out(d, c, u) for d, c, u in page], next_cursor=next_cursor)


async def _document(ctx: TenantCtx, document_id: uuid.UUID) -> tuple[Document, str, str | None]:
    row = (
        await ctx.db.execute(
            select(Document, Collection.name, User.display_name)
            .join(Collection, Collection.id == Document.collection_id)
            .outerjoin(User, User.id == Document.uploaded_by)
            .where(
                Document.id == document_id,
                Document.organization_id == ctx.org_id,
                Document.deleted_at.is_(None),
                Document.collection_id.in_(_accessible_ids(ctx)),
            )
        )
    ).first()
    if row is None:
        raise validation.not_found()
    return row[0], row[1], row[2]


async def get_document(ctx: TenantCtx, document_id: uuid.UUID) -> DocumentOut:
    policies.require(ctx.role, Action.DOCUMENT_VIEW)
    doc, cname, uname = await _document(ctx, document_id)
    return _doc_out(doc, cname, uname)


async def get_file_info(ctx: TenantCtx, document_id: uuid.UUID) -> Document:
    policies.require(ctx.role, Action.DOCUMENT_VIEW)
    doc, _, _ = await _document(ctx, document_id)
    return doc


async def delete_document(ctx: TenantCtx, store: ObjectStore, document_id: uuid.UUID) -> None:
    policies.require(ctx.role, Action.DOCUMENT_DELETE)
    doc, _, _ = await _document(ctx, document_id)
    key = doc.storage_key
    doc.deleted_at = datetime.now(UTC)
    await ctx.db.commit()  # from here on it is gone for every reader
    _log.info(
        "document.deleted",
        org_id=str(ctx.org_id),
        actor=str(ctx.user.id),
        document_id=str(document_id),
    )
    try:
        await store.delete(key)
    except StorageUnavailableError:
        _log.error("document_object_purge_pending", document_id=str(document_id))  # swept later
        return
    doc.purged_at = datetime.now(UTC)
    await ctx.db.commit()


# =============================================================== processing state

PROCESSING = ("uploaded", "parsing", "chunking", "embedding")
NEEDS_ATTENTION = ("failed", "unsupported_scanned", "unsupported_garbled", "ready_partial")


async def reprocess_document(ctx: TenantCtx, enqueue: Enqueue, document_id: uuid.UUID) -> None:
    policies.require(ctx.role, Action.DOCUMENT_REPROCESS)
    doc, _, _ = await _document(ctx, document_id)
    if doc.status in PROCESSING:
        raise AppError(409, "ALREADY_PROCESSING", "This document is already being processed")
    doc.status = "uploaded"
    doc.error_code = None
    doc.error_detail = None
    await ctx.db.commit()
    _log.info(
        "document.reprocess",
        org_id=str(ctx.org_id),
        actor=str(ctx.user.id),
        document_id=str(doc.id),
    )
    await enqueue(doc.id, ctx.org_id)


async def list_pages(ctx: TenantCtx, document_id: uuid.UUID) -> list[PageInfo]:
    policies.require(ctx.role, Action.DOCUMENT_VIEW)
    doc, _, _ = await _document(ctx, document_id)
    rows = await ctx.db.scalars(
        select(PageRow)
        .where(
            PageRow.document_id == doc.id,
            PageRow.organization_id == ctx.org_id,
            PageRow.collection_id.in_(_accessible_ids(ctx)),
        )
        .order_by(PageRow.page_number)
    )
    return [
        PageInfo(
            page_number=p.page_number, extraction_state=p.extraction_state, char_count=p.char_count
        )
        for p in rows
    ]


async def get_page(ctx: TenantCtx, document_id: uuid.UUID, page_number: int) -> PageText:
    policies.require(ctx.role, Action.DOCUMENT_VIEW)
    doc, _, _ = await _document(ctx, document_id)
    page = await ctx.db.scalar(
        select(PageRow).where(
            PageRow.document_id == doc.id,
            PageRow.page_number == page_number,
            PageRow.organization_id == ctx.org_id,
            PageRow.collection_id.in_(_accessible_ids(ctx)),
        )
    )
    if page is None:
        raise validation.not_found()
    return PageText(
        page_number=page.page_number, extraction_state=page.extraction_state,
        char_count=page.char_count, text=page.text,
    )  # fmt: skip


async def status_summary(ctx: TenantCtx) -> StatusSummary:
    policies.require(ctx.role, Action.DOCUMENT_VIEW)
    rows = (
        await ctx.db.execute(
            select(Document.status, func.count())
            .where(
                Document.organization_id == ctx.org_id,
                Document.deleted_at.is_(None),
                Document.collection_id.in_(_accessible_ids(ctx)),
            )
            .group_by(Document.status)
        )
    ).all()
    by_status = {status: int(count) for status, count in rows}
    return StatusSummary(
        total=sum(by_status.values()),
        by_status=by_status,
        needs_attention=sum(by_status.get(s, 0) for s in NEEDS_ATTENTION),
    )
