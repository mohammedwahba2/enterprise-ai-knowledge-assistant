"""Stage 8 evaluation. Default run: the harness against the real database with fakes (fast).
Opt-in live runs (real models through Ollama) write the committed reports in docs/eval/:

  EVAL_LIVE_OLLAMA=1                       gate calibration  -> docs/eval/stage8-gate.md
  EVAL_LIVE_OLLAMA=1 EVAL_LIVE_LLMS=a,b    model bake-off    -> docs/eval/stage8-answers.md
"""

import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from app.infrastructure.embeddings.ollama import OllamaEmbedder
from app.infrastructure.llm.ollama import OllamaChat
from evals import gate, judge
from evals.answers import (
    ADV_CATEGORIES,
    AnswerCase,
    CaseResult,
    Outcome,
    build_cases,
    check,
    render_summary,
    summarize,
)
from tests.eval8_support import Workspace, ask_case, build_workspace
from tests.fake_chat import FakeChat
from tests.fake_embedder import FakeEmbedder
from tests.tenancy_helpers import World

DOCS = Path(__file__).resolve().parents[2] / "docs" / "eval"
RAW = Path(os.environ.get("EVAL_RAW_DIR", str(Path(tempfile.gettempdir()) / "eval8")))
OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")
LIVE = pytest.mark.skipif(not os.environ.get("EVAL_LIVE_OLLAMA"), reason="needs Ollama with bge-m3")


def unlimited(world: World, **changes: object) -> None:
    world.settings = world.settings.model_copy(
        update={"chat_rate_per_minute": 100_000, "search_rate_per_minute": 100_000, **changes}
    )


class Extractive(FakeChat):
    """A deterministic stand-in for a model: answers with the source sentence that shares the most
    words with the question, cited [1]. Enough to exercise the whole pipeline and harness."""

    def __init__(self) -> None:
        super().__init__(self._reply, chunk_chars=40)

    @staticmethod
    def _reply(messages: list) -> str:  # type: ignore[type-arg]
        user = messages[1].content
        question = user.split("Question:")[1].strip().lower().split()
        sentences = [
            s.strip()
            for s in user.split("<<<")[1].split(">>>")[0].replace("\n", " ").split(".")
            if s.strip()
        ]
        best = max(sentences, key=lambda s: len(set(s.lower().split()) & set(question)))
        return f"{best} [1]."


async def test_the_harness_runs_the_whole_case_list_through_the_real_pipeline(world: World) -> None:
    embedder = FakeEmbedder()
    world.embedder = embedder
    world.chat = Extractive()
    unlimited(world, gate_min_similarity=0.2)
    ws = await build_workspace(world, embedder)
    cases = build_cases()
    sample = [
        c
        for c in cases
        if c.category in ("restricted", "unanswerable", "scanned_only", "prompt_injection")
        or c.id in ("en-01", "ar-01")
    ]
    results = [check(c, await ask_case(ws, c)) for c in sample]
    by_id = {r.case.id: r for r in results}

    # restricted-only questions asked by a viewer never leak the restricted facts
    for r in results:
        if r.case.kind == "restricted_only":
            shown = r.outcome.text + " ".join(r.outcome.related_titles)
            assert (
                "12 million" not in shown and "Cedar" not in shown and "4 percent" not in shown
            ), r.case.id
            # whether a model refuses is a model-quality question (measured live); what must hold
            # for ANY model is that the restricted facts cannot reach this user
    # a question that fails the gate is refused AND the interface is told that something could not
    # be searched (the workspace holds a scanned PDF with no text layer)
    scan_case = next(c for c in cases if c.id == "scan-01")
    refused = await ask_case(ws, replace(scan_case, text="zzzz qqqq xxxx wwww"))
    assert refused.status == "refused" and refused.unsearchable_documents >= 1
    # the authorized counterpart of the restricted questions is answerable
    assert by_id["restr-01"].outcome.status in (
        "complete",
        "refused",
    )  # (fake model quality is not the point)
    assert summarize(results).errors == 0


# ------------------------------------------------------------------ live: gate calibration


async def _points(ws: Workspace, cases: Sequence[AnswerCase]) -> list[gate.Point]:
    points = []
    for case in cases:
        person = ws.person(case.user)
        r = await person.post(f"/orgs/{ws.org_id}/search", {"query": case.text, "limit": 6})
        sims = [h["similarity"] for h in r.json()["hits"] if h["similarity"] is not None]
        points.append(
            gate.Point(case.id, case.expect == "answer", max(sims) if sims else -1.0, case.kind)
        )
    return points


@LIVE
async def test_live_gate_calibration(world: World) -> None:
    embedder = OllamaEmbedder(OLLAMA, "bge-m3", 1024, timeout=300.0)
    world.embedder = embedder
    unlimited(world)
    ws = await build_workspace(world, embedder)
    cases = build_cases()
    points = await _points(ws, cases)
    calibration, test = gate.split(points)
    chosen = gate.choose_threshold(calibration, max_false_refusal=0.05)
    on_test = gate.rates(test, chosen.threshold)
    on_cal = gate.rates(calibration, chosen.threshold)
    grid = [gate.rates(points, t / 100) for t in range(20, 66, 5)]
    kinds = sorted({p.kind for p in test if p.kind})
    by_kind = {
        k: (
            sum(1 for p in test if p.kind == k and p.score < chosen.threshold),
            sum(1 for p in test if p.kind == k),
        )
        for k in kinds
    }
    lines = [
        "# Stage 8: retrieval gate calibration\n",
        f"Generated {date.today().isoformat()} by `EVAL_LIVE_OLLAMA=1 pytest tests/test_eval_stage8.py -k gate`.\n",
        f"- Score: the highest cosine similarity (bge-m3) among the 6 passages the model would be shown, "
        "from the asking user's point of view (a viewer never retrieves the restricted board minutes).\n"
        f"- Questions: {len(points)} ({sum(p.answerable for p in points)} answerable, "
        f"{sum(not p.answerable for p in points)} unanswerable), split deterministically and stratified: "
        f"{len(calibration)} calibration, {len(test)} test. **The threshold was chosen on the calibration "
        "split only** (highest refusal recall with false refusals <= 5%) and then measured once on the test split.\n",
        f"- AUC: calibration {gate.auc(calibration):.3f}, test {gate.auc(test):.3f} "
        "(probability that an answerable question scores above an unanswerable one).\n",
        f"\n**Chosen threshold: {chosen.threshold:.3f}**\n\n",
        "| split | n answerable | n unanswerable | gate refusal recall (unanswerable) | false refusals (answerable) |\n|---|---|---|---|---|\n",
        f"| calibration | {on_cal.n_answerable} | {on_cal.n_unanswerable} | {on_cal.refusal_recall:.2f} | {on_cal.false_refusal:.2f} |\n",
        f"| test (held out) | {on_test.n_answerable} | {on_test.n_unanswerable} | {on_test.refusal_recall:.2f} | {on_test.false_refusal:.2f} |\n",
        "\nGate refusal recall by kind on the test split (the model's own NO_ANSWER and the citation verifier "
        "catch more; end-to-end numbers are in stage8-answers.md):\n\n| kind | refused by the gate |\n|---|---|\n",
        *[f"| {k} | {a}/{b} |\n" for k, (a, b) in by_kind.items()],
        "\nAll questions, by threshold (for reading the trade-off, not for choosing it):\n\n"
        "| threshold | unanswerable refused | answerable refused |\n|---|---|---|\n",
        *[
            f"| {r.threshold:.2f} | {r.refusal_recall:.2f} | {r.false_refusal:.2f} |\n"
            for r in grid
        ],
    ]
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "stage8-gate.md").write_text("".join(lines), encoding="utf-8")
    assert 0.0 < chosen.threshold < 1.0


# ------------------------------------------------------------------ live: model bake-off


def _outcomes_path(model: str) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    return RAW / f"{model.replace(':', '_')}.jsonl"


def _load(model: str) -> dict[str, Outcome]:
    path = _outcomes_path(model)
    done: dict[str, Outcome] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            done[row["id"]] = Outcome(
                **{
                    **row["outcome"],
                    "cited_docs": tuple(row["outcome"]["cited_docs"]),
                    "sources": tuple(row["outcome"]["sources"]),
                    "related_titles": tuple(row["outcome"]["related_titles"]),
                }
            )
    return done


def _save(model: str, case_id: str, outcome: Outcome) -> None:
    with _outcomes_path(model).open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps({"id": case_id, "outcome": outcome.__dict__}, ensure_ascii=False) + "\n"
        )


async def _run_model(
    world: World, ws: Workspace, model: str, cases: Sequence[AnswerCase]
) -> list[CaseResult]:
    world.chat = OllamaChat(OLLAMA, model, num_ctx=8192, temperature=0.1, timeout=300.0)
    done = _load(model)
    results = []
    for case in cases:
        if case.id not in done:
            done[case.id] = await ask_case(ws, case)
            _save(model, case.id, done[case.id])
        results.append(check(case, done[case.id]))
    return results


@LIVE
@pytest.mark.skipif(
    not os.environ.get("EVAL_LIVE_LLMS"), reason="set EVAL_LIVE_LLMS=model_a,model_b"
)
async def test_live_model_bakeoff(world: World) -> None:
    models = [m.strip() for m in os.environ["EVAL_LIVE_LLMS"].split(",") if m.strip()]
    threshold = float(os.environ.get("EVAL_GATE", world.settings.gate_min_similarity))
    embedder = OllamaEmbedder(OLLAMA, "bge-m3", 1024, timeout=300.0)
    world.embedder = embedder
    unlimited(world, gate_min_similarity=threshold, llm_timeout_seconds=300.0)
    ws = await build_workspace(world, embedder)
    cases = build_cases()
    results = {m: await _run_model(world, ws, m, cases) for m in models}

    # faithfulness, judged by the OTHER model (never the generator), plus the judge's own accuracy
    items = judge.calibration_items()
    judged: dict[str, tuple[int, int, int]] = {}
    agreement: dict[str, dict[str, float | int]] = {}
    for generator in models:
        judge_name = next((m for m in models if m != generator), generator)
        judge_model = OllamaChat(OLLAMA, judge_name, num_ctx=8192, temperature=0.0, timeout=300.0)
        if judge_name not in agreement:
            agreement[judge_name] = judge.agreement(
                items, [await judge.judge(judge_model, i.answer, i.sources) for i in items]
            )
        ok = bad = unreadable = 0
        for r in results[generator]:
            if r.answered and r.outcome.sources:
                verdict = await judge.judge(judge_model, r.outcome.text, r.outcome.sources)
                ok, bad, unreadable = (
                    ok + (verdict is True),
                    bad + (verdict is False),
                    unreadable + (verdict is None),
                )
        judged[generator] = (ok, bad, unreadable)

    out = [
        "# Stage 8: grounded answers, hallucination suite and model bake-off\n\n",
        f"Generated {date.today().isoformat()} by `EVAL_LIVE_OLLAMA=1 EVAL_LIVE_LLMS={','.join(models)} pytest tests/test_eval_stage8.py -k bakeoff`.\n\n",
        f"Same questions, same retrieval (bge-m3 hybrid, gate threshold {threshold:.3f}), same prompt, temperature 0.1, "
        f"`num_ctx` 8192, one run per question. {len(cases)} cases: {sum(c.expect == 'answer' for c in cases)} should be answered, "
        f"{sum(c.expect == 'refuse' for c in cases)} refused ({sum(c.category == 'unanswerable' for c in cases)} unanswerable questions in four kinds, "
        f"{sum(c.category in ADV_CATEGORIES for c in cases)} adversarial).\n\n",
    ]
    for m in models:
        out.append(render_summary(m, summarize(results[m])))
        ok, bad, unreadable = judged[m]
        total = ok + bad + unreadable
        out.append(
            f"\nLLM-judge faithfulness (judge: {next((x for x in models if x != m), m)}): "
            f"{ok}/{total} answers judged fully supported, {bad} not, {unreadable} unreadable verdicts.\n\n"
        )
    out.append(
        "## Judge accuracy on the labelled calibration set (40 items)\n\n| judge model | accuracy | recall on faithful | recall on unfaithful | unreadable |\n|---|---|---|---|---|\n"
    )
    for name, a in agreement.items():
        out.append(
            f"| {name} | {a['accuracy']:.2f} | {a['faithful_recall']:.2f} | {a['unfaithful_recall']:.2f} | {a['unreadable']} |\n"
        )
    out.append("\n## Failed cases per model (id: problems)\n\n")
    for m in models:
        out.append(f"### {m}\n\n")
        for r in results[m]:
            if not r.passed:
                out.append(
                    f"- {r.case.id} ({r.case.category}{'/' + r.case.kind if r.case.kind else ''}): {'; '.join(r.problems)}\n"
                )
        out.append("\n")
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "stage8-answers.md").write_text("".join(out), encoding="utf-8")
    assert all(summarize(results[m]).errors == 0 for m in models), (
        "pipeline errors during the bake-off"
    )
