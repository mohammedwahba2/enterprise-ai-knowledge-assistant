"""Stage 7 ablations: candidate embedders, normalization, language configs, fusion, routing.

Everything here is evaluation tooling. Candidate vectors are computed in memory (the corpus is a
few dozen chunks), so candidates with other dimensions never touch the product schema; the
product's own hybrid path is checked separately through the API (`ApiRetriever`).
"""

import math
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.embeddings.base import Embedder, embed_in_batches
from app.infrastructure.embeddings.ollama import OllamaEmbedder
from app.modules.documents.validation import title_from
from app.modules.processing.arabic import fold_digits
from app.modules.processing.indexing import embedding_text
from app.modules.retrieval.fusion import rrf
from evals.corpus import CorpusDoc, Question
from evals.harness import Retrieved, Retriever

N_CANDIDATES = 40


@dataclass(frozen=True)
class ChunkRow:
    slug: str
    chunk_index: int
    page_start: int
    page_end: int
    title: str
    heading_path: str
    content: str
    content_search: str

    @property
    def key(self) -> tuple[str, int]:
        return (self.slug, self.chunk_index)

    def retrieved(self) -> Retrieved:
        return Retrieved(
            self.slug, self.chunk_index, self.page_start, self.page_end, self.content_search
        )


async def load_chunks(sessions: async_sessionmaker[AsyncSession]) -> list[ChunkRow]:
    async with sessions() as s:
        rows = (
            await s.execute(
                text(
                    "select regexp_replace(d.original_filename, '\\.md$', ''), c.chunk_index, "
                    "c.page_start, c.page_end, d.title, c.heading_path, c.content, "
                    "c.content_search "
                    "from chunks c join documents d on d.id = c.document_id "
                    "where d.deleted_at is null order by 1, 2"
                )
            )
        ).all()
    return [ChunkRow(*tuple(r)) for r in rows]


@dataclass(frozen=True)
class EmbeddingModel:
    name: str
    url: str
    model: str
    dimensions: int
    query_prefix: str = ""
    passage_prefix: str = ""
    embedder: Embedder | None = None  # tests inject a fake; otherwise an Ollama-style server

    def client(self) -> Embedder:
        return self.embedder or OllamaEmbedder(self.url, self.model, self.dimensions, timeout=300.0)


class VectorIndex:
    """Exact cosine search over in-memory chunk vectors for one embedding model."""

    def __init__(
        self, model: EmbeddingModel, chunks: Sequence[ChunkRow], vectors: list[list[float]]
    ) -> None:
        self.model, self.chunks, self.vectors = model, chunks, vectors

    @classmethod
    async def build(cls, model: EmbeddingModel, chunks: Sequence[ChunkRow]) -> "VectorIndex":
        texts = [
            model.passage_prefix + embedding_text(c.title, c.heading_path, c.content)
            for c in chunks
        ]
        return cls(model, chunks, await embed_in_batches(model.client(), texts, 16))

    async def query_vector(self, query: str, *, fold: bool = True) -> list[float]:
        prepared = fold_digits(query) if fold else query
        (vector,) = await embed_in_batches(
            self.model.client(), [self.model.query_prefix + prepared], 1
        )
        return vector

    def rank(self, vector: list[float], n: int = N_CANDIDATES) -> list[ChunkRow]:
        def cosine(other: list[float]) -> float:
            dot = sum(a * b for a, b in zip(vector, other, strict=True))
            norm = math.sqrt(sum(a * a for a in vector)) * math.sqrt(sum(b * b for b in other))
            return dot / norm if norm else 0.0

        scored = sorted(
            ((cosine(v), c) for v, c in zip(self.vectors, self.chunks, strict=True)),
            key=lambda t: (-t[0], t[1].key),
        )
        return [c for _, c in scored[:n]]


def vector_retriever(index: VectorIndex, *, fold_query: bool = True, k: int = 10) -> Retriever:
    async def retrieve(question: Question) -> list[Retrieved]:
        vector = await index.query_vector(question.text, fold=fold_query)
        return [c.retrieved() for c in index.rank(vector)[:k]]

    return retrieve


_WORD = re.compile(r"\w+", re.UNICODE)


class RawFtsRetriever:
    """Full text with NO normalization at all (the ablation baseline for "does it help?").

    Lowercased words of the raw question against `to_tsvector('simple', content)` of the raw chunk.
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession], k: int = N_CANDIDATES) -> None:
        self.sessions, self.k = sessions, k

    async def __call__(self, question: Question) -> list[Retrieved]:
        words = _WORD.findall(question.text.lower())
        if not words:
            return []
        async with self.sessions() as s:
            rows = (
                await s.execute(
                    text(
                        "select regexp_replace(d.original_filename, '\\.md$', ''), c.chunk_index, "
                        "c.page_start, c.page_end, c.content_search "
                        "from chunks c join documents d on d.id = c.document_id "
                        "where to_tsvector('simple', c.content) @@ to_tsquery('simple', :q) "
                        "order by ts_rank_cd(to_tsvector('simple', c.content), "
                        "to_tsquery('simple', :q)) desc, 1, c.chunk_index limit :k"
                    ),
                    {"q": " | ".join(words), "k": self.k},
                )
            ).all()
        return [Retrieved(*tuple(r)) for r in rows]


def hybrid(
    legs: dict[str, Retriever],
    *,
    k: int = 60,
    limit: int = 10,
    weights: dict[str, int] | None = None,
) -> Retriever:
    """Reciprocal Rank Fusion of any retrievers (a weight repeats a leg's list)."""

    async def retrieve(question: Question) -> list[Retrieved]:
        by_key: dict[tuple[str, int], Retrieved] = {}
        rankings: dict[str, list[tuple[str, int]]] = {}
        for name, leg in legs.items():
            hits = list(await leg(question))
            for h in hits:
                by_key.setdefault((h.doc, h.chunk_index), h)
            for copy in range((weights or {}).get(name, 1)):
                rankings[f"{name}#{copy}"] = [(h.doc, h.chunk_index) for h in hits]
        return [by_key[key] for key, _ in rrf(rankings, k=k)[:limit]]

    return retrieve


def cached(retriever: Retriever) -> Retriever:
    """Memoize a retriever per question id, so a parameter grid re-fuses without re-querying."""
    memo: dict[str, list[Retrieved]] = {}

    async def retrieve(question: Question) -> list[Retrieved]:
        if question.id not in memo:
            memo[question.id] = list(await retriever(question))
        return memo[question.id]

    return retrieve


def routed(by_language: dict[str, Retriever], default: Retriever) -> Retriever:
    """Pick a retriever by the QUESTION's language (Arabic vs everything else)."""

    async def retrieve(question: Question) -> list[Retrieved]:
        return list(await by_language.get(question.lang, default)(question))

    return retrieve


# ---- the product path, through the API ---------------------------------------------------


def api_retriever(
    post_search: Callable[[str], Awaitable[list[dict[str, object]]]], corpus: Sequence[CorpusDoc]
) -> Retriever:
    """Wrap the real `POST /search` so the product path is scored by the same harness."""
    slug_by_title = {title_from(d.filename): d.slug for d in corpus}

    async def retrieve(question: Question) -> list[Retrieved]:
        hits = await post_search(question.text)
        out: list[Retrieved] = []
        for h in hits:
            content = str(h["content"])
            out.append(
                Retrieved(
                    slug_by_title[str(h["document_title"])],
                    0,
                    int(h["page_start"]),  # type: ignore[call-overload]
                    int(h["page_end"]),  # type: ignore[call-overload]
                    _search_text(content),
                )
            )
        return out

    return retrieve


def _search_text(content: str) -> str:
    from app.modules.processing.arabic import search_normalize

    return search_normalize(content)
