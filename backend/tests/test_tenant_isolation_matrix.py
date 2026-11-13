"""Cross-tenant isolation matrix, generated from the live OpenAPI schema.

Every route that carries `{org_id}` is called as an outsider (a signed-in user who belongs to a
DIFFERENT organization) with the victim organization's real id, and with the victim's real member
and invitation ids. All of them must answer an identical 404 and must not change anything.
A route that nobody classified makes the suite fail, so new endpoints cannot silently skip this.
"""

import re
import uuid
from typing import Any

from httpx import Response

from app.main import create_app
from tests.tenancy_helpers import Person, World

METHODS = ("get", "post", "put", "patch", "delete")

# Routes that are NOT organization-scoped, with the reason each is safe.
AUTH_PREFIX = "/api/v1/auth/"  # identity: acts on the caller's own account only
USER_SCOPED = {
    ("get", "/api/v1/orgs"),  # lists only the caller's own memberships (RLS enforced)
    ("post", "/api/v1/orgs"),  # creates a new org owned by the caller
    ("post", "/api/v1/invitations/accept"),  # capability = possession of the emailed token
}

# Minimal valid bodies for body-bearing org-scoped routes (required: forgetting one fails the test).
BODIES: dict[tuple[str, str], dict[str, Any]] = {
    ("patch", "/api/v1/orgs/{org_id}"): {"name": "Hijacked"},
    ("patch", "/api/v1/orgs/{org_id}/members/{member_id}"): {"role": "owner"},
    ("post", "/api/v1/orgs/{org_id}/invitations"): {"email": "evil@example.com", "role": "admin"},
}


def _routes() -> list[tuple[str, str]]:
    spec = create_app().openapi()
    return [
        (method, path)
        for path, ops in spec["paths"].items()
        for method in ops
        if method in METHODS and path.startswith("/api/v1/")
    ]


def test_every_api_route_is_classified() -> None:
    unclassified = []
    for method, path in _routes():
        if path.startswith(AUTH_PREFIX) or (method, path) in USER_SCOPED:
            continue
        if "{org_id}" not in path:
            unclassified.append((method, path))
    assert not unclassified, (
        f"Routes without org scoping must be added to USER_SCOPED with a justification: {unclassified}"
    )


def test_every_org_scoped_route_has_a_body_sample_when_it_needs_one() -> None:
    missing = [
        (m, p)
        for m, p in _routes()
        if "{org_id}" in p and m in ("post", "put", "patch") and (m, p) not in BODIES
    ]
    assert not missing, f"Add sample bodies for: {missing}"


def _fill(path: str, org_id: str, member_id: str, invitation_id: str) -> str:
    return (
        path.replace("{org_id}", org_id)
        .replace("{member_id}", member_id)
        .replace("{invitation_id}", invitation_id)
    )


def _call(person: Person, method: str, template: str, url: str) -> Any:
    body = BODIES.get((method, template))
    return person.client.request(
        method.upper(), url, json=body, headers=person.h() if method != "get" else None
    )


async def _snapshot(owner: Person, org_id: str) -> dict[str, Any]:
    org = await owner.get(f"/orgs/{org_id}")
    members = await owner.get(f"/orgs/{org_id}/members")
    invites = await owner.get(f"/orgs/{org_id}/invitations")
    return {"org": org.json(), "members": members.json(), "invites": invites.json()}


def _normalised(r: Response) -> dict[str, Any]:
    body = dict(r.json())
    body.pop("request_id", None)
    return body


async def test_outsiders_get_an_identical_404_on_every_org_scoped_route(world: World) -> None:
    victim, member, outsider = (
        await world.person("Victim"),
        await world.person("Member"),
        await world.person("Outsider"),
    )
    org = await world.org(victim, "Victim Org")
    await world.org(outsider, "Outsider Org")  # the outsider is a real user with a real org
    await world.join(victim, org["id"], member, "member")
    await victim.post(
        f"/orgs/{org['id']}/invitations", {"email": "pending@example.com", "role": "viewer"}
    )
    member_id = await world.member_id(victim, org["id"], member.user_id)
    invitation_id = (await victim.get(f"/orgs/{org['id']}/invitations")).json()[0]["id"]
    before = await _snapshot(victim, org["id"])

    absent = str(uuid.uuid4())
    scoped = [(m, p) for m, p in _routes() if "{org_id}" in p]
    assert len(scoped) >= 9, "the matrix found suspiciously few routes"
    reference: dict[str, Any] | None = None
    checked = 0
    for method, template in scoped:
        for who, (oid, mid, iid) in {
            "victim ids": (org["id"], member_id, invitation_id),
            "victim org, random subresource": (org["id"], absent, absent),
            "random everything": (absent, absent, absent),
        }.items():
            url = _fill(template, oid, mid, iid)
            r = await _call(outsider, method, template, url)
            assert r.status_code == 404, (
                f"{method.upper()} {url} [{who}] -> {r.status_code} {r.text}"
            )
            body = _normalised(r)
            assert body["code"] == "NOT_FOUND"
            reference = reference or body
            assert body == reference, "404 bodies must be identical (no existence oracle)"
            checked += 1

    # unauthenticated callers never reach the tenant layer
    outsider.client.cookies.clear()
    for method, template in scoped:
        url = _fill(template, org["id"], member_id, invitation_id)
        r = await _call(outsider, method, template, url)
        # state-changing calls fail the CSRF check first; either way nothing is processed
        assert r.status_code in (401, 403), (
            f"{method.upper()} {url} unauthenticated -> {r.status_code}"
        )
        assert r.json()["code"] in ("UNAUTHENTICATED", "CSRF_FAILED")

    assert await _snapshot(victim, org["id"]) == before, "an outsider request changed victim data"
    assert checked == len(scoped) * 3


async def test_the_owner_really_reaches_every_get_route(world: World) -> None:
    """Guards the matrix against a false pass: the URLs it builds are valid for real members."""
    owner = await world.person("Owner")
    org = await world.org(owner)
    member_id = await world.member_id(owner, org["id"], owner.user_id)
    for method, template in _routes():
        if method == "get" and "{org_id}" in template:
            url = _fill(template, org["id"], member_id, str(uuid.uuid4()))
            r = await _call(owner, method, template, url)
            assert r.status_code == 200, url


def test_route_templates_only_use_known_path_parameters() -> None:
    known = {"org_id", "member_id", "invitation_id"}
    for _, path in _routes():
        assert set(re.findall(r"{(\w+)}", path)) <= known, path
