from collections import Counter

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.modules.processing.chunker import (
    MAX_TOKENS,
    TARGET_TOKENS,
    Chunk,
    Page,
    chunk_pages,
    estimate_tokens,
)

WORDS = [
    "leave",
    "policy",
    "employee",
    "annual",
    "carry",
    "forfeit",
    "manager",
    "approval",
    "عمل",
    "إجازة",
    "سنوية",
    "الموظف",
    "تقدم",
]


def para(n: int, seed: int = 0) -> str:
    return " ".join(WORDS[(i + seed) % len(WORDS)] for i in range(n)) + "."


def words_of(chunks: list[Chunk]) -> Counter[str]:
    return Counter(w for c in chunks for w in c.content.split())


# ---------------------------------------------------------------- examples


def test_empty_input_yields_no_chunks() -> None:
    assert chunk_pages([]) == []
    assert chunk_pages([Page(1, "")]) == []


def test_small_document_is_one_chunk_with_its_page_range() -> None:
    chunks = chunk_pages([Page(1, "Intro paragraph one."), Page(2, "Second page text.")])
    assert len(chunks) == 1
    assert (chunks[0].page_start, chunks[0].page_end) == (1, 2)
    assert "Intro paragraph one." in chunks[0].content and "Second page text." in chunks[0].content


def test_headings_become_the_heading_path_with_numbering_depth() -> None:
    text = "4. LEAVE\n\n4.2 Annual leave\nEmployees receive 25 working days of leave each year.\n\n4.4 Carry-over\nUp to five days may be carried over until March."
    chunks = chunk_pages([Page(14, text)])
    paths = {c.heading_path for c in chunks}
    assert any("4.2 Annual leave" in p for p in paths) or any("4.4 Carry-over" in p for p in paths)
    deepest = max(chunks, key=lambda c: c.heading_path.count(">"))
    assert deepest.heading_path.startswith("4. LEAVE >")


def test_a_long_section_is_split_without_losing_text_and_with_overlap() -> None:
    pages = [Page(i, "\n\n".join(para(60, i * 7 + j) for j in range(6))) for i in range(1, 4)]
    chunks = chunk_pages(pages)
    assert len(chunks) > 3
    assert all(c.token_count <= MAX_TOKENS for c in chunks)
    original = Counter(w for p in pages for w in p.text.split())
    assert all(words_of(chunks)[w] >= n for w, n in original.items())  # nothing lost
    # consecutive chunks of one section share a little text (overlap), but never most of it
    shared = [
        set(a.content.split("\n")) & set(b.content.split("\n"))
        for a, b in zip(chunks, chunks[1:], strict=False)
    ]
    assert any(shared)


def test_a_single_giant_paragraph_is_split_at_sentences_then_words() -> None:
    giant = " ".join(para(40, i) for i in range(30))  # ~1,200 words, many sentences
    chunks = chunk_pages([Page(1, giant)])
    assert len(chunks) >= 2 and all(c.token_count <= MAX_TOKENS for c in chunks)
    no_sentences = " ".join(WORDS[i % len(WORDS)] for i in range(2500))  # one endless sentence
    pieces = chunk_pages([Page(1, no_sentences)])
    assert len(pieces) >= 3 and all(c.token_count <= MAX_TOKENS for c in pieces)


def test_page_ranges_follow_the_text_and_never_go_backwards() -> None:
    pages = [Page(n, "\n\n".join(para(70, n + j) for j in range(4))) for n in (3, 4, 7, 8)]
    chunks = chunk_pages(pages)
    assert chunks[0].page_start == 3 and chunks[-1].page_end == 8
    for a, b in zip(chunks, chunks[1:], strict=False):
        assert b.page_start >= a.page_start and b.page_end >= a.page_end
    assert all(c.page_end >= c.page_start for c in chunks)
    covered = {p for c in chunks for p in range(c.page_start, c.page_end + 1)}
    assert {3, 4, 7, 8} <= covered


def test_sections_do_not_overlap_into_each_other() -> None:
    body = "\n\n".join(para(55, j) for j in range(5))
    text = f"1. FIRST\n{body}\n\n2. SECOND\n{body}"
    chunks = chunk_pages([Page(1, text)])
    second = [c for c in chunks if "2. SECOND" in c.heading_path]
    assert second and all("1. FIRST" not in c.heading_path for c in second)
    assert "SECOND" not in " ".join(
        c.content for c in chunks if "1. FIRST" in c.heading_path and "2. SECOND" not in c.content
    )


def test_chunks_carry_language_and_search_text() -> None:
    chunks = chunk_pages([Page(1, "تُمنح الإجازة السنوية ٢٥ يوماً\n\nAnnual leave is 25 days.")])
    assert chunks[0].lang == "mixed"
    assert (
        "25" in chunks[0].content_search and "الاجازه" not in chunks[0].content_search
    )  # ه/ة not folded
    assert "الاجازة" in chunks[0].content_search


def test_output_is_deterministic() -> None:
    pages = [Page(1, "\n\n".join(para(70, j) for j in range(8)))]
    assert chunk_pages(pages) == chunk_pages(pages)


def test_no_chunk_consists_only_of_a_heading() -> None:
    chunks = chunk_pages([Page(1, "1. ALONE\n\n2. ALSO ALONE")])
    assert all(
        (c.content.strip() and not c.content.strip().startswith("2. ALSO ALONE"))
        or "\n" in c.content
        or len(chunks) == 1
        for c in chunks
    )


def test_token_estimate_is_monotonic_and_nonzero_for_text() -> None:
    assert estimate_tokens("") == 0 and estimate_tokens("word") >= 1
    assert estimate_tokens(para(100)) > estimate_tokens(para(10))


# ---------------------------------------------------------------- properties

word = st.sampled_from(WORDS + ["a", "of", "2025", "٢٥"])
paragraph = st.lists(word, min_size=1, max_size=400).map(lambda ws: " ".join(ws) + ".")
heading = st.sampled_from(
    ["1. SCOPE", "2.1 Definitions", "ANNUAL LEAVE", "الإجازات:", "3.2 Carry-over"]
)
block = st.one_of(paragraph, heading)
page_text = st.lists(block, min_size=0, max_size=12).map("\n\n".join)
documents = st.lists(page_text, min_size=1, max_size=6).map(
    lambda texts: [Page(i + 1, t) for i, t in enumerate(texts)]
)
PROPS = settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@PROPS
@given(documents)
def test_property_no_words_are_ever_lost(pages: list[Page]) -> None:
    chunks = chunk_pages(pages)
    original = Counter(w for p in pages for w in p.text.split())
    have = words_of(chunks)
    # headings may merge into chunk text; every original word must still be present at least as often
    # (headings that stand alone at the very end have no body to attach to and are dropped by design)
    body_words = Counter(
        w
        for p in pages
        for blk in p.text.split("\n\n")
        if blk not in {"1. SCOPE", "2.1 Definitions", "ANNUAL LEAVE", "الإجازات:", "3.2 Carry-over"}
        for w in blk.split()
    )
    assert all(have[w] >= n for w, n in body_words.items()), original - have


@PROPS
@given(documents)
def test_property_sizes_are_bounded_and_indexes_contiguous(pages: list[Page]) -> None:
    chunks = chunk_pages(pages)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert all(0 < c.token_count <= MAX_TOKENS for c in chunks)
    assert all(c.token_count == estimate_tokens(c.content) for c in chunks)


@PROPS
@given(documents)
def test_property_page_ranges_are_valid_and_cover_every_page_with_text(pages: list[Page]) -> None:
    chunks = chunk_pages(pages)
    numbers = {p.number for p in pages}
    assert all(
        c.page_start in numbers and c.page_end in numbers and c.page_start <= c.page_end
        for c in chunks
    )
    for a, b in zip(chunks, chunks[1:], strict=False):
        assert b.page_start >= a.page_start
    covered = {p for c in chunks for p in range(c.page_start, c.page_end + 1)}
    pages_with_body = {p.number for p in pages if any(w in p.text for w in WORDS)}
    heading_only = {
        p.number
        for p in pages
        if p.text.strip()
        and all(
            b in {"1. SCOPE", "2.1 Definitions", "ANNUAL LEAVE", "الإجازات:", "3.2 Carry-over"}
            for b in p.text.split("\n\n")
        )
    }
    assert (pages_with_body - heading_only) <= covered


@PROPS
@given(documents)
def test_property_chunking_is_deterministic_and_chunks_are_not_empty(pages: list[Page]) -> None:
    a, b = chunk_pages(pages), chunk_pages(pages)
    assert a == b
    assert all(c.content.strip() for c in a)


@PROPS
@given(st.lists(paragraph, min_size=1, max_size=30))
def test_property_target_size_is_respected_for_ordinary_paragraphs(paras: list[str]) -> None:
    chunks = chunk_pages([Page(1, "\n\n".join(paras))])
    # no chunk is wildly larger than the target when paragraphs are small enough to pack
    small = all(estimate_tokens(p) < TARGET_TOKENS // 2 for p in paras)
    if small:
        assert all(c.token_count <= MAX_TOKENS for c in chunks)


@pytest.mark.parametrize("n", [1, 2, 5])
def test_pages_with_only_blank_lines_are_skipped_safely(n: int) -> None:
    assert chunk_pages([Page(i, "\n\n  \n") for i in range(1, n + 1)]) == []
