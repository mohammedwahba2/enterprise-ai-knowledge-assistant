"""The retrieval metrics and harness, against hand-computed cases (no database)."""

import math

import pytest

from evals import metrics
from evals.corpus import CorpusDoc, Gold, Question
from evals.harness import Retrieved, evaluate, judge, render_markdown


def chunk(doc: str, text: str, index: int = 0, pages: tuple[int, int] = (1, 1)) -> Retrieved:
    return Retrieved(doc, index, pages[0], pages[1], text)


# ------------------------------------------------------------------ metrics


def test_recall_hit_and_reciprocal_rank_on_a_known_ranking() -> None:
    judged = [None, 0, None, 1, None]  # gold items 0 and 1 found at ranks 2 and 4
    assert metrics.recall_at_k(judged, 2, 1) == 0.0
    assert metrics.recall_at_k(judged, 2, 3) == 0.5
    assert metrics.recall_at_k(judged, 2, 5) == 1.0
    assert metrics.hit_at_k(judged, 1) == 0.0 and metrics.hit_at_k(judged, 2) == 1.0
    assert metrics.reciprocal_rank(judged) == 0.5
    assert metrics.reciprocal_rank([None, None]) == 0.0
    assert metrics.reciprocal_rank([None] * 10 + [0], k=10) == 0.0  # outside the cutoff


def test_ndcg_matches_the_textbook_formula() -> None:
    judged = [None, 0, None, 1]
    dcg = 1 / math.log2(3) + 1 / math.log2(5)
    ideal = 1 / math.log2(2) + 1 / math.log2(3)
    assert metrics.ndcg_at_k(judged, 2, 4) == pytest.approx(dcg / ideal)
    assert metrics.ndcg_at_k([0, 1], 2, 10) == pytest.approx(1.0)  # perfect ranking
    assert metrics.ndcg_at_k([None, None], 1, 10) == 0.0


def test_ndcg_ideal_is_capped_by_k() -> None:
    # 3 gold items but only the top 2 positions count: two hits at the top is already ideal
    assert metrics.ndcg_at_k([0, 1, None], 3, 2) == pytest.approx(1.0)


def test_metrics_refuse_to_score_questions_without_gold() -> None:
    with pytest.raises(ValueError):
        metrics.recall_at_k([], 0, 5)
    with pytest.raises(ValueError):
        metrics.ndcg_at_k([], 0, 5)


# ------------------------------------------------------------------ judging


def test_a_chunk_is_relevant_only_if_it_is_the_gold_document_and_contains_the_evidence() -> None:
    gold = [Gold("policy_en", "25 working days")]
    ranking = [
        chunk("other_en", "employees get 25 working days"),  # right words, wrong document
        chunk("policy_en", "employees get 21 working days"),  # right document, wrong fact
        chunk("policy_en", "employees get 25 working days", index=2),
    ]
    assert judge(ranking, gold) == [None, None, 0]


def test_each_gold_item_is_credited_once_to_the_best_ranked_chunk() -> None:
    gold = [Gold("a", "alpha"), Gold("a", "beta")]
    ranking = [chunk("a", "alpha"), chunk("a", "alpha again", 1), chunk("a", "beta", 2)]
    assert judge(ranking, gold) == [0, None, 1]


def test_evidence_matching_is_search_normalized_on_both_sides() -> None:
    gold = [Gold("doc", "الإجازة ٢٥ يوما")]  # hamza and Arabic-Indic digits in the evidence
    assert judge([chunk("doc", "الاجازة 25 يوما")], gold) == [0]


# ------------------------------------------------------------------ harness


def question(qid: str, text: str, gold: list[Gold], **kw: str | None) -> Question:
    return Question(
        id=qid,
        text=text,
        lang=kw.get("lang") or "en",
        category=kw.get("category") or "en_factoid",
        gold=tuple(gold),
        group=kw.get("group"),
    )


CORPUS = [CorpusDoc("a_en", "en", "a_en.md", "alpha"), CorpusDoc("b_ar", "ar", "b_ar.md", "beta")]
QUESTIONS = [
    question("q1", "first", [Gold("a_en", "alpha")]),
    question("q2", "second", [Gold("b_ar", "beta")], lang="en", category="cross_en_to_ar"),
    question("q3", "nothing", [], category="unanswerable"),
]


async def test_a_perfect_retriever_scores_one_and_unanswerable_questions_are_not_scored() -> None:
    async def perfect(q: Question) -> list[Retrieved]:
        return [chunk(g.doc, g.evidence) for g in q.gold]

    report = await evaluate("perfect", perfect, QUESTIONS, CORPUS)
    assert report.overall.n == 2 and report.unanswerable == 1
    assert report.overall.recall[1] == 1.0 and report.overall.mrr == 1.0
    assert report.overall.ndcg10 == pytest.approx(1.0) and report.failures == []
    assert set(report.by_category) == {"en_factoid", "cross_en_to_ar"}
    assert set(report.by_pair) == {"en->en", "en->ar"}


async def test_a_useless_retriever_scores_zero_and_lists_its_failures() -> None:
    async def useless(_q: Question) -> list[Retrieved]:
        return [chunk("a_en", "unrelated")]

    report = await evaluate("useless", useless, QUESTIONS, CORPUS)
    assert report.overall.recall[10] == 0.0 and report.overall.mrr == 0.0
    assert report.failures == ["q1", "q2"]


async def test_digit_consistency_detects_rankings_that_depend_on_the_digit_style() -> None:
    qs = [
        question("d1", "limit 25", [Gold("a_en", "alpha")], group="g", category="digit_variant"),
        question("d2", "limit ٢٥", [Gold("a_en", "alpha")], group="g", category="digit_variant"),
    ]

    async def stable(_q: Question) -> list[Retrieved]:
        return [chunk("a_en", "alpha")]

    async def digit_sensitive(q: Question) -> list[Retrieved]:
        return [chunk("a_en", "alpha")] if "25" in q.text else [chunk("b_ar", "beta")]

    assert (await evaluate("stable", stable, qs, CORPUS)).digit_consistency == 1.0
    assert (await evaluate("sensitive", digit_sensitive, qs, CORPUS)).digit_consistency == 0.0


async def test_the_markdown_report_has_every_section() -> None:
    async def perfect(q: Question) -> list[Retrieved]:
        return [chunk(g.doc, g.evidence) for g in q.gold]

    text = render_markdown([await evaluate("perfect", perfect, QUESTIONS, CORPUS)])
    for expected in ("### perfect", "| category", "| language pair", "en->ar", "| all | 2 | 1.00"):
        assert expected in text
