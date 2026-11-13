"""Hand-written cross-tenant attack scenarios: changed IDs, guessed IDs, replayed tokens."""

import uuid
from datetime import UTC, datetime

from httpx import Response
from sqlalchemy import select

from app.modules.tenancy.models import Invitation, Membership
from tests.tenancy_helpers import Person, World

Scenario = tuple[Person, Person, Person, dict[str, str], dict[str, str]]


async def _two_orgs(world: World) -> Scenario:
    a_owner, a_member = await world.person("Alice"), await world.person("Amir")
    b_owner = await world.person("Bella")
    a = await world.org(a_owner, "Org A")
    b = await world.org(b_owner, "Org B")
    await world.join(a_owner, a["id"], a_member, "member")
    return a_owner, a_member, b_owner, a, b


def _strip(r: Response) -> dict[str, object]:
    return {k: v for k, v in r.json().items() if k != "request_id"}


async def test_member_ids_from_another_org_are_not_addressable_through_my_org(world: World) -> None:
    a_owner, a_member, b_owner, a, b = await _two_orgs(world)
    victim_membership = await world.member_id(a_owner, a["id"], a_member.user_id)
    # Bella is the owner of B and tries A's membership id through HER OWN org path
    for r in (
        await b_owner.patch(f"/orgs/{b['id']}/members/{victim_membership}", {"role": "viewer"}),
        await b_owner.delete(f"/orgs/{b['id']}/members/{victim_membership}"),
    ):
        assert r.status_code == 404
    still = (await a_owner.get(f"/orgs/{a['id']}/members")).json()
    assert {m["role"] for m in still} == {"owner", "member"}
    assert (await a_member.get(f"/orgs/{a['id']}")).status_code == 200


async def test_invitation_ids_from_another_org_are_not_addressable(world: World) -> None:
    a_owner, _, b_owner, a, b = await _two_orgs(world)
    await a_owner.post(f"/orgs/{a['id']}/invitations", {"email": "x@example.com", "role": "viewer"})
    inv = (await a_owner.get(f"/orgs/{a['id']}/invitations")).json()[0]["id"]
    r = await b_owner.delete(f"/orgs/{b['id']}/invitations/{inv}")
    assert r.status_code == 404
    assert len((await a_owner.get(f"/orgs/{a['id']}/invitations")).json()) == 1  # still pending


async def test_guessing_uuids_never_reveals_anything(world: World) -> None:
    _, _, b_owner, a, b = await _two_orgs(world)
    for _ in range(25):
        guess = str(uuid.uuid4())
        assert (await b_owner.get(f"/orgs/{guess}")).status_code == 404
        assert (
            await b_owner.get(f"/orgs/{b['id']}/members/{guess}")
        ).status_code == 405  # no such route
        assert (
            await b_owner.patch(f"/orgs/{b['id']}/members/{guess}", {"role": "admin"})
        ).status_code == 404
    # a real-but-foreign id answers exactly like a random one
    real = await b_owner.get(f"/orgs/{a['id']}")
    rand = await b_owner.get(f"/orgs/{uuid.uuid4()}")
    assert real.status_code == rand.status_code == 404
    assert _strip(real) == _strip(rand)


async def test_a_members_session_for_org_a_does_not_grant_org_b(world: World) -> None:
    _, a_member, _, a, b = await _two_orgs(world)
    assert (await a_member.get(f"/orgs/{a['id']}")).status_code == 200
    for path in (f"/orgs/{b['id']}", f"/orgs/{b['id']}/members", f"/orgs/{b['id']}/invitations"):
        assert (await a_member.get(path)).status_code == 404
    assert (
        await a_member.post(
            f"/orgs/{b['id']}/invitations", {"email": "z@example.com", "role": "viewer"}
        )
    ).status_code == 404
    assert (await a_member.delete(f"/orgs/{b['id']}")).status_code == 404


async def test_mass_assignment_cannot_smuggle_tenant_fields(world: World) -> None:
    a_owner, _, b_owner, a, b = await _two_orgs(world)
    mid = await world.member_id(b_owner, b["id"], b_owner.user_id)
    attempts = [
        (b_owner.patch(f"/orgs/{b['id']}", {"name": "ok", "id": a["id"]})),
        (b_owner.patch(f"/orgs/{b['id']}", {"name": "ok", "organization_id": a["id"]})),
        (
            b_owner.patch(
                f"/orgs/{b['id']}/members/{mid}", {"role": "owner", "organization_id": a["id"]}
            )
        ),
        (b_owner.post("/orgs", {"name": "n", "slug": "taken", "id": a["id"]})),
    ]
    for coro in attempts:
        assert (await coro).status_code == 422
    assert (await a_owner.get(f"/orgs/{a['id']}")).json()["name"] == "Org A"


async def test_invitation_tokens_do_not_cross_organizations(world: World) -> None:
    a_owner, _, b_owner, a, b = await _two_orgs(world)
    guest = await world.person("Guest")
    await a_owner.post(f"/orgs/{a['id']}/invitations", {"email": guest.email, "role": "admin"})
    token = world.outbox.last_token()
    mallory = await world.person("Mallory")
    # a stranger replaying a token, and a different org's owner replaying it: both refused
    for p in (mallory, b_owner):
        r = await p.post("/invitations/accept", {"token": token})
        assert r.status_code == 400 and r.json()["code"] == "INVALID_INVITATION"
    assert (await mallory.get(f"/orgs/{a['id']}")).status_code == 404
    # tampering with the token (flip one character) is just another invalid token
    flipped = token[:-1] + ("A" if token[-1] != "A" else "B")
    assert (await guest.post("/invitations/accept", {"token": flipped})).status_code == 400
    ok = await guest.post("/invitations/accept", {"token": token})
    assert ok.status_code == 200 and ok.json()["id"] == a["id"] and ok.json()["role"] == "admin"
    # the guest got org A only: nothing leaks into org B
    assert (await guest.get(f"/orgs/{b['id']}")).status_code == 404
    assert [o["id"] for o in (await guest.get("/orgs")).json()] == [a["id"]]


async def test_accepting_with_a_mismatched_email_creates_no_membership(world: World) -> None:
    a_owner, _, _, a, _ = await _two_orgs(world)
    guest, mallory = await world.person("Guest"), await world.person("Mallory")
    await a_owner.post(f"/orgs/{a['id']}/invitations", {"email": guest.email, "role": "member"})
    await mallory.post("/invitations/accept", {"token": world.outbox.last_token()})
    async with world.scoped_db(a["id"], a_owner.user_id) as s:
        users = {m.user_id for m in (await s.scalars(select(Membership))).all()}
        assert uuid.UUID(mallory.user_id) not in users
        inv = (await s.scalars(select(Invitation).where(Invitation.email == guest.email))).one()
        assert inv.accepted_at is None and inv.revoked_at is None
        assert inv.expires_at > datetime.now(UTC)


async def test_org_list_never_contains_other_peoples_orgs(world: World) -> None:
    _, _, b_owner, _, b = await _two_orgs(world)
    assert [o["id"] for o in (await b_owner.get("/orgs")).json()] == [b["id"]]
    spy = await world.person("Spy")
    assert (await spy.get("/orgs")).json() == []
