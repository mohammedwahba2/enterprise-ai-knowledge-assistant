"""The stage 7 ablation matrix: which retrieval configuration earns its complexity."""

from collections.abc import Awaitable, Callable, Sequence

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from evals.ablation import (
    EmbeddingModel,
    RawFtsRetriever,
    VectorIndex,
    api_retriever,
    cached,
    hybrid,
    load_chunks,
    routed,
    vector_retriever,
)
from evals.baselines import FtsRetriever
from evals.corpus import CorpusDoc, Question
from evals.harness import Report, Retriever, evaluate

ApiPost = Callable[[str], Awaitable[list[dict[str, object]]]]


FUSION_K = (60, 20, 10, 5, 3)
FUSION_WEIGHTS = (1, 2, 3, 4)
# The cell of the grid the product uses (see settings.rrf_k / rrf_vector_weight); every other
# hybrid in the matrix is evaluated at the same setting so the comparisons are fair.
CHOSEN_K = 3
CHOSEN_VECTOR_WEIGHT = 2


def chosen(legs: dict[str, Retriever], vector_leg: str = "vector") -> Retriever:
    return hybrid(legs, k=CHOSEN_K, weights={vector_leg: CHOSEN_VECTOR_WEIGHT})


async def run_ablations(
    sessions: async_sessionmaker[AsyncSession],
    corpus: Sequence[CorpusDoc],
    questions: Sequence[Question],
    *,
    primary: EmbeddingModel,
    candidates: Sequence[EmbeddingModel] = (),
    api_post: ApiPost | None = None,
    dev_ids: frozenset[str] = frozenset(),
) -> tuple[list[Report], str]:
    """`primary` is the product's embedder (bge-m3); `candidates` are the bake-off challengers."""
    chunks = await load_chunks(sessions)
    fts_language = FtsRetriever(sessions, "language", k=40)
    fts_simple = FtsRetriever(sessions, "simple", k=40)
    fts_raw = RawFtsRetriever(sessions)
    primary_index = await VectorIndex.build(primary, chunks)
    vec_primary = vector_retriever(primary_index, k=40)

    async def run(name: str, retriever: Callable[..., Awaitable[Sequence[object]]]) -> Report:
        return await evaluate(name, retriever, questions, corpus)  # type: ignore[arg-type]

    # Fusion grid first: legs are cached, so each (k, weight) cell is pure re-fusion.
    grid_vec = cached(vec_primary)
    grid_fts = cached(fts_language)
    reports: list[Report] = []
    split_rows: list[str] = []
    dev = [q for q in questions if q.id in dev_ids]
    test = [q for q in questions if q.id not in dev_ids]
    for rrf_k in FUSION_K:
        for weight in FUSION_WEIGHTS:
            cell = hybrid(
                {"vector": grid_vec, "fts": grid_fts}, k=rrf_k, weights={"vector": weight}
            )
            reports.append(await run(f"FUSION GRID k={rrf_k} vector-weight={weight}", cell))
            if dev_ids:
                d = await evaluate("dev", cell, dev, corpus)
                t = await evaluate("test", cell, test, corpus)
                split_rows.append(
                    f"| k={rrf_k} weight={weight} | {d.overall.recall[5]:.2f} "
                    f"| {t.overall.recall[5]:.2f} "
                    f"| {d.overall.mrr:.2f} | {t.overall.mrr:.2f} |"
                )
    reports += [
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
            chosen({"vector": vec_primary, "fts": fts_simple}),
        ),
        await run(
            f"hybrid RRF, {primary.name} + full text (raw)",
            chosen({"vector": vec_primary, "fts": fts_raw}),
        ),
        await run(
            f"hybrid RRF, {primary.name} + full text (language-aware), chosen k/weight",
            chosen({"vector": vec_primary, "fts": fts_language}),
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
                chosen({"vector": legs, "fts": fts_language}),
            )
        )
    if candidate_vectors:
        everything: dict[str, Retriever] = {
            primary.name: vec_primary,
            **candidate_vectors,
            "fts": fts_language,
        }
        ensemble = chosen(everything, vector_leg=primary.name)
        reports.append(await run("hybrid RRF, all embedders + full text (ensemble)", ensemble))
        reports.append(
            await run(
                "language-routed: Arabic questions use the ensemble, English the primary hybrid",
                routed(
                    {"ar": ensemble},
                    chosen({"vector": vec_primary, "fts": fts_language}),
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
    split_table = ""
    if split_rows:
        split_table = (
            f"| fusion cell | dev R@5 (n={len(dev)}) | test R@5 (n={len(test)}) "
            "| dev MRR | test MRR |\n"
            "|---|---|---|---|---|\n" + "\n".join(split_rows) + "\n"
        )
    return reports, split_table
