from tests import files
from tests.tenancy_helpers import World


async def _setup(world: World):  # type: ignore[no-untyped-def]
    owner = await world.person("Owner")
    org = await world.org(owner, "Acme")
    return owner, org["id"]


async def test_every_workspace_starts_with_a_general_collection(world: World) -> None:
    owner, oid = await _setup(world)
    cols = (await owner.get(f"/orgs/{oid}/collections")).json()
    assert [(c["name"], c["visibility"], c["document_count"]) for c in cols] == [
        ("General", "org", 0)
    ]
    assert cols[0]["can_upload"] is True and cols[0]["member_count"] == 0


async def test_only_admins_manage_collections(world: World) -> None:
    owner, oid = await _setup(world)
    admin, editor = await world.person("Admin"), await world.person("Ed")
    await world.join(owner, oid, admin, "admin")
    await world.join(owner, oid, editor, "editor")
    assert (await editor.post(f"/orgs/{oid}/collections", {"name": "Nope"})).status_code == 403
    r = await admin.post(
        f"/orgs/{oid}/collections", {"name": "  Finance  ", "description": "Budgets"}
    )
    assert (
        r.status_code == 201 and r.json()["name"] == "Finance" and r.json()["visibility"] == "org"
    )
    cid = r.json()["id"]
    assert (await editor.patch(f"/orgs/{oid}/collections/{cid}", {"name": "x"})).status_code == 403
    assert (await editor.delete(f"/orgs/{oid}/collections/{cid}")).status_code == 403
    assert (
        await editor.put(f"/orgs/{oid}/collections/{cid}/members", {"user_ids": []})
    ).status_code == 403
    assert (await editor.get(f"/orgs/{oid}/collections/{cid}/members")).status_code == 403
    # members see counts only as far as their role allows
    seen = {c["name"]: c for c in (await editor.get(f"/orgs/{oid}/collections")).json()}
    assert seen["Finance"]["member_count"] is None and seen["Finance"]["can_upload"] is True


async def test_names_are_unique_case_insensitively_and_validated(world: World) -> None:
    owner, oid = await _setup(world)
    assert (await owner.post(f"/orgs/{oid}/collections", {"name": "general"})).status_code == 409
    r = await owner.post(f"/orgs/{oid}/collections", {"name": "HR"})
    assert r.status_code == 201
    dup = await owner.patch(f"/orgs/{oid}/collections/{r.json()['id']}", {"name": "GENERAL"})
    assert dup.status_code == 409 and dup.json()["code"] == "NAME_TAKEN"
    for bad in (
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 101},
        {"name": "ok", "visibility": "secret"},
        {"name": "ok", "organization_id": oid},
    ):
        assert (await owner.post(f"/orgs/{oid}/collections", bad)).status_code == 422
    # the same name in ANOTHER workspace is fine
    other = await world.person("Other")
    o2 = await world.org(other, "Else")
    assert (await other.post(f"/orgs/{o2['id']}/collections", {"name": "HR"})).status_code == 201


async def test_restricted_collections_are_invisible_to_unlisted_members(world: World) -> None:
    owner, oid = await _setup(world)
    listed, unlisted = await world.person("Listed"), await world.person("Unlisted")
    await world.join(owner, oid, listed, "member")
    await world.join(owner, oid, unlisted, "member")
    cid = await world.collection(owner, oid, "Board", "restricted", members=[listed.user_id])
    for person, sees in ((owner, True), (listed, True), (unlisted, False)):
        names = [c["name"] for c in (await person.get(f"/orgs/{oid}/collections")).json()]
        assert ("Board" in names) is sees, person.name
    assert (await unlisted.patch(f"/orgs/{oid}/collections/{cid}", {"name": "x"})).status_code in (
        403,
        404,
    )
    # the unlisted member cannot even learn the collection exists through documents
    r = await owner.upload(oid, cid, ("secret.pdf", files.pdf("secret")))
    assert r.status_code == 200
    assert (await unlisted.get(f"/orgs/{oid}/documents?collection_id={cid}")).json()["items"] == []


async def test_membership_list_rules(world: World) -> None:
    owner, oid = await _setup(world)
    a, b, outsider = await world.person("A"), await world.person("B"), await world.person("Out")
    await world.join(owner, oid, a, "member")
    await world.join(owner, oid, b, "viewer")
    open_id = await world.general(owner, oid)
    r = await owner.put(f"/orgs/{oid}/collections/{open_id}/members", {"user_ids": [a.user_id]})
    assert r.status_code == 409 and r.json()["code"] == "NOT_RESTRICTED"
    cid = await world.collection(owner, oid, "Secret", "restricted")
    ok = await owner.put(
        f"/orgs/{oid}/collections/{cid}/members", {"user_ids": [a.user_id, a.user_id, b.user_id]}
    )
    assert ok.status_code == 200 and {m["user_id"] for m in ok.json()} == {
        a.user_id,
        b.user_id,
    }  # deduplicated
    assert all(m["email"] for m in ok.json())
    bad = await owner.put(
        f"/orgs/{oid}/collections/{cid}/members", {"user_ids": [a.user_id, outsider.user_id]}
    )
    assert (
        bad.status_code == 422 and bad.json()["code"] == "NOT_ORG_MEMBER"
    )  # not in this workspace
    still = (await owner.get(f"/orgs/{oid}/collections/{cid}/members")).json()
    assert {m["user_id"] for m in still} == {
        a.user_id,
        b.user_id,
    }  # a failed update changes nothing
    cleared = await owner.put(f"/orgs/{oid}/collections/{cid}/members", {"user_ids": []})
    assert cleared.json() == []
    assert (
        await owner.put(f"/orgs/{oid}/collections/{cid}/members", {"user_ids": ["not-a-uuid"]})
    ).status_code == 422


async def test_opening_a_collection_forgets_its_old_member_list(world: World) -> None:
    owner, oid = await _setup(world)
    a = await world.person("A")
    await world.join(owner, oid, a, "member")
    cid = await world.collection(owner, oid, "Temp", "restricted", members=[a.user_id])
    await owner.patch(f"/orgs/{oid}/collections/{cid}", {"visibility": "org"})
    await owner.patch(f"/orgs/{oid}/collections/{cid}", {"visibility": "restricted"})
    assert (
        await owner.get(f"/orgs/{oid}/collections/{cid}/members")
    ).json() == []  # nothing resurfaces
    assert "Temp" not in [c["name"] for c in (await a.get(f"/orgs/{oid}/collections")).json()]


async def test_delete_collection_rules(world: World) -> None:
    owner, oid = await _setup(world)
    cid = await world.collection(owner, oid, "Scratch")
    up = await owner.upload(oid, cid, ("a.pdf", files.pdf("a")))
    doc_id = up.json()[0]["document"]["id"]
    r = await owner.delete(f"/orgs/{oid}/collections/{cid}")
    assert r.status_code == 409 and r.json()["code"] == "COLLECTION_NOT_EMPTY"
    assert (await owner.delete(f"/orgs/{oid}/documents/{doc_id}")).status_code == 204
    assert (await owner.delete(f"/orgs/{oid}/collections/{cid}")).status_code == 204
    assert cid not in [c["id"] for c in (await owner.get(f"/orgs/{oid}/collections")).json()]
    assert (await owner.delete(f"/orgs/{oid}/collections/{cid}")).status_code == 404


async def test_document_and_member_counts(world: World) -> None:
    owner, oid = await _setup(world)
    cid = await world.general(owner, oid)
    await owner.upload(oid, cid, ("a.pdf", files.pdf("a")), ("b.txt", files.text_file("b")))
    general = next(
        c for c in (await owner.get(f"/orgs/{oid}/collections")).json() if c["id"] == cid
    )
    assert general["document_count"] == 2
