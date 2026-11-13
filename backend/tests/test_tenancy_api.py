import asyncio
import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.modules.tenancy.models import Invitation
from tests.tenancy_helpers import V1, World

# ======================================================================= basics


async def test_create_org_makes_the_creator_owner(world: World) -> None:
    ana = await world.person("Ana")
    org = await world.org(ana, "Acme  Logistics ")
    assert org["role"] == "owner" and org["name"] == "Acme Logistics"
    assert re.fullmatch(r"acme-logistics-[0-9a-f]{6}", org["slug"])
    listed = (await ana.get("/orgs")).json()
    assert [o["id"] for o in listed] == [org["id"]]


async def test_arabic_names_get_a_safe_ascii_slug(world: World) -> None:
    ana = await world.person("Ana")
    org = await world.org(ana, "شركة هالدن")
    assert org["name"] == "شركة هالدن"
    assert re.fullmatch(r"workspace-[0-9a-f]{6}", org["slug"])


async def test_org_creation_is_capped_per_user(world: World) -> None:
    world.settings = world.settings.model_copy(update={"max_owned_orgs_per_user": 2})
    ana = await world.person("Ana")
    await world.org(ana, "One")
    await world.org(ana, "Two")
    r = await ana.post("/orgs", {"name": "Three"})
    assert r.status_code == 409 and r.json()["code"] == "ORG_LIMIT_REACHED"


async def test_org_name_validation(world: World) -> None:
    ana = await world.person("Ana")
    for bad in ({"name": ""}, {"name": "   "}, {"name": "x" * 101}, {"name": "ok", "slug": "evil"}):
        assert (await ana.post("/orgs", bad)).status_code == 422


async def test_listing_shows_only_my_own_orgs_with_my_role(world: World) -> None:
    ana, ben = await world.person("Ana"), await world.person("Ben")
    a = await world.org(ana, "A")
    await world.org(ben, "B")
    await world.join(ana, a["id"], ben, "viewer")
    mine = {o["name"]: o["role"] for o in (await ben.get("/orgs")).json()}
    assert mine == {"A": "viewer", "B": "owner"}
    assert {o["name"] for o in (await ana.get("/orgs")).json()} == {"A"}


async def test_unauthenticated_requests_are_rejected(world: World) -> None:
    ana = await world.person("Ana")
    org = await world.org(ana)
    ana.client.cookies.clear()
    for method, path in (
        ("GET", "/orgs"),
        ("GET", f"/orgs/{org['id']}"),
        ("GET", f"/orgs/{org['id']}/members"),
    ):
        r = await ana.client.request(method, f"{V1}{path}")
        assert r.status_code == 401, path


# ======================================================================= update / delete


async def test_update_and_delete_follow_roles(world: World) -> None:
    owner, admin, member = (
        await world.person("Owner"),
        await world.person("Admin"),
        await world.person("Mem"),
    )
    org = await world.org(owner)
    await world.join(owner, org["id"], admin, "admin")
    await world.join(owner, org["id"], member, "member")
    oid = org["id"]
    assert (await member.patch(f"/orgs/{oid}", {"name": "Nope"})).status_code == 403
    assert (await admin.patch(f"/orgs/{oid}", {"name": "Renamed"})).json()["name"] == "Renamed"
    assert (await admin.delete(f"/orgs/{oid}")).status_code == 403  # owner only
    assert (await member.delete(f"/orgs/{oid}")).status_code == 403
    assert (await owner.delete(f"/orgs/{oid}")).status_code == 204
    for p in (owner, admin, member):
        assert (await p.get(f"/orgs/{oid}")).status_code == 404
    assert (await admin.get("/orgs")).json() == []


# ======================================================================= members


async def test_member_emails_are_visible_to_admins_only(world: World) -> None:
    owner, viewer = await world.person("Owner"), await world.person("View")
    org = await world.org(owner)
    await world.join(owner, org["id"], viewer, "viewer")
    seen_by_owner = (await owner.get(f"/orgs/{org['id']}/members")).json()
    seen_by_viewer = (await viewer.get(f"/orgs/{org['id']}/members")).json()
    assert all(m["email"] for m in seen_by_owner)
    assert len(seen_by_viewer) == 2 and all(m["email"] is None for m in seen_by_viewer)
    assert {m["display_name"] for m in seen_by_viewer} == {"Owner", "View"}


async def test_role_changes_follow_the_hierarchy(world: World) -> None:
    owner, admin, editor = (
        await world.person("Owner"),
        await world.person("Admin"),
        await world.person("Ed"),
    )
    org = await world.org(owner)
    oid = org["id"]
    await world.join(owner, oid, admin, "admin")
    await world.join(owner, oid, editor, "editor")
    owner_m = await world.member_id(owner, oid, owner.user_id)
    admin_m = await world.member_id(owner, oid, admin.user_id)
    editor_m = await world.member_id(owner, oid, editor.user_id)

    ok = await admin.patch(f"/orgs/{oid}/members/{editor_m}", {"role": "member"})
    assert ok.status_code == 200 and ok.json()["role"] == "member"
    for body in ({"role": "owner"},):  # admins cannot mint owners
        r = await admin.patch(f"/orgs/{oid}/members/{editor_m}", body)
        assert r.status_code == 403 and r.json()["code"] == "OWNER_PROTECTED"
    r = await admin.patch(f"/orgs/{oid}/members/{owner_m}", {"role": "member"})  # nor touch owners
    assert r.status_code == 403 and r.json()["code"] == "OWNER_PROTECTED"
    r = await admin.patch(
        f"/orgs/{oid}/members/{admin_m}", {"role": "owner"}
    )  # nor promote themselves
    assert r.status_code == 403
    assert (
        await editor.patch(f"/orgs/{oid}/members/{editor_m}", {"role": "admin"})
    ).status_code == 403
    assert (
        await owner.patch(f"/orgs/{oid}/members/{editor_m}", {"role": "owner"})
    ).status_code == 200


async def test_unknown_roles_and_extra_fields_are_rejected(world: World) -> None:
    owner = await world.person("Owner")
    org = await world.org(owner)
    m = await world.member_id(owner, org["id"], owner.user_id)
    for body in (
        {"role": "root"},
        {"role": "owner", "organization_id": org["id"]},
        {"user_id": "x"},
        {},
    ):
        assert (await owner.patch(f"/orgs/{org['id']}/members/{m}", body)).status_code == 422


async def test_last_owner_cannot_leave_or_be_demoted(world: World) -> None:
    owner, other = await world.person("Owner"), await world.person("Other")
    org = await world.org(owner)
    oid = org["id"]
    await world.join(owner, oid, other, "admin")
    mine = await world.member_id(owner, oid, owner.user_id)
    r = await owner.patch(f"/orgs/{oid}/members/{mine}", {"role": "admin"})
    assert r.status_code == 409 and r.json()["code"] == "LAST_OWNER"
    r = await owner.delete(f"/orgs/{oid}/members/{mine}")
    assert r.status_code == 409 and r.json()["code"] == "LAST_OWNER"
    # with a second owner, the first may step down and leave
    other_m = await world.member_id(owner, oid, other.user_id)
    assert (
        await owner.patch(f"/orgs/{oid}/members/{other_m}", {"role": "owner"})
    ).status_code == 200
    assert (await owner.patch(f"/orgs/{oid}/members/{mine}", {"role": "member"})).status_code == 200
    assert (
        await other.delete(f"/orgs/{oid}/members/{other_m}")
    ).status_code == 409  # now they are last


async def test_two_owners_cannot_demote_each_other_simultaneously(world: World) -> None:
    a, b = await world.person("A"), await world.person("B")
    org = await world.org(a)
    oid = org["id"]
    await world.join(a, oid, b, "admin")
    await a.patch(
        f"/orgs/{oid}/members/{await world.member_id(a, oid, b.user_id)}", {"role": "owner"}
    )
    a_m, b_m = await world.member_id(a, oid, a.user_id), await world.member_id(a, oid, b.user_id)
    results = await asyncio.gather(
        a.patch(f"/orgs/{oid}/members/{b_m}", {"role": "viewer"}),
        b.patch(f"/orgs/{oid}/members/{a_m}", {"role": "viewer"}),
    )
    assert sorted(r.status_code for r in results) == [200, 409]
    survivors = [p for p, r in zip((a, b), results, strict=True) if r.status_code == 409]
    members = (await survivors[0].get(f"/orgs/{oid}/members")).json()
    assert [m["role"] for m in members].count("owner") == 1


async def test_admin_can_remove_members_but_not_owners_and_anyone_can_leave(world: World) -> None:
    owner, admin, mem = (
        await world.person("Owner"),
        await world.person("Admin"),
        await world.person("Mem"),
    )
    org = await world.org(owner)
    oid = org["id"]
    await world.join(owner, oid, admin, "admin")
    await world.join(owner, oid, mem, "member")
    owner_m = await world.member_id(owner, oid, owner.user_id)
    mem_m = await world.member_id(owner, oid, mem.user_id)
    r = await admin.delete(f"/orgs/{oid}/members/{owner_m}")
    assert r.status_code == 403 and r.json()["code"] == "OWNER_PROTECTED"
    other_member = await world.person("Other")
    await world.join(owner, oid, other_member, "viewer")
    om = await world.member_id(owner, oid, other_member.user_id)
    assert (
        await mem.delete(f"/orgs/{oid}/members/{om}")
    ).status_code == 403  # members cannot remove others
    assert (await mem.delete(f"/orgs/{oid}/members/{mem_m}")).status_code == 204  # but can leave
    assert (await mem.get(f"/orgs/{oid}")).status_code == 404  # access ends immediately
    assert (await admin.delete(f"/orgs/{oid}/members/{om}")).status_code == 204


async def test_removed_member_loses_access_with_a_still_valid_session(world: World) -> None:
    owner, mem = await world.person("Owner"), await world.person("Mem")
    org = await world.org(owner)
    await world.join(owner, org["id"], mem, "member")
    assert (await mem.get(f"/orgs/{org['id']}")).status_code == 200
    mid = await world.member_id(owner, org["id"], mem.user_id)
    await owner.delete(f"/orgs/{org['id']}/members/{mid}")
    assert (await mem.get(f"/orgs/{org['id']}")).status_code == 404
    assert (await mem.get(f"/orgs/{org['id']}/members")).status_code == 404


# ======================================================================= invitations


async def test_invitation_flow_end_to_end(world: World) -> None:
    owner, guest = await world.person("Owner"), await world.person("Guest")
    org = await world.org(owner, "Acme")
    r = await owner.post(
        f"/orgs/{org['id']}/invitations", {"email": guest.email, "role": "editor", "locale": "ar"}
    )
    assert r.status_code == 201
    msg = world.outbox.messages[-1]
    assert msg["to"] == guest.email and "/ar/accept-invite#token=" in msg["body"]
    assert "?token=" not in msg["body"] and "Acme" in msg["subject"]
    assert "token" not in str(r.json()) and "hash" not in str(r.json())  # never echoed back
    pending = (await owner.get(f"/orgs/{org['id']}/invitations")).json()
    assert [i["email"] for i in pending] == [guest.email]
    accepted = await guest.post("/invitations/accept", {"token": world.outbox.last_token()})
    assert accepted.status_code == 200 and accepted.json()["role"] == "editor"
    assert (await owner.get(f"/orgs/{org['id']}/invitations")).json() == []
    assert (await guest.get(f"/orgs/{org['id']}")).json()["role"] == "editor"


async def test_invitation_can_only_be_used_once(world: World) -> None:
    owner, guest = await world.person("Owner"), await world.person("Guest")
    org = await world.org(owner)
    await owner.post(f"/orgs/{org['id']}/invitations", {"email": guest.email, "role": "member"})
    token = world.outbox.last_token()
    assert (await guest.post("/invitations/accept", {"token": token})).status_code == 200
    again = await guest.post("/invitations/accept", {"token": token})
    assert again.status_code == 400 and again.json()["code"] == "INVALID_INVITATION"


async def test_invitation_for_another_email_is_refused_and_not_consumed(world: World) -> None:
    owner, guest, intruder = (
        await world.person("Owner"),
        await world.person("Guest"),
        await world.person("Mal"),
    )
    org = await world.org(owner)
    await owner.post(f"/orgs/{org['id']}/invitations", {"email": guest.email, "role": "admin"})
    token = world.outbox.last_token()
    r = await intruder.post("/invitations/accept", {"token": token})
    assert r.status_code == 400 and r.json()["code"] == "INVALID_INVITATION"
    assert (await intruder.get(f"/orgs/{org['id']}")).status_code == 404
    assert (
        await guest.post("/invitations/accept", {"token": token})
    ).status_code == 200  # still valid


async def test_invalid_expired_revoked_and_replaced_invitations(world: World) -> None:
    owner, guest = await world.person("Owner"), await world.person("Guest")
    org = await world.org(owner)
    oid = org["id"]
    for token in ("x" * 43, "not-a-real-token-but-long-enough-12345"):
        r = await guest.post("/invitations/accept", {"token": token})
        assert r.status_code == 400 and r.json()["code"] == "INVALID_INVITATION"
    assert (await guest.post("/invitations/accept", {"token": "short"})).status_code == 422

    await owner.post(f"/orgs/{oid}/invitations", {"email": guest.email, "role": "member"})
    first = world.outbox.last_token()
    await owner.post(
        f"/orgs/{oid}/invitations", {"email": guest.email, "role": "viewer"}
    )  # replaces
    second = world.outbox.last_token()
    assert (await guest.post("/invitations/accept", {"token": first})).status_code == 400
    inv_id = (await owner.get(f"/orgs/{oid}/invitations")).json()[0]["id"]
    assert (await owner.delete(f"/orgs/{oid}/invitations/{inv_id}")).status_code == 204
    assert (
        await guest.post("/invitations/accept", {"token": second})
    ).status_code == 400  # revoked

    await owner.post(f"/orgs/{oid}/invitations", {"email": guest.email, "role": "member"})
    third = world.outbox.last_token()
    async with world.scoped_db(oid, owner.user_id) as s:
        await s.execute(
            update(Invitation).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await s.commit()
    r = await guest.post("/invitations/accept", {"token": third})
    assert r.status_code == 400 and r.json()["code"] == "INVALID_INVITATION"


async def test_invitation_rules(world: World) -> None:
    owner = await world.person("Owner")
    admin = await world.person("Admin")
    mem = await world.person("Mem")
    guest = await world.person("Guest")
    org = await world.org(owner)
    oid = org["id"]
    await world.join(owner, oid, admin, "admin")
    await world.join(owner, oid, mem, "member")
    body = {"email": guest.email, "role": "member"}
    assert (await mem.post(f"/orgs/{oid}/invitations", body)).status_code == 403
    assert (await mem.get(f"/orgs/{oid}/invitations")).status_code == 403
    assert (
        await admin.post(f"/orgs/{oid}/invitations", {**body, "role": "admin"})
    ).status_code == 201
    for bad_role in ("owner", "root"):
        r = await owner.post(f"/orgs/{oid}/invitations", {**body, "role": bad_role})
        assert r.status_code == 422  # owners are promoted, never invited
    r = await owner.post(f"/orgs/{oid}/invitations", {"email": mem.email, "role": "viewer"})
    assert r.status_code == 409 and r.json()["code"] == "ALREADY_MEMBER"
    assert (
        await owner.post(f"/orgs/{oid}/invitations", {"email": "not-an-email", "role": "viewer"})
    ).status_code == 422


async def test_existing_member_cannot_be_escalated_by_accepting_an_invitation(world: World) -> None:
    owner, mem = await world.person("Owner"), await world.person("Mem")
    org = await world.org(owner)
    oid = org["id"]
    await world.join(owner, oid, mem, "viewer")
    # an invitation created before they joined (simulated by revoking membership then re-adding)
    async with world.scoped_db(oid, owner.user_id) as s:
        s.add(
            Invitation(
                organization_id=uuid.UUID(oid),
                email=mem.email,
                role="admin",
                token_hash=hashlib.sha256(b"stale-invite-token-0123456789abc").hexdigest(),
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
        await s.commit()
    r = await mem.post("/invitations/accept", {"token": "stale-invite-token-0123456789abc"})
    assert r.status_code == 200 and r.json()["role"] == "viewer"  # role unchanged
