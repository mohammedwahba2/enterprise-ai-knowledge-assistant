import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.infrastructure.storage.s3 import S3ObjectStore
from app.modules.documents import validation
from app.modules.documents.models import Document
from tests import files
from tests.tenancy_helpers import Person, World

SAMPLES = {
    "report.pdf": (files.pdf("report"), "application/pdf"),
    "policy.docx": (
        files.docx("policy"),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    "deck.pptx": (
        files.pptx("deck"),
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ),
    "notes.txt": (files.text_file("notes"), "text/plain"),
    "readme.md": (files.text_file("# readme"), "text/markdown"),
}


@pytest.fixture
async def store(settings: Settings) -> AsyncIterator[S3ObjectStore]:
    yield S3ObjectStore(settings)


async def _org(world: World) -> tuple[Person, str, str]:
    owner = await world.person("Owner")
    org = await world.org(owner, "Acme")
    return owner, org["id"], await world.general(owner, org["id"])


# =============================================================== upload


async def test_every_supported_type_uploads_and_is_listed(world: World) -> None:
    owner, oid, cid = await _org(world)
    r = await owner.upload(oid, cid, *[(n, c) for n, (c, _) in SAMPLES.items()])
    assert r.status_code == 200
    results = r.json()
    assert [x["outcome"] for x in results] == ["created"] * 5
    by_name = {x["filename"]: x["document"] for x in results}
    for name, (_, mime) in SAMPLES.items():
        d = by_name[name]
        assert d["mime_type"] == mime and d["status"] == "uploaded" and d["size_bytes"] > 0
        assert d["collection_name"] == "General" and d["uploaded_by_name"] == "Owner"
    assert by_name["report.pdf"]["title"] == "report"
    listed = (await owner.get(f"/orgs/{oid}/documents")).json()
    assert len(listed["items"]) == 5 and listed["next_cursor"] is None


async def test_client_supplied_content_type_and_filename_are_not_trusted(world: World) -> None:
    owner, oid, cid = await _org(world)
    r = await owner.client.post(
        f"/api/v1/orgs/{oid}/documents",
        data={"collection_id": cid},
        files=[("files", ("../../../etc/passwd.pdf", files.pdf("x"), "text/html"))],
        headers=owner.h(),
    )
    doc = r.json()[0]["document"]
    assert r.json()[0]["outcome"] == "created"
    assert doc["original_filename"] == "passwd.pdf" and doc["mime_type"] == "application/pdf"


async def test_storage_key_is_opaque_and_never_contains_the_filename(
    world: World, store: S3ObjectStore
) -> None:
    owner, oid, cid = await _org(world)
    r = await owner.upload(oid, cid, ("Confidential Salaries.pdf", files.pdf("s")))
    doc_id = r.json()[0]["document"]["id"]
    async with world.scoped_db(oid, owner.user_id) as s:
        key = (
            await s.scalar(select(Document.storage_key).where(Document.id == uuid.UUID(doc_id)))
        ) or ""
    assert key == f"org/{oid}/doc/{doc_id}"
    assert "Salaries" not in key and ".pdf" not in key
    assert await store.exists(key)


@pytest.mark.parametrize(
    ("name", "content", "code"),
    [
        ("evil.pdf", b"MZ\x90 not a pdf", "UNSUPPORTED_TYPE"),
        ("page.html", b"<html></html>", "UNSUPPORTED_TYPE"),
        ("macro.docx", files.xlsx("x"), "UNSUPPORTED_TYPE"),
        ("noext", files.pdf("x"), "UNSUPPORTED_TYPE"),
        ("bin.txt", b"a\x00b", "UNSUPPORTED_TYPE"),
        ("broken.docx", b"PK\x03\x04 junk", "CORRUPT_FILE"),
        ("empty.pdf", b"", "EMPTY_FILE"),
    ],
)
async def test_bad_files_are_rejected_per_file_without_failing_the_batch(
    world: World, name: str, content: bytes, code: str
) -> None:
    owner, oid, cid = await _org(world)
    r = await owner.upload(oid, cid, (name, content), ("good.pdf", files.pdf("good")))
    assert r.status_code == 200
    bad, good = r.json()
    assert bad["outcome"] == "rejected" and bad["error_code"] == code and bad["document"] is None
    assert good["outcome"] == "created"
    assert (
        len((await owner.get(f"/orgs/{oid}/documents")).json()["items"]) == 1
    )  # nothing stored for the bad one


async def test_size_and_count_limits(world: World, store: S3ObjectStore) -> None:
    world.settings = world.settings.model_copy(
        update={"max_upload_bytes": 2048, "max_files_per_upload": 3}
    )
    owner, oid, cid = await _org(world)
    big = files.pdf("x" * 5000)
    r = await owner.upload(oid, cid, ("big.pdf", big), ("small.pdf", files.pdf("s")))
    assert [x["error_code"] or x["outcome"] for x in r.json()] == ["FILE_TOO_LARGE", "created"]
    many = await owner.upload(oid, cid, *[(f"f{i}.pdf", files.pdf(str(i))) for i in range(4)])
    assert many.status_code == 422 and many.json()["code"] == "TOO_MANY_FILES"
    none = await owner.client.post(
        f"/api/v1/orgs/{oid}/documents", data={"collection_id": cid}, headers=owner.h()
    )
    assert none.status_code == 422
    assert (
        len(await store.list_keys(f"org/{oid}/")) == 1
    )  # only the small file ever reached storage


async def test_duplicates_are_detected_per_collection_only(world: World) -> None:
    owner, oid, cid = await _org(world)
    other = await world.collection(owner, oid, "Other")
    first = (await owner.upload(oid, cid, ("a.pdf", files.pdf("same")))).json()[0]
    again = (await owner.upload(oid, cid, ("renamed.pdf", files.pdf("same")))).json()[0]
    assert first["outcome"] == "created" and again["outcome"] == "duplicate"
    assert again["document"]["id"] == first["document"]["id"]  # points at the original
    elsewhere = (await owner.upload(oid, other, ("a.pdf", files.pdf("same")))).json()[0]
    assert (
        elsewhere["outcome"] == "created" and elsewhere["document"]["id"] != first["document"]["id"]
    )
    # deleting frees the slot
    await owner.delete(f"/orgs/{oid}/documents/{first['document']['id']}")
    reborn = (await owner.upload(oid, cid, ("a.pdf", files.pdf("same")))).json()[0]
    assert reborn["outcome"] == "created" and reborn["document"]["id"] != first["document"]["id"]


async def test_identical_bytes_in_two_workspaces_are_independent(world: World) -> None:
    a, b = await world.person("A"), await world.person("B")
    oa, ob = (await world.org(a, "A"))["id"], (await world.org(b, "B"))["id"]
    ra = (await a.upload(oa, await world.general(a, oa), ("x.pdf", files.pdf("shared")))).json()[0]
    rb = (await b.upload(ob, await world.general(b, ob), ("x.pdf", files.pdf("shared")))).json()[0]
    assert (
        ra["outcome"] == rb["outcome"] == "created"
    )  # no cross-tenant dedupe, no existence oracle
    assert ra["document"]["id"] != rb["document"]["id"]


async def test_simultaneous_identical_uploads_create_exactly_one_document(
    world: World, store: S3ObjectStore
) -> None:
    owner, oid, cid = await _org(world)
    results = await asyncio.gather(
        *(owner.upload(oid, cid, ("race.pdf", files.pdf("race"))) for _ in range(6))
    )
    outcomes = sorted(r.json()[0]["outcome"] for r in results)
    assert outcomes == ["created"] + ["duplicate"] * 5
    assert len((await owner.get(f"/orgs/{oid}/documents")).json()["items"]) == 1
    assert len(await store.list_keys(f"org/{oid}/")) == 1  # no orphaned objects from the losers


async def test_storage_outage_fails_cleanly_and_leaves_nothing_behind(world: World) -> None:
    world.settings = world.settings.model_copy(update={"s3_endpoint": "http://127.0.0.1:1"})
    owner, oid, cid = await _org(world)
    r = await owner.upload(oid, cid, ("a.pdf", files.pdf("a")))
    assert r.status_code == 503 and r.json()["code"] == "STORAGE_UNAVAILABLE"
    assert r.headers["retry-after"]
    assert (await owner.get(f"/orgs/{oid}/documents")).json()["items"] == []


async def test_a_database_failure_after_the_object_was_stored_cleans_the_object_up(
    world: World, store: S3ObjectStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, oid, cid = await _org(world)

    def boom(_: str) -> str:
        raise RuntimeError("simulated failure after the object was stored")

    monkeypatch.setattr(validation, "title_from", boom)
    with pytest.raises(RuntimeError):
        await owner.upload(oid, cid, ("a.pdf", files.pdf("a")))
    assert await store.list_keys(f"org/{oid}/") == []  # no object without a row
    assert (await owner.get(f"/orgs/{oid}/documents")).json()["items"] == []


async def test_uploading_to_an_unknown_collection_or_with_a_bad_id(world: World) -> None:
    owner, oid, _ = await _org(world)
    assert (
        await owner.upload(oid, str(uuid.uuid4()), ("a.pdf", files.pdf("a")))
    ).status_code == 404
    r = await owner.client.post(
        f"/api/v1/orgs/{oid}/documents",
        data={"collection_id": "nope"},
        files=[("files", ("a.pdf", files.pdf("a"), "application/pdf"))],
        headers=owner.h(),
    )
    assert r.status_code == 422


# =============================================================== list / get


async def test_pagination_filters_and_search(world: World) -> None:
    owner, oid, cid = await _org(world)
    second = await world.collection(owner, oid, "Second")
    for i in range(5):
        await owner.upload(oid, cid, (f"doc-{i}.pdf", files.pdf(f"doc{i}")))
    await owner.upload(oid, second, ("100%_done.txt", files.text_file("pct")))
    await owner.upload(oid, second, ("another.txt", files.text_file("another")))
    page1 = (await owner.get(f"/orgs/{oid}/documents?limit=3")).json()
    assert len(page1["items"]) == 3 and page1["next_cursor"]
    page2 = (await owner.get(f"/orgs/{oid}/documents?limit=3&cursor={page1['next_cursor']}")).json()
    page3 = (await owner.get(f"/orgs/{oid}/documents?limit=3&cursor={page2['next_cursor']}")).json()
    ids = [d["id"] for p in (page1, page2, page3) for d in p["items"]]
    assert (
        len(ids) == 7 and len(set(ids)) == 7 and page3["next_cursor"] is None
    )  # no gaps, no repeats
    names = [d["original_filename"] for p in (page1, page2, page3) for d in p["items"]]
    assert names[0] == "another.txt" and names[-1] == "doc-0.pdf"  # newest first
    only = (await owner.get(f"/orgs/{oid}/documents?collection_id={second}")).json()["items"]
    assert {d["collection_name"] for d in only} == {"Second"} and len(only) == 2
    assert [
        d["original_filename"]
        for d in (await owner.get(f"/orgs/{oid}/documents?q=doc-3")).json()["items"]
    ] == ["doc-3.pdf"]
    # LIKE wildcards in the search term are literal, not patterns
    assert [
        d["original_filename"]
        for d in (await owner.get(f"/orgs/{oid}/documents?q=%25_")).json()["items"]
    ] == ["100%_done.txt"]
    assert (await owner.get(f"/orgs/{oid}/documents?q=%25")).json()["items"][0][
        "original_filename"
    ] == "100%_done.txt"
    assert (await owner.get(f"/orgs/{oid}/documents?status=ready")).json()["items"] == []
    assert (
        len((await owner.get(f"/orgs/{oid}/documents?status=uploaded&limit=100")).json()["items"])
        == 7
    )


@pytest.mark.parametrize(
    "query", ["limit=0", "limit=101", "cursor=garbage!!", "collection_id=nope"]
)
async def test_list_parameters_are_validated(world: World, query: str) -> None:
    owner, oid, _ = await _org(world)
    assert (await owner.get(f"/orgs/{oid}/documents?{query}")).status_code == 422


async def test_get_one_document(world: World) -> None:
    owner, oid, cid = await _org(world)
    doc = (await owner.upload(oid, cid, ("a.pdf", files.pdf("a")))).json()[0]["document"]
    assert (await owner.get(f"/orgs/{oid}/documents/{doc['id']}")).json()["id"] == doc["id"]
    assert (await owner.get(f"/orgs/{oid}/documents/{uuid.uuid4()}")).status_code == 404


# =============================================================== download


async def test_download_round_trip_and_safe_headers(world: World) -> None:
    owner, oid, cid = await _org(world)
    content = files.pdf("round trip " + "x" * 200_000)
    doc = (await owner.upload(oid, cid, ("عقد الإيجار.pdf", content))).json()[0]["document"]
    r = await owner.get(f"/orgs/{oid}/documents/{doc['id']}/file")
    assert r.status_code == 200 and r.content == content  # bytes survive the S3 round trip
    h = r.headers
    assert h["content-type"] == "application/pdf"
    assert (
        h["content-disposition"].startswith("inline;")
        and "filename*=UTF-8''" in h["content-disposition"]
    )
    assert h["x-content-type-options"] == "nosniff"
    assert "sandbox" in h["content-security-policy"]
    assert h["cache-control"] == "private, no-store"
    assert int(h["content-length"]) == len(content)
    forced = await owner.get(f"/orgs/{oid}/documents/{doc['id']}/file?download=true")
    assert forced.headers["content-disposition"].startswith("attachment;")


async def test_only_pdfs_may_render_inline(world: World) -> None:
    owner, oid, cid = await _org(world)
    for name, (content, mime) in SAMPLES.items():
        doc = (await owner.upload(oid, cid, (name, content))).json()[0]["document"]
        r = await owner.get(f"/orgs/{oid}/documents/{doc['id']}/file")
        assert r.status_code == 200 and r.content == content
        inline = r.headers["content-disposition"].startswith("inline;")
        assert inline is (mime == "application/pdf"), name
        if name.endswith(".md"):
            assert r.headers["content-type"].startswith("text/plain")  # never rendered as markup


# =============================================================== delete


async def test_delete_removes_the_object_and_hides_the_document(
    world: World, store: S3ObjectStore
) -> None:
    owner, oid, cid = await _org(world)
    doc = (await owner.upload(oid, cid, ("a.pdf", files.pdf("a")))).json()[0]["document"]
    key = f"org/{oid}/doc/{doc['id']}"
    assert await store.exists(key)
    assert (await owner.delete(f"/orgs/{oid}/documents/{doc['id']}")).status_code == 204
    assert not await store.exists(key)
    assert (await owner.get(f"/orgs/{oid}/documents/{doc['id']}")).status_code == 404
    assert (await owner.get(f"/orgs/{oid}/documents/{doc['id']}/file")).status_code == 404
    assert (await owner.get(f"/orgs/{oid}/documents")).json()["items"] == []
    assert (await owner.delete(f"/orgs/{oid}/documents/{doc['id']}")).status_code == 404
    async with world.scoped_db(
        oid, owner.user_id
    ) as s:  # the row is kept (soft delete) and marked purged
        row = await s.scalar(select(Document).where(Document.id == uuid.UUID(doc["id"])))
        assert row is not None and row.deleted_at is not None and row.purged_at is not None


async def test_deleting_a_workspace_deletes_its_files_and_nothing_else(
    world: World, store: S3ObjectStore
) -> None:
    owner, oid, cid = await _org(world)
    keep = await world.person("Keep")
    kept_org = (await world.org(keep, "Keep"))["id"]
    await owner.upload(oid, cid, ("a.pdf", files.pdf("a")), ("b.pdf", files.pdf("b")))
    await keep.upload(kept_org, await world.general(keep, kept_org), ("k.pdf", files.pdf("k")))
    assert len(await store.list_keys(f"org/{oid}/")) == 2
    assert (await owner.delete(f"/orgs/{oid}")).status_code == 204
    assert await store.list_keys(f"org/{oid}/") == []
    assert len(await store.list_keys(f"org/{kept_org}/")) == 1  # another tenant's files untouched
