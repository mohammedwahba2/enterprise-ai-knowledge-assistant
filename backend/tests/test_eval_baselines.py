"""The baselines and harness end to end on the real database (real pipeline and indexes).

The default test uses the deterministic fake embedder. `EVAL_LIVE_OLLAMA=1` additionally runs the
real bge-m3 model and writes the committed baseline report (see docs/eval/).
"""

import os
from datetime import date
from pathlib import Path

import pytest

from app.infrastructure.embeddings.base import Embedder
from app.infrastructure.embeddings.ollama import OllamaEmbedder
from evals.baselines import FtsRetriever, VectorRetriever
from evals.corpus import build_corpus, load_questions
from evals.harness import Report, evaluate, render_markdown
from tests.eval_support import ingest_corpus
from tests.fake_embedder import FakeEmbedder
from tests.pipeline_helpers import worker_sessions
from tests.tenancy_helpers import World
from tests.test_pipeline import setup

REPORT = Path(__file__).resolve().parents[2] / "docs" / "eval" / "stage6-baseline.md"


async def run_baselines(world: World, embedder: Embedder, label: str) -> list[Report]:
    owner, oid, cid = await setup(world)
    await ingest_corpus(world, owner, oid, cid, embedder)
    engine, sessions = worker_sessions(world.worker_db_url)
    try:
        corpus, questions = build_corpus(), load_questions()
        return [
            await evaluate(
                f"vector, {label}", VectorRetriever(sessions, embedder), questions, corpus
            ),
            await evaluate(
                "full text, language-aware (arabic/english)",
                FtsRetriever(sessions, "language"),
                questions,
                corpus,
            ),
            await evaluate(
                "full text, simple", FtsRetriever(sessions, "simple"), questions, corpus
            ),
        ]
    finally:
        await engine.dispose()


async def test_baselines_discriminate_and_digit_variants_rank_identically(world: World) -> None:
    reports = await run_baselines(world, FakeEmbedder(), "fake hash embedder")
    questions = load_questions()
    answerable = len([q for q in questions if q.gold])
    unanswerable = len(questions) - answerable
    for report in reports:
        assert report.overall.n == answerable and report.unanswerable == unanswerable
        # the same question typed with Western, Arabic-Indic and Persian digits ranks identically
        assert report.digit_consistency == 1.0, report.name
        # same-language questions are findable...
        for category in ("en_factoid", "ar_factoid"):
            assert report.by_category[category].recall[10] >= 0.9, (report.name, category)
        # ...and these language-blind baselines cannot cross languages, so the harness is not
        # trivially saturated: a real multilingual model has headroom to win.
        for category in ("cross_ar_to_en", "cross_en_to_ar"):
            assert report.by_category[category].recall[10] <= 0.3, (report.name, category)
    vector = reports[0]
    assert vector.by_category["variant_entity"].recall[5] >= 0.8  # hard negatives are separable


@pytest.mark.skipif(
    not os.environ.get("EVAL_LIVE_OLLAMA"), reason="needs a running Ollama with bge-m3"
)
async def test_live_bge_m3_baseline_report(world: World) -> None:
    embedder = OllamaEmbedder(
        os.environ.get("OLLAMA_URL", "http://localhost:11434"), "bge-m3", 1024
    )
    reports = await run_baselines(world, embedder, "bge-m3 (Ollama)")
    corpus, questions = build_corpus(), load_questions()
    header = (
        "# Stage 6 retrieval baseline\n\n"
        f"Generated {date.today().isoformat()} by `EVAL_LIVE_OLLAMA=1 pytest "
        "tests/test_eval_baselines.py`. **Foundation numbers, not the stage-7 evaluation.**\n\n"
        f"- Corpus: {len(corpus)} synthetic documents ({sum(1 for d in corpus if '__' in d.slug)} are "
        "near-duplicate subsidiary variants used as hard negatives), each about one chunk.\n"
        f"- Questions: {len(questions)} ({len([q for q in questions if q.gold])} answerable).\n"
        "- Retrieval is unfiltered (no permissions), single-stage (no fusion, no reranker): "
        "the product path is stage 7.\n"
        "- Small corpus: differences of a few points are noise; read the cross-lingual rows and "
        "the large gaps.\n\n"
    )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(header + render_markdown(reports), encoding="utf-8")
    # PLAN section 11.5: the same question in any digit script must return identical results
    assert reports[0].digit_consistency == 1.0
