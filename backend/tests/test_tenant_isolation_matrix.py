"""Cross-tenant isolation matrix, generated from the live OpenAPI schema.

Every route that carries `{org_id}` is called as an outsider (a signed-in user who belongs to a
DIFFERENT organization) with the victim organization's real ids (organization, member, invitation,
collection, document), with a real organization id but random sub-resource ids, and with random ids
everywhere. All of them must answer an identical 404 and must not change anything.
A route that nobody classified makes the suite fail, so new endpoints cannot silently skip this.
"""

import re
import uuid
from typing import Any

from httpx import Response

from app.main import create_app
from tests import files
from tests.tenancy_helpers import Person, World

METHODS = ("get", "post", "put", "patch", "delete")

# Routes that are NOT organization-scoped, with the reason each is safe.
AUTH_PREFIX = "/api/v1/auth/"  # identity: acts on the caller's own account only
USER_SCOPED = {
    ("get", "/api/v1/orgs"),  # lists only the caller's own memberships (RLS enforced)
    ("post", "/api/v1/orgs"),  # creates a new org owned by the caller
    ("post", "/api/v1/invitations/accept"),  # capability = possession of the emailed token
}

ORG = "/api/v1/orgs/{org_id}"
# Minimal valid JSON bodies for body-bearing org-scoped routes (forgetting one fails the test).
BODIES: dict[tuple[str, str], dict[str, Any]] = {
    ("patch", ORG): {"name": "Hijacked"},
    ("patch", f"{ORG}/members/{{member_id}}"): {"role": "owner"},
    ("post", f"{ORG}/invitations"): {"email": "evil@example.com", "role": "admin"},
    ("post", f"{ORG}/collections"): {"name": "Planted"},
    ("patch", f"{ORG}/collections/{{collection_id}}"): {"name": "Hijacked", "visibility": "org"},
    ("put", f"{ORG}/collections/{{collection_id}}/members"): {"user_ids": []},
}
MULTIPART = {
    ("post", f"{ORG}/documents")
}  # sent as a real file upload into the victim's collection
PARAMS = {"org_id", "member_id", "invitation_id", "collection_id", "document_id"}


def _routes() -> list[tuple[str, str]]:
    spec = create_app().openapi()
    return [
        (method, path)
        for path, ops in spec["paths"].items()
        for method in ops
        if method in METHODS and path.startswith("/api/v1/")
    ]


def test_every_api_route_is_classified() -> None:
    unclassified = [
        (m, p)
        for m, p in _routes()
        if not p.startswith(AUTH_PREFIX) and (m, p) not in USER_SCOPED and "{org_id}" not in p
    ]
    assert not unclassified, (
        f"Routes without org scoping must be added to USER_SCOPED with a justification: {unclassified}"
    )


def test_every_org_scoped_route_has_a_body_sample_when_it_needs_one() -> None:
    missing = [
        (m, p)
        for m, p in _routes()
        if "{org_id}" in p
        and m in ("post", "put", "patch")
        and (m, p) not in BODIES
        and (m, p) not in MULTIPART
    ]
    assert not missing, f"Add sample bodies for: {missing}"


def test_route_templates_only_use_known_path_parameters() -> None:
    for _, path in _routes():
        assert set(re.findall(r"{(\w+)}", path)) <= PARAMS, path


def _fill(path: str, ids: dict[str, str]) -> str:
    for name, value in ids.items():
        path = path.replace("{" + name + "}", value)
    return path


async def _call(
    person: Person, method: str, template: str, url: str, collection_id: str
) -> Response:
    headers = person.h() if method != "get" else None
    if (method, template) in MULTIPART:
        return await person.client.post(
            url,
            data={"collection_id": collection_id},
            files=[("files", ("planted.pdf", files.pdf("planted"), "application/pdf"))],
            headers=headers,
        )
    return await person.client.request(
        method.upper(), url, json=BODIES.get((method, template)), headers=headers
    )


async def _snapshot(owner: Person, org_id: str) -> dict[str, Any]:
    base = f"/orgs/{org_id}"
    return {
        "org": (await owner.get(base)).json(),
        "members": (await owner.get(f"{base}/members")).json(),
        "invites": (await owner.get(f"{base}/invitations")).json(),
        "collections": (await owner.get(f"{base}/collections")).json(),
        "documents": (await owner.get(f"{base}/documents")).json(),
    }


def _normalised(r: Response) -> dict[str, Any]:
    body = dict(r.json())
    body.pop("request_id", None)
    return body


async def _victim(world: World) -> tuple[Person, dict[str, str]]:
    victim = await world.person("Victim")
    member = await world.person("Member")
    org = await world.org(victim, "Victim Org")
    oid = org["id"]
    await world.join(victim, oid, member, "member")
    await victim.post(
        f"/orgs/{oid}/invitations", {"email": "pending@example.com", "role": "viewer"}
    )
    collection_id = await world.collection(
        victim, oid, "Board", "restricted", members=[member.user_id]
    )
    upload = await victim.upload(oid, collection_id, ("secret.pdf", files.pdf("secret")))
    ids = {
        "org_id": oid,
        "member_id": await world.member_id(victim, oid, member.user_id),
        "invitation_id": (await victim.get(f"/orgs/{oid}/invitations")).json()[0]["id"],
        "collection_id": collection_id,
        "document_id": upload.json()[0]["document"]["id"],
    }
    return victim, ids


async def test_outsiders_get_an_identical_404_on_every_org_scoped_route(world: World) -> None:
    victim, ids = await _victim(world)
    outsider = await world.person("Outsider")
    await world.org(outsider, "Outsider Org")  # a real user with a real org of their own
    before = await _snapshot(victim, ids["org_id"])

    absent = {name: str(uuid.uuid4()) for name in PARAMS}
    scenarios = {
        "victim ids": ids,
        "victim org, random subresources": {**absent, "org_id": ids["org_id"]},
        "random everything": absent,
    }
    scoped = [(m, p) for m, p in _routes() if "{org_id}" in p]
    assert len(scoped) >= 18, "the matrix found suspiciously few routes"
    reference: dict[str, Any] | None = None
    checked = 0
    for method, template in scoped:
        for label, mapping in scenarios.items():
            url = _fill(template, mapping)
            r = await _call(outsider, method, template, url, mapping["collection_id"])
            assert r.status_code == 404, (
                f"{method.upper()} {url} [{label}] -> {r.status_code} {r.text[:120]}"
            )
            body = _normalised(r)
            assert body["code"] == "NOT_FOUND"
            reference = reference or body
            assert body == reference, "404 bodies must be identical (no existence oracle)"
            checked += 1
    assert checked == len(scoped) * 3

    # unauthenticated callers never reach the tenant layer
    outsider.client.cookies.clear()
    for method, template in scoped:
        url = _fill(template, ids)
        r = await _call(outsider, method, template, url, ids["collection_id"])
        # state-changing calls fail the CSRF check first; either way nothing is processed
        assert r.status_code in (401, 403), (
            f"{method.upper()} {url} unauthenticated -> {r.status_code}"
        )
        assert r.json()["code"] in ("UNAUTHENTICATED", "CSRF_FAILED")

    assert await _snapshot(victim, ids["org_id"]) == before, (
        "an outsider request changed victim data"
    )


async def test_org_members_without_collection_access_are_also_refused_on_collection_routes(
    world: World,
) -> None:
    """Same-org, wrong-collection: a member not on the restricted list gets the same 404."""
    victim, ids = await _victim(world)
    bystander = await world.person("Bystander")
    await world.join(victim, ids["org_id"], bystander, "editor")
    oid = ids["org_id"]
    for method, template in [
        (m, p) for m, p in _routes() if "{collection_id}" in p or "{document_id}" in p
    ]:
        if (method, template) in {("post", f"{ORG}/collections")}:
            continue
        url = _fill(template, ids)
        r = await _call(bystander, method, template, url, ids["collection_id"])
        # role failures (403) are acceptable for admin-only routes; leaks (2xx) and 5xx are not
        assert r.status_code in (403, 404), (
            f"{method.upper()} {url} -> {r.status_code} {r.text[:100]}"
        )
    assert (
        await victim.get(f"/orgs/{oid}/documents/{ids['document_id']}")
    ).status_code == 200  # intact


async def test_the_owner_really_reaches_every_get_route(world: World) -> None:
    """Guards the matrix against a false pass: the URLs it builds are valid for real members."""
    victim, ids = await _victim(world)
    for method, template in _routes():
        if method == "get" and "{org_id}" in template:
            r = await victim.client.get(_fill(template, ids))
            assert r.status_code == 200, template
