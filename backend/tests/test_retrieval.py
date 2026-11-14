"""Hybrid retrieval end to end: real Postgres (pgvector, RLS), real pipeline, real API."""

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import text

from app.modules.access.policies import Role
from app.modules.retrieval import service as retrieval
from tests.fake_embedder import FakeEmbedder
from tests.pipeline_helpers import worker_sessions
from tests.tenancy_helpers import Person, World

CANARY = "CANARY-RESTRICTED-9X"
LEAVE = "Employees receive twenty five working days of paid annual leave per calendar year."
TRAVEL = "The daily travel allowance is three hundred riyals for domestic business trips."
SECRET = f"Board only: {CANARY}. The acquisition budget for Project Cedar is twelve million."


async def index(
    world: World,
    owner: Person,
    oid: str,
    cid: str,
    name: str,
    body: str,
    embedder: FakeEmbedder | None = None,
) -> str:
    r = await owner.upload(oid, cid, (f"{name}.md", f"# {name}\n\n{body}\n".encode()))
    assert r.json()[0]["outcome"] == "created", r.text
    doc_id = str(r.json()[0]["document"]["id"])
    assert await world.process(oid, doc_id, embedder=embedder) == "processed"
    return doc_id


async def search(
    person: Person, oid: str, query: str, *, limit: int = 8, collections: list[str] | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"query": query, "limit": limit}
    if collections is not None:
        body["collection_ids"] = collections
    r = await person.post(f"/orgs/{oid}/search", body)
    assert r.status_code == 200, r.text
    return dict(r.json())


def titles(result: dict[str, Any]) -> list[str]:
    return [h["document_title"] for h in result["hits"]]


class Team:
    """An organization with one person per role and a restricted collection with one member."""

    def __init__(self) -> None:
        self.people: dict[str, Person] = {}
        self.oid = ""
        self.general = ""
        self.restricted = ""


async def team(world: World) -> Team:
    t = Team()
    owner = await world.person("Owner")
    t.people["owner"] = owner
    t.oid = (await world.org(owner, "Acme"))["id"]
    t.general = await world.general(owner, t.oid)
    for role in ("admin", "editor", "member", "viewer", "listed"):
        person = await world.person(role.title())
        await world.join(owner, t.oid, person, "member" if role == "listed" else role)
        t.people[role] = person
    t.restricted = await world.collection(
        owner, t.oid, "Board", "restricted", members=[t.people["listed"].user_id]
    )
    await index(world, owner, t.oid, t.general, "leave policy", LEAVE)
    await index(world, owner, t.oid, t.general, "travel policy", TRAVEL)
    await index(world, owner, t.oid, t.restricted, "board minutes", SECRET)
    return t


# ------------------------------------------------------------------ basics


async def test_hybrid_search_ranks_the_matching_chunk_first(world: World) -> None:
    t = await team(world)
    result = await search(t.people["viewer"], t.oid, "how many days of annual leave per year")
    assert result["degraded"] is False
    assert titles(result)[0] == "leave policy"
    hit = result["hits"][0]
    assert hit["collection_name"] == "General" and hit["page_start"] == 1
    assert "twenty five working days" in hit["content"]
    assert 0 < hit["similarity"] <= 1 and hit["score"] > 0


async def test_limit_and_collection_narrowing_are_honored(world: World) -> None:
    t = await team(world)
    owner = t.people["owner"]
    assert len((await search(owner, t.oid, "policy leave travel", limit=1))["hits"]) == 1
    only_general = await search(owner, t.oid, "board budget leave", collections=[t.general])
    assert "board minutes" not in titles(only_general)


@pytest.mark.parametrize("role", ["owner", "admin", "editor", "member", "viewer"])
async def test_every_role_can_search_but_only_admins_can_use_debug(world: World, role: str) -> None:
    t = await team(world)
    person = t.people[role]
    assert (
        await person.post(f"/orgs/{t.oid}/search", {"query": "annual leave"})
    ).status_code == 200
    debug = await person.post(f"/orgs/{t.oid}/search/debug", {"query": "annual leave"})
    assert debug.status_code == (200 if role in ("owner", "admin") else 403)


async def test_debug_shows_each_leg_and_the_fused_score(world: World) -> None:
    t = await team(world)
    r = await t.people["admin"].post(
        f"/orgs/{t.oid}/search/debug", {"query": "annual leave per year"}
    )
    body = r.json()
    assert body["embedding_model"] == "fake-hash-1024" and body["accessible_collections"] == 2
    assert body["vector_candidates"] > 0 and body["fts_candidates"] > 0
    top = body["hits"][0]
    assert top["vector_rank"] == 1 and top["fts_rank"] == 1 and top["fts_score"] > 0
    assert set(body["timings_ms"]) == {"vector", "fts", "total"}


@pytest.mark.parametrize(
    "payload",
    [
        {"query": ""},
        {"query": "   "},
        {"query": "x" * 1001},
        {"query": "a", "limit": 0},
        {"query": "a", "limit": 21},
    ],
)
async def test_invalid_requests_are_rejected(world: World, payload: dict[str, Any]) -> None:
    t = await team(world)
    assert (await t.people["viewer"].post(f"/orgs/{t.oid}/search", payload)).status_code == 422


# ------------------------------------------------------------------ permissions


async def test_restricted_text_never_reaches_unlisted_members(world: World) -> None:
    t = await team(world)
    for who in ("member", "viewer", "editor"):
        r = await t.people[who].post(
            f"/orgs/{t.oid}/search", {"query": f"{CANARY} acquisition budget Project Cedar"}
        )
        assert r.status_code == 200
        assert (
            CANARY not in r.text and "Project Cedar" not in r.text and "board minutes" not in r.text
        )
    # listed member, admin and owner can find it
    for who in ("listed", "admin", "owner"):
        found = await search(t.people[who], t.oid, f"{CANARY} acquisition budget")
        assert titles(found)[0] == "board minutes", who


async def test_naming_an_inaccessible_collection_leaks_nothing(world: World) -> None:
    t = await team(world)
    viewer = t.people["viewer"]
    asked = await search(viewer, t.oid, f"{CANARY} budget", collections=[t.restricted])
    assert asked["hits"] == []  # no error either: existence is not revealed
    mixed = await search(viewer, t.oid, "annual leave", collections=[t.restricted, t.general])
    assert titles(mixed)[0] == "leave policy"
    unknown = await search(viewer, t.oid, CANARY, collections=[str(uuid.uuid4())])
    assert unknown["hits"] == []  # same as naming a collection that exists but is off limits


async def test_revoking_access_takes_effect_on_the_very_next_search(world: World) -> None:
    t = await team(world)
    owner, listed = t.people["owner"], t.people["listed"]
    assert titles(await search(listed, t.oid, f"{CANARY} budget"))[:1] == ["board minutes"]
    r = await owner.put(f"/orgs/{t.oid}/collections/{t.restricted}/members", {"user_ids": []})
    assert r.status_code == 200
    after = await listed.post(f"/orgs/{t.oid}/search", {"query": f"{CANARY} budget"})
    assert CANARY not in after.text and "board minutes" not in after.text


async def test_a_deleted_document_disappears_at_once_even_before_the_purge(world: World) -> None:
    t = await team(world)
    owner = t.people["owner"]
    doc_id = await index(
        world, owner, t.oid, t.general, "cafeteria menu", "Tuesday is soup day, with lentil soup."
    )
    assert titles(await search(owner, t.oid, "lentil soup"))[0] == "cafeteria menu"
    assert (await owner.delete(f"/orgs/{t.oid}/documents/{doc_id}")).status_code == 204
    # the chunks still exist (the sweeper purges them later) but must not be returned
    engine, sessions = worker_sessions(world.worker_db_url)
    try:
        async with sessions() as s:
            left = await s.scalar(
                text("select count(*) from chunks where document_id=:d"), {"d": uuid.UUID(doc_id)}
            )
    finally:
        await engine.dispose()
    assert left and left > 0
    assert "cafeteria menu" not in titles(await search(owner, t.oid, "lentil soup"))


async def test_tenants_never_see_each_others_chunks(world: World) -> None:
    a, b = await world.person("Alice"), await world.person("Bob")
    oa, ob = (await world.org(a, "A Corp"))["id"], (await world.org(b, "B Corp"))["id"]
    ca, cb = await world.general(a, oa), await world.general(b, ob)
    await index(world, a, oa, ca, "a secret", "Alpha corp only: zebra lantern protocol seven.")
    await index(world, b, ob, cb, "b notes", "Beta corp notes about lunch menus.")
    assert titles(await search(a, oa, "zebra lantern protocol"))[0] == "a secret"
    from_b = await b.post(f"/orgs/{ob}/search", {"query": "zebra lantern protocol seven"})
    assert "a secret" not in from_b.text and "Alpha" not in from_b.text
    # Bob cannot use Alice's org id at all: identical 404 to a nonexistent organization
    foreign = await b.post(f"/orgs/{oa}/search", {"query": "zebra"})
    nonexistent = await b.post(f"/orgs/{uuid.uuid4()}/search", {"query": "zebra"})
    assert foreign.status_code == nonexistent.status_code == 404
    assert foreign.json()["code"] == nonexistent.json()["code"]


# ------------------------------------------------------------------ models, outages, normalization


async def test_chunks_from_another_model_are_excluded_from_vectors_but_still_found_by_text(
    world: World,
) -> None:
    t = await team(world)
    owner = t.people["owner"]
    await index(
        world,
        owner,
        t.oid,
        t.general,
        "legacy handbook",
        "Legacy handbook: parking permits are issued by facilities.",
        embedder=FakeEmbedder(model="older-model"),
    )
    r = await t.people["admin"].post(
        f"/orgs/{t.oid}/search/debug", {"query": "parking permits facilities"}
    )
    hit = next(h for h in r.json()["hits"] if h["document_title"] == "legacy handbook")
    assert hit["vector_rank"] is None and hit["fts_rank"] is not None  # lexical leg only
    assert r.json()["degraded"] is False  # the embedder is fine; those chunks are just stale


async def test_search_degrades_to_full_text_when_the_embedder_is_down(world: World) -> None:
    world.embedder = FakeEmbedder(unavailable=True)
    t = await team(world)
    result = await search(t.people["viewer"], t.oid, "annual leave")
    assert result["degraded"] is True
    assert titles(result)[0] == "leave policy" and result["hits"][0]["similarity"] is None


async def test_digit_scripts_and_spelling_variants_return_identical_results(world: World) -> None:
    t = await team(world)
    owner = t.people["owner"]
    await index(
        world,
        owner,
        t.oid,
        t.general,
        "limits",
        "الحد الأقصى للمصروفات 25000 ريال، ويوافق المدير المالي على الإجازة",
    )
    rankings = []
    for q in (
        "الحد الأقصى 25000 ريال",
        "الحد الأقصى ٢٥٠٠٠ ريال",
        "الحد الأقصى ۲۵۰۰۰ ريال",
        "الحد الاقصى 25000 ريال",
    ):
        rankings.append([h["chunk_id"] for h in (await search(owner, t.oid, q))["hits"]])
    assert rankings[0] and all(r == rankings[0] for r in rankings)


async def test_the_search_is_rate_limited_per_user(world: World) -> None:
    world.settings = world.settings.model_copy(update={"search_rate_per_minute": 3})
    t = await team(world)
    viewer = t.people["viewer"]
    codes = [
        (await viewer.post(f"/orgs/{t.oid}/search", {"query": "leave"})).status_code
        for _ in range(5)
    ]
    assert codes == [200, 200, 200, 429, 429]
    other = await t.people["member"].post(f"/orgs/{t.oid}/search", {"query": "leave"})
    assert other.status_code == 200  # the limit is per user


# ------------------------------------------------------------------ database layer


async def test_row_level_security_alone_hides_restricted_chunks_from_the_api_role(
    world: World,
) -> None:
    t = await team(world)
    viewer, listed = t.people["viewer"], t.people["listed"]
    async with world.scoped_db(t.oid, viewer.user_id) as s:
        assert await s.scalar(text("select count(*) from chunks")) == 2  # General only
        with pytest.raises(Exception, match="permission denied"):
            await s.execute(text("delete from chunks"))
    async with world.scoped_db(t.oid, listed.user_id) as s:
        assert await s.scalar(text("select count(*) from chunks")) == 3
        with pytest.raises(Exception, match="permission denied"):
            await s.execute(text("update chunks set content = 'x'"))


async def test_filtered_vector_search_still_fills_the_candidate_list(world: World) -> None:
    """The nearest vectors all live in a collection the caller cannot access. Without HNSW
    iterative scans a filtered search returns almost nothing; with them it keeps scanning."""
    t = await team(world)
    owner = t.people["owner"]
    query = "quarterly forecast variance report"
    for i in range(70):  # restricted chunks that are much closer to the query
        await index(world, owner, t.oid, t.restricted, f"forecast {i}", f"{query} number {i}")
    viewer = t.people["viewer"]
    async with world.scoped_db(t.oid, viewer.user_id) as s:
        # Forbid sequential scans and explicit sorts: the only way left to satisfy
        # "ORDER BY distance LIMIT n" is the HNSW index, which is what runs at real scale.
        await s.execute(text("set local enable_seqscan = off"))
        await s.execute(text("set local enable_sort = off"))
        ctx = SimpleNamespace(
            db=s,
            org_id=uuid.UUID(t.oid),
            role=Role.VIEWER,
            user=SimpleNamespace(id=uuid.UUID(viewer.user_id)),
        )
        # A tiny ef_search makes the plain filtered scan stop after 10 candidates, all of them
        # restricted ones; only iterative scanning keeps going until it finds accessible chunks.
        settings = world.settings.model_copy(update={"hnsw_ef_search": 10})
        scope = retrieval._scope(ctx, None)  # type: ignore[arg-type]
        hits = await retrieval._vector_leg(ctx, FakeEmbedder(), query, scope, 40, settings)  # type: ignore[arg-type]
    # the viewer may see exactly the two General chunks and none of the 70 restricted ones
    assert len(hits) == 2


async def test_the_query_reaches_the_embedder_with_ascii_digits(world: World) -> None:
    """The fake embedder folds digits itself, which would hide a regression: record what it gets."""
    recorder = FakeEmbedder()
    world.embedder = recorder
    t = await team(world)
    await search(t.people["viewer"], t.oid, "الحد ٢٥٬٠٠٠ ريال و ۷۵ يوماً")
    assert recorder.texts == ["الحد 25,000 ريال و 75 يوماً"]


def test_product_fusion_defaults_are_the_cell_the_evaluation_chose() -> None:
    from app.core.config import Settings
    from evals.stage7 import CHOSEN_K, CHOSEN_VECTOR_WEIGHT

    settings = Settings()
    assert (settings.rrf_k, settings.rrf_vector_weight) == (CHOSEN_K, CHOSEN_VECTOR_WEIGHT)


async def test_the_lexical_leg_alone_tells_documents_apart_by_digits_in_any_script(
    world: World,
) -> None:
    """With the embedder down only full text answers, so a broken lexical normalization cannot be
    hidden by the vector leg. Two documents differ ONLY by a number; the question types that
    number in Western, Arabic-Indic or Persian digits and must find the right one every time."""
    world.embedder = FakeEmbedder(unavailable=True)
    t = await team(world)
    owner = t.people["owner"]
    for name, amount in (("limit a", "25000"), ("limit b", "30000")):
        await index(
            world, owner, t.oid, t.general, name, f"الحد الأقصى للمصروفات {amount} ريال",
            embedder=FakeEmbedder(),
        )  # fmt: skip
    expectations = {
        "الحد الأقصى 25000": "limit a", "الحد الأقصى ٢٥٠٠٠": "limit a", "الحد الأقصى ۲۵۰۰۰": "limit a",
        "الحد الأقصى 30000": "limit b", "الحد الأقصى ٣٠٠٠٠": "limit b", "الحد الأقصى ۳۰۰۰۰": "limit b",
    }  # fmt: skip
    for query, expected in expectations.items():
        result = await search(owner, t.oid, query)
        assert result["degraded"] is True
        assert titles(result)[0] == expected, query
