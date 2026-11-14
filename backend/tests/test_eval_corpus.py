"""The evaluation corpus and question set are test fixtures too: they must be internally sound,
or every metric computed from them is wrong."""

from collections import Counter

import pytest

from app.modules.processing.arabic import search_normalize
from app.modules.processing.chunker import Page, chunk_pages
from app.modules.processing.parsers import parse_text
from evals.corpus import CATEGORIES, build_corpus, load_questions

DOCS = {d.slug: d for d in build_corpus()}
QUESTIONS = load_questions()


def test_corpus_has_unique_slugs_languages_and_synthetic_marker() -> None:
    slugs = [d.slug for d in build_corpus()]
    assert len(slugs) == len(set(slugs)) == 34
    assert {d.language for d in DOCS.values()} == {"ar", "en", "mixed"}
    # every document says it is synthetic: this repository never contains real company data
    assert all("synthetic" in d.text.lower() or "افتراضية" in d.text for d in DOCS.values())


def test_every_variant_differs_from_its_base_so_it_is_a_real_hard_negative() -> None:
    for slug, doc in DOCS.items():
        if "__" not in slug:
            continue
        base = DOCS[slug.split("__")[0]]
        assert doc.text != base.text
        # same structure and wording, different numbers
        assert len(doc.text.splitlines()) == len(base.text.splitlines())
        base_digits = [c for c in base.text if c.isdigit()]
        assert [c for c in doc.text if c.isdigit()] != base_digits, slug


def test_question_ids_are_unique_and_categories_are_known() -> None:
    ids = [q.id for q in QUESTIONS]
    assert len(ids) == len(set(ids))
    assert {q.category for q in QUESTIONS} <= set(CATEGORIES)
    assert len(QUESTIONS) >= 60


def test_every_category_and_language_pair_is_covered() -> None:
    counts = Counter(q.category for q in QUESTIONS)
    assert set(counts) == set(CATEGORIES)
    minimum = {"en_factoid": 12, "ar_factoid": 12, "cross_ar_to_en": 8, "cross_en_to_ar": 8}
    for category, n in minimum.items():
        assert counts[category] >= n, category
    assert {q.lang for q in QUESTIONS} == {"ar", "en"}


@pytest.mark.parametrize("question", QUESTIONS, ids=lambda q: q.id)
def test_gold_evidence_exists_in_the_gold_document_and_nowhere_else(question) -> None:  # type: ignore[no-untyped-def]
    gold_docs = {g.doc for g in question.gold}
    for gold in question.gold:
        assert gold.doc in DOCS, f"unknown document {gold.doc}"
        needle = search_normalize(gold.evidence)
        assert needle in DOCS[gold.doc].search_text, "evidence phrase not in the document"
        others = [s for s, d in DOCS.items() if s not in gold_docs and needle in d.search_text]
        assert not others, f"evidence is ambiguous, also in {others}"


@pytest.mark.parametrize("question", [q for q in QUESTIONS if q.gold], ids=lambda q: q.id)
def test_gold_evidence_lies_wholly_inside_one_real_chunk(question) -> None:  # type: ignore[no-untyped-def]
    """Judging is chunk-level: an evidence phrase cut by a chunk boundary would be unfindable."""
    for gold in question.gold:
        pages = [Page(p.number, p.text) for p in parse_text(DOCS[gold.doc].text.encode())]
        needle = search_normalize(gold.evidence)
        assert any(needle in c.content_search for c in chunk_pages(pages))


def test_question_kinds_are_what_they_claim_to_be() -> None:
    for q in QUESTIONS:
        gold_langs = {DOCS[g.doc].language for g in q.gold}
        if q.category == "cross_ar_to_en":
            assert q.lang == "ar" and gold_langs == {"en"}
        if q.category == "cross_en_to_ar":
            assert q.lang == "en" and gold_langs == {"ar"}
        if q.category == "unanswerable":
            assert not q.gold
        else:
            assert q.gold, q.id


def test_digit_variant_groups_ask_the_same_question_in_all_three_digit_styles() -> None:
    groups: dict[str, list] = {}  # type: ignore[type-arg]
    for q in QUESTIONS:
        if q.category == "digit_variant":
            assert q.group
            groups.setdefault(q.group, []).append(q)
    assert len(groups) >= 4
    for name, members in groups.items():
        assert len(members) == 3, name
        assert len({m.gold for m in members}) == 1  # identical gold
        # they differ as typed but are the same once normalized
        assert len({m.text for m in members}) == 3
        assert len({search_normalize(m.text) for m in members}) == 1, name


def test_the_restricted_document_carries_a_canary_that_exists_nowhere_else() -> None:
    restricted = [d for d in DOCS.values() if d.restricted]
    assert [d.slug for d in restricted] == ["board_minutes_restricted_en"]
    canary = "CANARY-7F3A-ZEBRA-LANTERN"
    assert canary in restricted[0].text
    assert all(canary not in d.text for d in DOCS.values() if not d.restricted)
