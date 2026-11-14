"""Shared plumbing for the stage 8 evaluation: build the workspace, ask through the real API."""

import json
from dataclasses import dataclass
from typing import Any

from app.infrastructure.embeddings.base import Embedder
from app.modules.documents.validation import title_from
from evals import corpus
from evals.answers import ADV_DIR, AnswerCase, Outcome
from tests.pdfgen import PageSpec, make_pdf
from tests.tenancy_helpers import Person, World

SCAN_NAME = "supplier_agreement_scan.pdf"


@dataclass
class Workspace:
    owner: Person
    viewer: Person
    org_id: str
    general: str
    restricted: str
    slug_by_title: dict[str, str]

    def person(self, user: str) -> Person:
        return self.owner if user == "owner" else self.viewer


async def build_workspace(
    world: World, embedder: Embedder, *, include_adversarial: bool = True
) -> Workspace:
    """An organization with an owner, a viewer without access to the restricted collection, the
    whole evaluation corpus (the board minutes in the restricted collection), the adversarial
    documents and one scanned PDF that has no text layer."""
    owner = await world.person("Owner")
    viewer = await world.person("Viewer")
    oid = (await world.org(owner, "Eval Co"))["id"]
    await world.join(owner, oid, viewer, "viewer")
    general = await world.general(owner, oid)
    restricted = await world.collection(owner, oid, "Board", "restricted", members=[])
    slug_by_title: dict[str, str] = {}
    files: list[tuple[str, str, bytes]] = []
    for doc in corpus.build_corpus():
        files.append((doc.slug, restricted if doc.restricted else general, doc.text.encode()))
        slug_by_title[title_from(doc.filename)] = doc.slug
    if include_adversarial:
        for path in sorted(ADV_DIR.glob("*.md")):
            files.append((path.stem, general, path.read_bytes()))
            slug_by_title[title_from(path.name)] = path.stem
        files.append((SCAN_NAME, general, make_pdf([PageSpec([], image_ratio=0.9)])))
    for slug, collection_id, data in files:
        name = slug if slug.endswith(".pdf") else f"{slug}.md"
        r = await owner.upload(oid, collection_id, (name, data))
        result = r.json()[0]
        assert result["outcome"] == "created", (name, result)
        await world.process(oid, str(result["document"]["id"]), embedder=embedder)
    return Workspace(owner, viewer, oid, general, restricted, slug_by_title)


def parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for frame in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in frame.splitlines() if ": " in line)
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def to_outcome(events: list[tuple[str, dict[str, Any]]], slug_by_title: dict[str, str]) -> Outcome:
    by_name = dict(events)
    if "final" in by_name:
        f = by_name["final"]
        return Outcome(
            "complete", f["text"], cited_docs=tuple(slug_by_title.get(c["document_title"], c["document_title"]) for c in f["citations"]),
            partially_supported=f["partially_supported"], language=f["language"],
            first_token_ms=f["first_token_ms"], latency_ms=f["latency_ms"],
            sources=tuple(c["quote"] for c in f["citations"]),
        )  # fmt: skip
    if "refused" in by_name:
        r = by_name["refused"]
        return Outcome(
            "refused", r["text"], refusal_reason=r["reason"],
            related_titles=tuple(x["document_title"] for x in r["related"]),
            unsearchable_documents=r.get("unsearchable_documents", 0),
        )  # fmt: skip
    return Outcome("error", refusal_reason=by_name.get("error", {}).get("code"))


async def ask_case(ws: Workspace, case: AnswerCase) -> Outcome:
    person = ws.person(case.user)
    created = await person.post(f"/orgs/{ws.org_id}/conversations", {})
    cid = created.json()["id"]
    r = await person.post(f"/orgs/{ws.org_id}/conversations/{cid}/messages", {"content": case.text})
    if r.status_code != 200:
        return Outcome("error", refusal_reason=f"HTTP {r.status_code}")
    return to_outcome(parse_sse(r.text), ws.slug_by_title)
