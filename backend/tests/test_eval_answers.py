"""The answer checks, summary and gate calibration, against hand-built cases."""

import pytest

from evals import gate
from evals.answers import AnswerCase, Outcome, build_cases, check, summarize

LEAVE = AnswerCase("q", "q", "en", "en_factoid", "answer", keys=(("25",),), gold_docs=("leave",))


def done(text: str, docs: tuple[str, ...] = ("leave",), **kw: object) -> Outcome:
    return Outcome("complete", text, cited_docs=docs, **kw)  # type: ignore[arg-type]


# ------------------------------------------------------------------ checks


def test_numbers_are_compared_by_value_across_digit_scripts_not_as_substrings() -> None:
    assert check(LEAVE, done("They receive 25 working days [1].")).passed
    assert check(LEAVE, done("يحصلون على ٢٥ يوماً [1].")).passed  # Arabic-Indic digits
    assert not check(LEAVE, done("They receive 250 days [1].")).passed  # 250 is not 25
    assert not check(LEAVE, done("They receive 125 days [1].")).passed
    assert check(LEAVE, done("The cap is 25,000.")).passed is False  # 25000 is not 25


def test_an_answer_must_cite_a_gold_document() -> None:
    result = check(LEAVE, done("25 days [1].", docs=("other",)))
    assert not result.passed and "did not cite a gold document" in result.problems


def test_text_keys_accept_any_alternative_and_every_group_is_required() -> None:
    case = AnswerCase(
        "q",
        "q",
        "ar",
        "ar_factoid",
        "answer",
        keys=(("الدمام", "dammam"), ("2", "ساعتين")),
        gold_docs=("d",),
    )
    assert check(case, done("المركز في الدمام ويبلغ العملاء خلال ساعتين", docs=("d",))).passed
    assert check(case, done("It is in Dammam, within 2 hours", docs=("d",))).passed
    missing = check(case, done("المركز في الدمام", docs=("d",)))
    assert not missing.passed and "missing key fact '2'" in missing.problems[0]


def test_refusing_an_answerable_question_and_answering_an_unanswerable_one_both_fail() -> None:
    assert "refused an answerable question" in check(LEAVE, Outcome("refused")).problems
    unanswerable = AnswerCase("u", "u", "en", "unanswerable", "refuse", needs_citation=False)
    assert check(unanswerable, Outcome("refused")).passed
    assert "answered an unanswerable question" in check(unanswerable, done("It is 12.")).problems


def test_a_pipeline_error_is_never_a_pass() -> None:
    assert not check(LEAVE, Outcome("error", refusal_reason="LLM_UNAVAILABLE")).passed
    unanswerable = AnswerCase("u", "u", "en", "unanswerable", "refuse", needs_citation=False)
    assert not check(unanswerable, Outcome("error")).passed  # an outage is not a correct refusal


def test_forbidden_phrases_and_figures_are_caught_in_answers_and_related_titles() -> None:
    trap = AnswerCase(
        "t",
        "t",
        "en",
        "numeric_trap",
        "answer",
        keys=(("1200",),),
        forbidden_numbers=("800",),
        gold_docs=("l",),
    )
    assert check(trap, done("The cap is SAR 1,200 per night [1].", docs=("l",))).passed
    assert not check(trap, done("It is 1,200, not like the domestic 800 [1].", docs=("l",))).passed
    secret = AnswerCase(
        "s", "s", "en", "unanswerable", "refuse", forbidden=("Cedar",), needs_citation=False
    )
    assert not check(secret, Outcome("refused", related_titles=("Project Cedar minutes",))).passed


def test_a_superseded_figure_is_only_acceptable_when_its_version_is_named() -> None:
    case = AnswerCase("c", "c", "en", "conflicting_versions", "answer", keys=(("300",),),
                      forbidden_unless=(("250", ("2023", "superseded")),), gold_docs=("d",))  # fmt: skip
    assert check(case, done("It is SAR 300 [1].", docs=("d",))).passed
    assert check(case, done("SAR 300 now; the 2023 version said 250 [1].", docs=("d",))).passed
    assert not check(case, done("SAR 300, or 250 [1].", docs=("d",))).passed


def test_identifier_questions_are_checked_by_the_document_they_cite() -> None:
    case = next(c for c in build_cases() if c.category == "identifier")
    assert case.keys == () and case.gold_docs


# ------------------------------------------------------------------ cases and summary


def test_every_question_and_adversarial_case_becomes_a_case_with_a_sound_expectation() -> None:
    cases = build_cases()
    ids = [c.id for c in cases]
    assert len(ids) == len(set(ids))
    unanswerable = [c for c in cases if c.category == "unanswerable"]
    assert len(unanswerable) >= 60  # PLAN 11.7
    assert {c.kind for c in unanswerable} == {
        "off_topic",
        "absent",
        "plausible_absent",
        "near_miss",
        "restricted_only",
    }
    assert all(c.expect == "refuse" for c in unanswerable)
    restricted_only = [c for c in unanswerable if c.kind == "restricted_only"]
    assert len(restricted_only) >= 8 and all(c.user == "viewer" for c in restricted_only)
    assert (
        next(c for c in cases if c.id == "restr-01").user == "owner"
    )  # the authorized counterpart
    answerable = [c for c in cases if c.expect == "answer" and c.category not in ("identifier",)]
    assert all(c.keys for c in answerable), "every answerable case needs a checkable key fact"
    assert {c.category for c in cases} >= {
        "prompt_injection",
        "conflicting_versions",
        "numeric_trap",
        "pressure_to_guess",
        "scanned_only",
    }


def test_the_summary_counts_what_the_targets_are_about() -> None:
    answerable_ok = check(
        LEAVE, done("25 days [1].", first_token_ms=800, latency_ms=3000, language="en")
    )
    answerable_refused = check(LEAVE, Outcome("refused"))
    un = AnswerCase(
        "u", "u", "en", "unanswerable", "refuse", kind="near_miss", needs_citation=False
    )
    refused = check(un, Outcome("refused"))
    hallucinated = check(un, done("It is 12.", docs=(), language="en"))
    s = summarize([answerable_ok, answerable_refused, refused, hallucinated])
    assert (s.answerable, s.answered_correct, s.false_refusals) == (2, 1, 1)
    assert (s.unanswerable, s.refused_correctly) == (2, 1)
    assert s.unanswerable_by_kind == {"near_miss": (1, 2)}
    assert s.citation_precision == 1.0 and s.citation_recall == 1.0
    assert s.ttft_p50 == 800 and s.errors == 0


# ------------------------------------------------------------------ gate calibration


def pts() -> list[gate.Point]:
    return [
        gate.Point("a1", True, 0.9), gate.Point("a2", True, 0.8), gate.Point("a3", True, 0.7),
        gate.Point("a4", True, 0.4),
        gate.Point("u1", False, 0.5), gate.Point("u2", False, 0.3), gate.Point("u3", False, 0.2),
        gate.Point("u4", False, 0.1),
    ]  # fmt: skip


def test_auc_matches_the_pairwise_definition() -> None:
    # answerable > unanswerable in 15 of 16 pairs (only 0.4 vs 0.5 loses)
    assert gate.auc(pts()) == pytest.approx(15 / 16)
    assert (
        gate.auc([gate.Point("a", True, 0.5), gate.Point("u", False, 0.5)]) == 0.5
    )  # ties count half
    with pytest.raises(ValueError):
        gate.auc([gate.Point("a", True, 0.5)])


def test_rates_refuse_below_the_threshold() -> None:
    r = gate.rates(pts(), 0.45)
    assert (r.refusal_recall, r.false_refusal) == (0.75, 0.25)  # u2,u3,u4 refused; a4 refused
    assert (
        gate.rates(pts(), 0.0).refusal_recall == 0.0 and gate.rates(pts(), 1.0).false_refusal == 1.0
    )


def test_the_chosen_threshold_is_the_most_protective_one_within_the_false_refusal_bound() -> None:
    chosen = gate.choose_threshold(pts(), max_false_refusal=0.0)
    assert chosen.false_refusal == 0.0 and chosen.refusal_recall == 0.75
    assert chosen.threshold == pytest.approx(0.35)  # midway between 0.3 (refuse) and 0.4 (answer)
    loose = gate.choose_threshold(pts(), max_false_refusal=0.25)
    assert loose.refusal_recall == 1.0 and loose.false_refusal == 0.25
    with pytest.raises(ValueError):
        gate.choose_threshold([gate.Point("a", True, -1.0), gate.Point("u", False, 0.5)], -0.1)


def test_the_split_is_deterministic_stratified_and_disjoint() -> None:
    many = [gate.Point(f"a{i}", True, 0.5) for i in range(20)] + [
        gate.Point(f"u{i}", False, 0.2) for i in range(20)
    ]
    cal, test = gate.split(many)
    assert gate.split(many) == (cal, test)  # deterministic
    assert not {p.case_id for p in cal} & {p.case_id for p in test}
    assert len(cal) + len(test) == 40
    for half in (cal, test):
        assert sum(p.answerable for p in half) == 10 and sum(not p.answerable for p in half) == 10


def test_the_product_gate_default_is_the_threshold_the_calibration_report_chose() -> None:
    import re
    from pathlib import Path

    from app.core.config import Settings

    report = Path(__file__).resolve().parents[2] / "docs" / "eval" / "stage8-gate.md"
    match = re.search(r"Chosen threshold: ([0-9.]+)", report.read_text(encoding="utf-8"))
    assert match is not None, "the calibration report must state the chosen threshold"
    chosen = float(match.group(1))
    assert Settings().gate_min_similarity == pytest.approx(chosen, abs=0.005)
