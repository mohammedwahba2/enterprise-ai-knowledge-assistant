"""Ingest the evaluation corpus through the real upload API and ingestion pipeline."""

from app.infrastructure.embeddings.base import Embedder
from evals.corpus import build_corpus
from tests.tenancy_helpers import Person, World


async def ingest_corpus(
    world: World, owner: Person, org_id: str, collection_id: str, embedder: Embedder
) -> dict[str, str]:
    """Returns slug -> document id; every document must end `ready`."""
    ids: dict[str, str] = {}
    for doc in build_corpus():
        response = await owner.upload(
            org_id, collection_id, (doc.filename, doc.text.encode("utf-8"))
        )
        result = response.json()[0]
        assert result["outcome"] == "created", (doc.slug, result)
        document_id = str(result["document"]["id"])
        assert await world.process(org_id, document_id, embedder=embedder) == "processed", doc.slug
        ids[doc.slug] = document_id
    return ids
