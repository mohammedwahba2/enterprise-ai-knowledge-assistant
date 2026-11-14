"""The ingestion pipeline end to end: real worker role, real Postgres, real object store."""

import io
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select, text, update

from app.core.config import Settings
from app.infrastructure.storage.s3 import S3ObjectStore
from app.modules.documents.models import Document
from app.modules.processing import parsers
from app.modules.processing.models import Chunk, DocumentPage, IngestionJob
from app.modules.processing.parsers import OfficeConverter
from tests import files
from tests.pdfgen import PageSpec, encrypted, make_pdf
from tests.tenancy_helpers import Person, World

ENGLISH = "Employees receive twenty five working days of paid annual leave per calendar year."
ENGLISH2 = "Unused days may be carried over for a maximum of five days until the end of March."
ARABIC = "يحصل الموظفون على خمسة وعشرين يوم عمل من الإجازة السنوية في كل سنة ميلادية من الشركة"
ARABIC2 = "تقدم الطلبات عبر البوابة قبل أسبوعين على الأقل من تاريخ البدء على هذا النحو"
PUA = " "


async def setup(world: World, role: str = "owner") -> tuple[Person, str, str]:
    owner = await world.person("Owner")
    oid = (await world.org(owner, "Acme"))["id"]
    return owner, oid, await world.general(owner, oid)


async def ingest(
    world: World, owner: Person, oid: str, cid: str, name: str, data: bytes, **kw: object
) -> str:
    """Upload through the API, then process as the worker. Returns the document id."""
    r = await owner.upload(oid, cid, (name, data))
    assert r.json()[0]["outcome"] == "created", r.text
    doc_id = str(r.json()[0]["document"]["id"])
    outcome = await world.process(oid, doc_id, **kw)
    assert outcome in ("processed", "failed")
    return doc_id


async def fetch(
    world: World, owner: Person, oid: str, doc_id: str
) -> tuple[Document, list[DocumentPage], list[Chunk]]:
    async with world.scoped_db(oid, owner.user_id) as s:
        doc = (await s.scalars(select(Document).where(Document.id == uuid.UUID(doc_id)))).one()
        pages = list(
            (
                await s.scalars(
                    select(DocumentPage)
                    .where(DocumentPage.document_id == doc.id)
                    .order_by(DocumentPage.page_number)
                )
            ).all()
        )
        chunks_result = await s.execute(
            text("select 1")
        )  # app role has no chunk access: read as worker below
        assert chunks_result is not None
    return doc, pages, []


async def chunks_of(world: World, doc_id: str) -> list[dict[str, object]]:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.db.base import to_async_url

    engine = create_async_engine(to_async_url(world.worker_db_url), poolclass=NullPool)
    try:
        async with async_sessionmaker(engine)() as s:
            rows = (
                await s.scalars(
                    select(Chunk)
                    .where(Chunk.document_id == uuid.UUID(doc_id))
                    .order_by(Chunk.chunk_index)
                )
            ).all()
            return [
                {
                    "index": c.chunk_index,
                    "p0": c.page_start,
                    "p1": c.page_end,
                    "content": c.content,
                    "search": c.content_search,
                    "lang": c.lang,
                    "heading": c.heading_path,
                }
                for c in rows
            ]
    finally:
        await engine.dispose()


async def jobs_of(world: World, doc_id: str) -> list[IngestionJob]:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.db.base import to_async_url

    engine = create_async_engine(to_async_url(world.worker_db_url), poolclass=NullPool)
    try:
        async with async_sessionmaker(engine)() as s:
            return list(
                (
                    await s.scalars(
                        select(IngestionJob)
                        .where(IngestionJob.document_id == uuid.UUID(doc_id))
                        .order_by(IngestionJob.attempt)
                    )
                ).all()
            )
    finally:
        await engine.dispose()


# =============================================================== happy paths


async def test_a_text_pdf_becomes_ready_with_pages_chunks_and_a_job_record(world: World) -> None:
    owner, oid, cid = await setup(world)
    events: list[tuple[str, str | None]] = []

    async def publish(_o: uuid.UUID, _d: uuid.UUID, status: str, code: str | None) -> None:
        events.append((status, code))

    pdf = make_pdf(
        [PageSpec([ENGLISH, ENGLISH2]), PageSpec(["4.4 Carry-over", ENGLISH2]), PageSpec([ENGLISH])]
    )
    doc_id = await ingest(world, owner, oid, cid, "handbook.pdf", pdf, publish=publish)
    doc, pages, _ = await fetch(world, owner, oid, doc_id)
    assert (doc.status, doc.error_code, doc.page_count, doc.language, doc.pagination) == (
        "ready",
        None,
        3,
        "en",
        "native",
    )
    assert doc.page_summary == {"total": 3, "text": 3, "image_only": 0, "garbled": 0}
    assert [p.extraction_state for p in pages] == ["text"] * 3 and doc.processed_at is not None
    chunks = await chunks_of(world, doc_id)
    assert chunks and chunks[0]["p0"] == 1 and chunks[-1]["p1"] == 3
    assert "twenty five working days" in " ".join(str(c["content"]) for c in chunks)
    assert events == [("parsing", None), ("chunking", None), ("ready", None)]  # progress, in order
    jobs = await jobs_of(world, doc_id)
    assert [(j.attempt, j.status, j.stage) for j in jobs] == [(1, "succeeded", "chunking")]
    assert jobs[0].finished_at is not None


async def test_arabic_text_is_repaired_and_searchable(world: World) -> None:
    owner, oid, cid = await setup(world)
    pdf = make_pdf([PageSpec([ARABIC, ARABIC2]), PageSpec([ARABIC2, ARABIC])])
    doc_id = await ingest(world, owner, oid, cid, "دليل.pdf", pdf)
    doc, pages, _ = await fetch(world, owner, oid, doc_id)
    assert doc.status == "ready" and doc.language == "ar"
    joined = " ".join(p.text for p in pages)
    # pdfium hands right-to-left runs back in visual order; the pipeline restores logical order
    assert "يحصل الموظفون على" in joined and "تقدم الطلبات عبر البوابة" in joined
    chunks = await chunks_of(world, doc_id)
    assert chunks and all(c["lang"] == "ar" for c in chunks)
    assert "الاجازه" not in str(
        chunks[0]["search"]
    )  # search form folds alef variants, not ta marbuta
    assert "الاجازة" in str(chunks[0]["search"])


async def test_mixed_language_documents_are_labelled_mixed(world: World) -> None:
    owner, oid, cid = await setup(world)
    pdf = make_pdf([PageSpec([ENGLISH, ARABIC, ENGLISH2, ARABIC2])])
    doc_id = await ingest(world, owner, oid, cid, "bilingual.pdf", pdf)
    doc, _, _ = await fetch(world, owner, oid, doc_id)
    assert doc.status == "ready" and doc.language == "mixed"


async def test_text_and_markdown_get_virtual_pages_and_headings(world: World) -> None:
    owner, oid, cid = await setup(world)
    md = (
        "# Handbook\n\n"
        + "\n\n".join(f"{ENGLISH} Paragraph {i}. " + "filler words " * 100 for i in range(12))
    ).encode()
    doc_id = await ingest(world, owner, oid, cid, "handbook.md", md)
    doc, pages, _ = await fetch(world, owner, oid, doc_id)
    assert (doc.status, doc.pagination, doc.mime_type) == ("ready", "virtual", "text/markdown")
    assert len(pages) > 1 and doc.page_count == len(pages)
    txt_id = await ingest(
        world, owner, oid, cid, "notes.txt", files.text_file(ENGLISH + " " + ENGLISH2)
    )
    assert (await fetch(world, owner, oid, txt_id))[0].status == "ready"


# =============================================================== unreadable documents


async def test_partial_documents_name_their_unreadable_pages_and_index_only_the_rest(
    world: World,
) -> None:
    owner, oid, cid = await setup(world)
    pdf = make_pdf(
        [
            PageSpec([ENGLISH, ENGLISH2]),
            PageSpec([], image_ratio=0.9),
            PageSpec([ENGLISH2, ENGLISH]),
            PageSpec([PUA]),
        ]
    )
    doc_id = await ingest(world, owner, oid, cid, "partial.pdf", pdf)
    doc, pages, _ = await fetch(world, owner, oid, doc_id)
    assert (doc.status, doc.error_code) == ("ready_partial", "PARTIAL_TEXT")
    assert doc.page_summary == {"total": 4, "text": 2, "image_only": 1, "garbled": 1}
    assert [p.extraction_state for p in pages] == ["text", "image_only", "text", "garbled"]
    assert [bool(p.text) for p in pages] == [
        True,
        False,
        True,
        False,
    ]  # unusable pages keep no text at all
    chunks = await chunks_of(world, doc_id)
    assert chunks and {c["p0"] for c in chunks} | {c["p1"] for c in chunks} <= {
        1,
        3,
    }  # nothing from pages 2 and 4


async def test_scanned_documents_are_flagged_not_silently_empty(world: World) -> None:
    owner, oid, cid = await setup(world)
    pdf = make_pdf([PageSpec([], image_ratio=0.95), PageSpec([], image_ratio=0.95)])
    doc_id = await ingest(world, owner, oid, cid, "scan.pdf", pdf)
    doc, pages, _ = await fetch(world, owner, oid, doc_id)
    assert (doc.status, doc.error_code) == ("unsupported_scanned", "NO_TEXT_LAYER")
    assert [p.extraction_state for p in pages] == ["image_only"] * 2
    assert await chunks_of(world, doc_id) == []


async def test_garbled_documents_are_flagged(world: World) -> None:
    owner, oid, cid = await setup(world)
    doc_id = await ingest(
        world, owner, oid, cid, "broken-font.pdf", make_pdf([PageSpec([PUA, PUA]), PageSpec([PUA])])
    )
    doc, _, _ = await fetch(world, owner, oid, doc_id)
    assert (doc.status, doc.error_code) == ("unsupported_garbled", "GARBLED_TEXT")
    assert await chunks_of(world, doc_id) == []


@pytest.mark.parametrize(
    ("name", "build", "code"),
    [
        ("blank.pdf", lambda: make_pdf([PageSpec([]), PageSpec([])]), "EMPTY_DOCUMENT"),
        ("locked.pdf", lambda: encrypted(make_pdf([PageSpec([ENGLISH])])), "ENCRYPTED"),
        ("damaged.pdf", lambda: b"%PDF-1.4\n" + b"\x00\xff" * 3000, "CORRUPT"),
    ],
)
async def test_unprocessable_files_fail_with_a_stable_code(
    world: World, name: str, build: object, code: str
) -> None:
    owner, oid, cid = await setup(world)
    doc_id = await ingest(world, owner, oid, cid, name, build())  # type: ignore[operator]
    doc, pages, _ = await fetch(world, owner, oid, doc_id)
    assert (doc.status, doc.error_code) == ("failed", code)
    assert doc.error_detail and "Traceback" not in doc.error_detail and "/" not in doc.error_detail
    if (
        code != "EMPTY_DOCUMENT"
    ):  # a blank document keeps its (blank) page rows, the others never got that far
        assert pages == []
    assert await chunks_of(world, doc_id) == []
    jobs = await jobs_of(world, doc_id)
    assert jobs[-1].status == "failed" and jobs[-1].error_code == code


async def test_page_limit(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parsers, "MAX_PAGES", 2)
    owner, oid, cid = await setup(world)
    doc_id = await ingest(
        world, owner, oid, cid, "long.pdf", make_pdf([PageSpec([ENGLISH]) for _ in range(3)])
    )
    assert (await fetch(world, owner, oid, doc_id))[0].error_code == "TOO_MANY_PAGES"


# =============================================================== Office documents


class StubConverter(OfficeConverter):
    """Stands in for LibreOffice (the real one runs in the worker image; see the live verification)."""

    def __init__(self, tmp: Path, pdf: bytes) -> None:
        super().__init__("stub")
        self._pdf, self._tmp = pdf, tmp

    def to_pdf(self, source: Path) -> Path:
        out = self._tmp / f"{source.stem}.converted.pdf"
        out.write_bytes(self._pdf)
        return out


async def test_office_documents_go_through_conversion_and_keep_the_rendered_pdf(
    world: World, tmp_path: Path, settings: Settings
) -> None:
    owner, oid, cid = await setup(world)
    rendered = make_pdf([PageSpec([ENGLISH, ENGLISH2]), PageSpec([ENGLISH2])])
    doc_id = await ingest(
        world,
        owner,
        oid,
        cid,
        "policy.docx",
        files.docx("policy"),
        converter=StubConverter(tmp_path, rendered),
    )
    doc, _pages, _ = await fetch(world, owner, oid, doc_id)
    assert (doc.status, doc.pagination, doc.page_count) == ("ready", "native", 2)
    assert doc.viewer_key == f"org/{oid}/doc/{doc_id}.viewer.pdf"
    assert await S3ObjectStore(settings).exists(doc.viewer_key)  # the pages users will cite
    deck_id = await ingest(
        world,
        owner,
        oid,
        cid,
        "deck.pptx",
        files.pptx("deck"),
        converter=StubConverter(tmp_path, rendered),
    )
    assert (await fetch(world, owner, oid, deck_id))[0].status == "ready"


async def test_office_documents_fail_cleanly_when_conversion_is_unavailable(world: World) -> None:
    owner, oid, cid = await setup(world)
    doc_id = await ingest(
        world, owner, oid, cid, "policy.docx", files.docx("policy")
    )  # no soffice here
    doc, _, _ = await fetch(world, owner, oid, doc_id)
    assert (doc.status, doc.error_code) == ("failed", "CONVERSION_FAILED")


# =============================================================== robustness


async def test_reprocessing_replaces_results_instead_of_duplicating_them(world: World) -> None:
    owner, oid, cid = await setup(world)
    pdf = make_pdf([PageSpec([ENGLISH, ENGLISH2]), PageSpec([ENGLISH2])])
    doc_id = await ingest(world, owner, oid, cid, "a.pdf", pdf)
    first = await chunks_of(world, doc_id)
    assert (
        await world.process(oid, doc_id) == "skipped"
    )  # already ready: a duplicate task does nothing
    async with world.scoped_db(oid, owner.user_id) as s:
        await s.execute(
            update(Document).where(Document.id == uuid.UUID(doc_id)).values(status="uploaded")
        )
        await s.commit()
    assert await world.process(oid, doc_id) == "processed"
    second = await chunks_of(world, doc_id)
    assert [c["content"] for c in second] == [c["content"] for c in first] and len(second) == len(
        first
    )
    _, pages, _ = await fetch(world, owner, oid, doc_id)
    assert len(pages) == 2
    assert [j.attempt for j in await jobs_of(world, doc_id)] == [1, 2]


async def test_a_document_deleted_while_processing_leaves_nothing_behind(world: World) -> None:
    owner, oid, cid = await setup(world)
    r = await owner.upload(oid, cid, ("a.pdf", make_pdf([PageSpec([ENGLISH, ENGLISH2])])))
    doc_id = r.json()[0]["document"]["id"]

    async def delete_midway(_o: uuid.UUID, _d: uuid.UUID, status: str, _c: str | None) -> None:
        if status == "chunking":
            await owner.delete(f"/orgs/{oid}/documents/{doc_id}")

    assert await world.process(oid, doc_id, publish=delete_midway) == "skipped"
    assert await chunks_of(world, doc_id) == []
    async with world.scoped_db(oid, owner.user_id) as s:
        assert (
            await s.scalars(
                select(DocumentPage).where(DocumentPage.document_id == uuid.UUID(doc_id))
            )
        ).all() == []


async def test_a_missing_object_is_a_clean_failure(world: World, settings: Settings) -> None:
    owner, oid, cid = await setup(world)
    r = await owner.upload(oid, cid, ("a.pdf", make_pdf([PageSpec([ENGLISH])])))
    doc_id = r.json()[0]["document"]["id"]
    await S3ObjectStore(settings).delete(f"org/{oid}/doc/{doc_id}")
    assert await world.process(oid, doc_id) == "failed"
    assert (await fetch(world, owner, oid, doc_id))[0].error_code == "FILE_MISSING"


async def test_unexpected_errors_are_recorded_without_leaking_internals(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_: Path) -> list[parsers.RawPage]:
        raise RuntimeError("secret internal path /srv/private/key.pem")

    monkeypatch.setattr(parsers, "parse_pdf", boom)
    owner, oid, cid = await setup(world)
    doc_id = await ingest(world, owner, oid, cid, "a.pdf", make_pdf([PageSpec([ENGLISH])]))
    doc, _, _ = await fetch(world, owner, oid, doc_id)
    assert (doc.status, doc.error_code) == ("failed", "PROCESSING_ERROR")
    assert "secret" not in (doc.error_detail or "") and "/srv" not in (doc.error_detail or "")


async def test_a_failing_event_publisher_does_not_fail_the_job(world: World) -> None:
    async def broken(*_: object) -> None:
        raise ConnectionError("redis is down")

    owner, oid, cid = await setup(world)
    doc_id = await ingest(
        world, owner, oid, cid, "a.pdf", make_pdf([PageSpec([ENGLISH, ENGLISH2])]), publish=broken
    )
    assert (await fetch(world, owner, oid, doc_id))[0].status == "ready"


async def test_a_document_in_another_org_is_never_touched(world: World) -> None:
    owner, oid, cid = await setup(world)
    other = await world.person("Other")
    other_org = (await world.org(other, "Other"))["id"]
    r = await owner.upload(oid, cid, ("a.pdf", make_pdf([PageSpec([ENGLISH, ENGLISH2])])))
    doc_id = r.json()[0]["document"]["id"]
    # the task payload names the wrong organization: the pipeline must refuse it
    assert await world.process(other_org, doc_id) == "skipped"
    assert (await fetch(world, owner, oid, doc_id))[0].status == "uploaded"


_ = io  # (kept for ad-hoc debugging of fixtures)
