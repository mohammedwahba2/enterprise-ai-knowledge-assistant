"""The stage 7 ablation matrix: plumbing with the fake embedder, and the opt-in live evaluation.

Default run: validates that every configuration runs on the real database and that the product
`POST /search` path behaves like the in-memory hybrid. `EVAL_LIVE_OLLAMA=1` additionally runs the
real bge-m3 model and writes `docs/eval/stage7-retrieval.md`; `EVAL_E5_URL` / `EVAL_ATM_URL`
(servers started with `evals/serve_embedder.py`) add the bake-off candidates.
"""

import os
import re
from datetime import date
from pathlib import Path

import pytest

from app.infrastructure.embeddings.ollama import OllamaEmbedder
from evals.ablation import EmbeddingModel
from evals.corpus import build_corpus, load_questions
from evals.harness import check_gates, render_markdown, render_summary
from evals.stage7 import run_ablations
from tests.eval_support import ingest_corpus
from tests.fake_embedder import FakeEmbedder
from tests.pipeline_helpers import worker_sessions
from tests.tenancy_helpers import Person, World
from tests.test_pipeline import setup

# The questions that existed at stage 6, before the fusion grid was run: the fusion parameters were
# chosen by looking at these ("dev"); everything authored later is the held-out "test" set.
STAGE6_IDS = frozenset(
    q.id
    for q in load_questions()
    if re.fullmatch(
        r"(en|ar)-(0[1-9]|1[0-2])|x-(ar-en|en-ar)-0[1-8]|mix-.*|dg-.*|var-.*|restr-.*|none-0[1-6]",
        q.id,
    )
)
REPORT = Path(__file__).resolve().parents[2] / "docs" / "eval" / "stage7-retrieval.md"


def api_search(owner: Person, oid: str):  # type: ignore[no-untyped-def]
    async def post(query: str) -> list[dict[str, object]]:
        r = await owner.post(f"/orgs/{oid}/search", {"query": query, "limit": 10})
        assert r.status_code == 200, r.text
        return list(r.json()["hits"])

    return post


async def test_every_configuration_runs_and_the_product_path_matches_the_hybrid(
    world: World,
) -> None:
    embedder = FakeEmbedder()
    world.embedder = embedder
    world.settings = world.settings.model_copy(update={"search_rate_per_minute": 100_000})
    owner, oid, cid = await setup(world)
    await ingest_corpus(world, owner, oid, cid, embedder)
    engine, sessions = worker_sessions(world.worker_db_url)
    try:
        reports, _ = await run_ablations(
            sessions,
            build_corpus(),
            load_questions(),
            primary=EmbeddingModel("fake", "", embedder.model, 1024, embedder=embedder),
            api_post=api_search(owner, oid),
        )
    finally:
        await engine.dispose()
    by_name = {r.name: r for r in reports}
    assert len(reports) == 10 + 20
    product = by_name[next(n for n in by_name if n.startswith("PRODUCT"))]
    in_memory = by_name["FUSION GRID k=3 vector-weight=2"]
    # same legs, same fusion, same data: the product path must score the same as the harness model
    # recall@1 is excluded on purpose: equal fused scores are ordered by document name in the
    # harness and by id in the product, which can swap two tied chunks at rank 1 and nowhere else
    for k in (3, 5, 10):
        assert product.overall.recall[k] == pytest.approx(in_memory.overall.recall[k], abs=0.03)
    assert product.overall.mrr == pytest.approx(in_memory.overall.mrr, abs=0.05)
    assert product.digit_consistency == 1.0
    summary = render_summary(reports)
    assert (
        summary.count("\n") == len(reports) + 2
    )  # header + separator + rows and "PRODUCT" in summary


def _candidate(
    env: str, name: str, model: str, dims: int, query_prefix: str = "", passage_prefix: str = ""
) -> EmbeddingModel | None:
    url = os.environ.get(env)
    if not url:
        return None
    return EmbeddingModel(name, url, model, dims, query_prefix, passage_prefix)


@pytest.mark.skipif(not os.environ.get("EVAL_LIVE_OLLAMA"), reason="needs Ollama with bge-m3")
async def test_live_stage7_evaluation_report(world: World) -> None:
    ollama = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    embedder = OllamaEmbedder(ollama, "bge-m3", 1024, timeout=300.0)
    world.embedder = embedder
    world.settings = world.settings.model_copy(update={"search_rate_per_minute": 100_000})
    owner, oid, cid = await setup(world)
    await ingest_corpus(world, owner, oid, cid, embedder)
    candidates = [
        c
        for c in (
            _candidate(
                "EVAL_E5_URL", "multilingual-e5-large", "intfloat/multilingual-e5-large", 1024,
                query_prefix="query: ", passage_prefix="passage: ",
            ),
            _candidate(
                "EVAL_ATM_URL", "Arabic-Triplet-Matryoshka-V2",
                "Omartificial-Intelligence-Space/Arabic-Triplet-Matryoshka-V2", 768,
            ),
        )
        if c is not None
    ]  # fmt: skip
    engine, sessions = worker_sessions(world.worker_db_url)
    try:
        reports, split_table = await run_ablations(
            sessions, build_corpus(), load_questions(),
            primary=EmbeddingModel("bge-m3", ollama, "bge-m3", 1024),
            candidates=candidates, api_post=api_search(owner, oid), dev_ids=STAGE6_IDS,
        )  # fmt: skip
    finally:
        await engine.dispose()
    corpus, questions = build_corpus(), load_questions()
    product = next(r for r in reports if r.name.startswith("PRODUCT"))
    gates = "\n".join(
        f"- {'PASS' if ok else 'FAIL'}: {name} ({detail})"
        for name, ok, detail in check_gates(product)
    )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        "# Stage 7 retrieval evaluation and ablations\n\n"
        f"Generated {date.today().isoformat()} by `EVAL_LIVE_OLLAMA=1 pytest tests/test_eval_stage7.py`.\n\n"
        f"- Corpus: {len(corpus)} synthetic documents ({sum(1 for d in corpus if '__' in d.slug)} "
        "near-duplicate variants used as hard negatives), each one chunk.\n"
        f"- Questions: {len(questions)} ({len([q for q in questions if q.gold])} answerable).\n"
        "- Candidates evaluated: "
        + (", ".join(c.name for c in candidates) or "none (bge-m3 only)")
        + ".\n- Reranker: not evaluated (not downloaded).\n\n"
        "## Summary matrix (recall@5 unless stated)\n\n"
        + render_summary(reports)
        + "\n## Gates (initial, PLAN section 11.5) for the product path\n\n"
        + gates
        + "\n\n## Fusion cell chosen on the stage 6 questions (dev), checked on the new ones (test)\n\n"
        + split_table
        + "\n## Detail per configuration\n\n"
        + render_markdown(reports),
        encoding="utf-8",
    )
    assert product.digit_consistency == 1.0
