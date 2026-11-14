"""The stage 7 ablation matrix: which retrieval configuration earns its complexity."""

from collections.abc import Awaitable, Callable, Sequence

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from evals.ablation import (
    EmbeddingModel,
    RawFtsRetriever,
    VectorIndex,
    api_retriever,
    hybrid,
    load_chunks,
    routed,
    vector_retriever,
)
from evals.baselines import FtsRetriever
from evals.corpus import CorpusDoc, Question
from evals.harness import Report, Retriever, evaluate

ApiPost = Callable[[str], Awaitable[list[dict[str, object]]]]


async def run_ablations(
    sessions: async_sessionmaker[AsyncSession],
    corpus: Sequence[CorpusDoc],
    questions: Sequence[Question],
    *,
    primary: EmbeddingModel,
    candidates: Sequence[EmbeddingModel] = (),
    api_post: ApiPost | None = None,
) -> list[Report]:
    """`primary` is the product's embedder (bge-m3); `candidates` are the bake-off challengers."""
    chunks = await load_chunks(sessions)
    fts_language = FtsRetriever(sessions, "language", k=40)
    fts_simple = FtsRetriever(sessions, "simple", k=40)
    fts_raw = RawFtsRetriever(sessions)
    primary_index = await VectorIndex.build(primary, chunks)
    vec_primary = vector_retriever(primary_index, k=40)

    async def run(name: str, retriever: Callable[..., Awaitable[Sequence[object]]]) -> Report:
        return await evaluate(name, retriever, questions, corpus)  # type: ignore[arg-type]

    reports = [
        await run("full text, language-aware (arabic/english configs)", fts_language),
        await run("full text, simple config", fts_simple),
        await run("full text, raw (no normalization at all)", fts_raw),
        await run(f"vector, {primary.name}", vector_retriever(primary_index)),
        await run(
            f"vector, {primary.name}, query digits NOT folded",
            vector_retriever(primary_index, fold_query=False),
        ),
        await run(
            f"hybrid RRF, {primary.name} + full text (language-aware)",
            hybrid({"vector": vec_primary, "fts": fts_language}),
        ),
        await run(
            f"hybrid RRF, {primary.name} + full text (simple)",
            hybrid({"vector": vec_primary, "fts": fts_simple}),
        ),
        await run(
            f"hybrid RRF, {primary.name} + full text (raw)",
            hybrid({"vector": vec_primary, "fts": fts_raw}),
        ),
        await run(
            f"hybrid RRF, {primary.name} weighted 2:1 over full text",
            hybrid({"vector": vec_primary, "fts": fts_language}, weights={"vector": 2}),
        ),
    ]
    candidate_vectors: dict[str, Retriever] = {}
    for model in candidates:
        index = await VectorIndex.build(model, chunks)
        legs = vector_retriever(index, k=40)
        candidate_vectors[model.name] = legs
        reports.append(await run(f"vector, {model.name}", vector_retriever(index)))
        reports.append(
            await run(
                f"hybrid RRF, {model.name} + full text (language-aware)",
                hybrid({"vector": legs, "fts": fts_language}),
            )
        )
    if candidate_vectors:
        everything: dict[str, Retriever] = {
            primary.name: vec_primary,
            **candidate_vectors,
            "fts": fts_language,
        }
        ensemble = hybrid(everything)
        reports.append(await run("hybrid RRF, all embedders + full text (ensemble)", ensemble))
        reports.append(
            await run(
                "language-routed: Arabic questions use the ensemble, English the primary hybrid",
                routed(
                    {"ar": ensemble},
                    hybrid({"vector": vec_primary, "fts": fts_language}),
                ),
            )
        )
    if api_post is not None:
        reports.append(
            await run(
                "PRODUCT: POST /search (pgvector HNSW + full text, RRF, permission-filtered)",
                api_retriever(api_post, corpus),
            )
        )
    return reports
