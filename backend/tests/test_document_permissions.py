"""Document permission matrix: role x collection visibility x membership x operation.

Expectations are written out by hand from the rules in PLAN.md section 2 (not derived from the
implementation): editors and above write; every role reads; restricted collections are visible to
their listed members and to owners/admins only; inaccessible things answer 404, never 403.
"""

import uuid
from dataclasses import dataclass

import pytest

from tests import files
from tests.tenancy_helpers import Person, World

ROLES = ["owner", "admin", "editor", "member", "viewer"]
WRITERS = {"owner", "admin", "editor"}


@dataclass
class Cast:
    oid: str
    people: dict[str, Person]  # key: "owner", "admin", "editor_listed", "editor_unlisted", ...
    collections: dict[str, str]  # "org" | "restricted" -> collection id
    docs: dict[
        tuple[str, str], str
    ]  # (person key, collection key) -> a document to delete in that cell


def can_access(person_key: str, collection_key: str) -> bool:
    if collection_key == "org":
        return True
    role = person_key.split("_")[0]
    return role in ("owner", "admin") or person_key.endswith("_listed")


@pytest.fixture
async def cast(world: World) -> Cast:
    owner = await world.person("Owner")
    oid = (await world.org(owner, "Acme"))["id"]
    people: dict[str, Person] = {"owner": owner}
    listed_ids: list[str] = []
    for role in ("admin", "editor", "member", "viewer"):
        variants = ("",) if role == "admin" else ("_listed", "_unlisted")
        for v in variants:
            p = await world.person(f"{role}{v}")
            await world.join(owner, oid, p, role)
            people[f"{role}{v}"] = p
            if v == "_listed":
                listed_ids.append(p.user_id)
    collections = {
        "org": await world.general(owner, oid),
        "restricted": await world.collection(
            owner, oid, "Restricted", "restricted", members=listed_ids
        ),
    }
    docs: dict[tuple[str, str], str] = {}
    n = 0
    for pk in people:
        for ck, cid in collections.items():
            n += 1
            r = await owner.upload(oid, cid, (f"seed-{n}.pdf", files.pdf(f"seed {n}")))
            docs[(pk, ck)] = r.json()[0]["document"]["id"]
    return Cast(oid, people, collections, docs)


def _label(pk: str, ck: str) -> str:
    return f"{pk}->{ck}"


async def test_read_operations_follow_collection_access(cast: Cast) -> None:
    """list, get and download: allowed exactly when the caller can access the collection."""
    for pk, person in cast.people.items():
        for ck, cid in cast.collections.items():
            allowed = can_access(pk, ck)
            some_doc = cast.docs[("owner", ck)]
            listed = (
                await person.get(f"/orgs/{cast.oid}/documents?collection_id={cid}&limit=100")
            ).json()["items"]
            assert bool(listed) is allowed, f"list {_label(pk, ck)}"
            got = await person.get(f"/orgs/{cast.oid}/documents/{some_doc}")
            assert got.status_code == (200 if allowed else 404), (
                f"get {_label(pk, ck)} -> {got.status_code}"
            )
            dl = await person.get(f"/orgs/{cast.oid}/documents/{some_doc}/file")
            assert dl.status_code == (200 if allowed else 404), (
                f"download {_label(pk, ck)} -> {dl.status_code}"
            )
            if allowed:
                assert dl.content.startswith(b"%PDF-")
            else:
                assert b"%PDF" not in dl.content  # the body of a refusal carries no file content


async def test_unfiltered_listing_never_includes_inaccessible_collections(cast: Cast) -> None:
    restricted_ids = {cast.docs[(pk, "restricted")] for pk in cast.people}
    for pk, person in cast.people.items():
        items = (await person.get(f"/orgs/{cast.oid}/documents?limit=100")).json()["items"]
        seen = {d["id"] for d in items}
        assert (restricted_ids <= seen) is can_access(pk, "restricted"), pk
        if not can_access(pk, "restricted"):
            assert not (restricted_ids & seen), f"{pk} sees a restricted document"
            assert "Restricted" not in {d["collection_name"] for d in items}
        cols = {c["name"] for c in (await person.get(f"/orgs/{cast.oid}/collections")).json()}
        assert ("Restricted" in cols) is can_access(pk, "restricted"), pk


async def test_upload_follows_role_then_collection_access(cast: Cast) -> None:
    for pk, person in cast.people.items():
        role = pk.split("_")[0]
        for ck, cid in cast.collections.items():
            r = await person.upload(
                cast.oid,
                cid,
                (f"new-{uuid.uuid4().hex[:6]}.txt", files.text_file(uuid.uuid4().hex)),
            )
            if role not in WRITERS:
                assert r.status_code == 403, f"upload {_label(pk, ck)} -> {r.status_code}"
            elif can_access(pk, ck):
                assert r.status_code == 200 and r.json()[0]["outcome"] == "created", (
                    f"upload {_label(pk, ck)}"
                )
            else:
                assert r.status_code == 404, f"upload {_label(pk, ck)} -> {r.status_code}"


async def test_delete_follows_role_then_collection_access(cast: Cast) -> None:
    for (pk, ck), doc_id in cast.docs.items():
        person = cast.people[pk]
        role = pk.split("_")[0]
        r = await person.delete(f"/orgs/{cast.oid}/documents/{doc_id}")
        if role not in WRITERS:
            assert r.status_code == 403, f"delete {_label(pk, ck)} -> {r.status_code}"
        elif can_access(pk, ck):
            assert r.status_code == 204, f"delete {_label(pk, ck)} -> {r.status_code}"
        else:
            assert r.status_code == 404, f"delete {_label(pk, ck)} -> {r.status_code}"
    # inaccessible deletes really did nothing: a restricted doc survived every unlisted editor/member/viewer
    owner = cast.people["owner"]
    for (pk, ck), doc_id in cast.docs.items():
        role = pk.split("_")[0]
        if role in WRITERS and can_access(pk, ck):
            assert (
                await owner.get(f"/orgs/{cast.oid}/documents/{doc_id}")
            ).status_code == 404  # deleted
        else:
            assert (
                await owner.get(f"/orgs/{cast.oid}/documents/{doc_id}")
            ).status_code == 200  # intact


async def test_revoking_access_takes_effect_immediately(world: World, cast: Cast) -> None:
    listed = cast.people["member_listed"]
    doc = cast.docs[("owner", "restricted")]
    cid = cast.collections["restricted"]
    owner = cast.people["owner"]
    assert (await listed.get(f"/orgs/{cast.oid}/documents/{doc}/file")).status_code == 200
    await owner.put(f"/orgs/{cast.oid}/collections/{cid}/members", {"user_ids": []})
    assert (await listed.get(f"/orgs/{cast.oid}/documents/{doc}/file")).status_code == 404
    assert (await listed.get(f"/orgs/{cast.oid}/documents/{doc}")).status_code == 404
    # granting again restores it
    await owner.put(f"/orgs/{cast.oid}/collections/{cid}/members", {"user_ids": [listed.user_id]})
    assert (await listed.get(f"/orgs/{cast.oid}/documents/{doc}")).status_code == 200


async def test_demoting_a_collection_member_to_viewer_keeps_read_but_removes_write(
    world: World, cast: Cast
) -> None:
    owner, editor = cast.people["owner"], cast.people["editor_listed"]
    cid = cast.collections["restricted"]
    r = await editor.upload(cast.oid, cid, ("w.txt", files.text_file("w")))
    assert r.status_code == 200
    mid = await world.member_id(owner, cast.oid, editor.user_id)
    await owner.patch(f"/orgs/{cast.oid}/members/{mid}", {"role": "viewer"})
    assert (
        await editor.upload(cast.oid, cid, ("w2.txt", files.text_file("w2")))
    ).status_code == 403
    assert (await editor.get(f"/orgs/{cast.oid}/documents?collection_id={cid}")).json()[
        "items"
    ]  # still reads


async def test_a_removed_workspace_member_loses_every_document(world: World, cast: Cast) -> None:
    owner, member = cast.people["owner"], cast.people["member_listed"]
    doc = cast.docs[("owner", "org")]
    assert (await member.get(f"/orgs/{cast.oid}/documents/{doc}/file")).status_code == 200
    mid = await world.member_id(owner, cast.oid, member.user_id)
    await owner.delete(f"/orgs/{cast.oid}/members/{mid}")
    for path in (f"/documents/{doc}", f"/documents/{doc}/file", "/documents", "/collections"):
        assert (await member.get(f"/orgs/{cast.oid}{path}")).status_code == 404, path
