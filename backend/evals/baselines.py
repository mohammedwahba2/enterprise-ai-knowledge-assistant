"""Unfiltered baseline retrievers over the `chunks` table (worker role).

These exist to validate the harness and to give first numbers. They deliberately skip permission
filtering, fusion and reranking: the product retrieval path is stage 7.
"""

from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.types import vector_literal
from app.infrastructure.embeddings.base import Embedder
from evals.corpus import Question
from evals.harness import Retrieved, query_tokens

_SELECT = """
    select regexp_replace(d.original_filename, '\\.md$', '') as slug, c.chunk_index,
           c.page_start, c.page_end, c.content_search
    from chunks c join documents d on d.id = c.document_id
"""


def _rows(result: Sequence[tuple[str, int, int, int, str]]) -> list[Retrieved]:
    return [Retrieved(*row) for row in result]


class VectorRetriever:
    """Cosine nearest neighbours of the question embedding (HNSW)."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], embedder: Embedder, k: int = 10):
        self.sessions, self.embedder, self.k = sessions, embedder, k

    async def __call__(self, question: Question) -> list[Retrieved]:
        (vector,) = await self.embedder.embed([question.text])
        async with self.sessions() as s:
            result = await s.execute(
                text(
                    _SELECT
                    + " where c.embedding_model = :m"
                    + " order by c.embedding <=> CAST(CAST(:q AS text) AS vector) limit :k"
                ),
                {"q": vector_literal(vector), "m": self.embedder.model, "k": self.k},
            )
            return _rows([tuple(r) for r in result.all()])


class FtsRetriever:
    """Any-word full-text match ranked by ts_rank_cd. `config` is 'language' (per-chunk language
    config via content_tsv, query run through both) or 'simple' (content_tsv_simple)."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], config: str, k: int = 10):
        if config not in ("language", "simple"):
            raise ValueError(config)
        self.sessions, self.config, self.k = sessions, config, k

    async def __call__(self, question: Question) -> list[Retrieved]:
        words = query_tokens(question.text)
        if not words:
            return []
        query = " | ".join(words)
        if self.config == "simple":
            column, tsq = "c.content_tsv_simple", "to_tsquery('simple', :q)"
        else:
            column = "c.content_tsv"
            tsq = "(to_tsquery('arabic', :q) || to_tsquery('english', :q))"
        async with self.sessions() as s:
            result = await s.execute(
                text(
                    f"{_SELECT} where {column} @@ {tsq} "
                    f"order by ts_rank_cd({column}, {tsq}) desc, c.chunk_index limit :k"
                ),
                {"q": query, "k": self.k},
            )
            return _rows([tuple(r) for r in result.all()])
