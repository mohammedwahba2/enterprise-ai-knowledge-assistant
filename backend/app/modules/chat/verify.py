"""Deterministic citation verification (PLAN section 7.2, step 7).

The model's citations are claims, not facts. For every cited sentence we check that:
  * the marker maps to a source that was actually supplied (otherwise it is removed),
  * every number in the sentence occurs in the cited passage (numeric traps and invented figures),
  * the sentence is supported by the passage: it shares enough words with it, or - for answers in
    another language than the source - it is semantically close (embedding similarity).
Unsupported sentences lose their markers and the answer is flagged partially supported; an answer
with no supported citation at all is not shown as an answer.
"""

import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from app.modules.processing.arabic import fold_digits, search_normalize

_MARKER = re.compile(r"\[\s*(\d{1,2}(?:\s*[,،]\s*\d{1,2})*)\s*\]")
_SENTENCE_END = re.compile(r"(?<=[.!?؟…])\s+|\n+")
_WORD = re.compile(r"\w+", re.UNICODE)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")

Similarity = Callable[[Sequence[str], Sequence[str]], Awaitable[list[float]]]
"""Pairwise cosine similarity of two equally long text lists (the embedder, in production)."""


@dataclass(frozen=True)
class SourceText:
    marker: int
    text: str  # the passage as shown to the model


@dataclass
class Citation:
    marker: int
    support: float  # best support score of the sentences that cite it (0..1)


@dataclass
class Verification:
    text: str  # the answer with invalid and unsupported markers removed
    citations: list[Citation] = field(default_factory=list)
    invalid_markers: list[int] = field(default_factory=list)
    unsupported_sentences: list[str] = field(default_factory=list)
    uncited_unsupported: list[str] = field(default_factory=list)
    cited_sentences: int = 0

    @property
    def has_support(self) -> bool:
        return bool(self.citations)

    @property
    def partially_supported(self) -> bool:
        return bool(self.unsupported_sentences or self.uncited_unsupported or self.invalid_markers)


def numbers_of(text: str) -> set[str]:
    """Numbers as comparable strings: digit scripts folded, thousands separators dropped."""
    folded = fold_digits(text)
    return {n.replace(",", "") for n in _NUMBER.findall(folded)}


def _tokens(text: str) -> set[str]:
    return {t for t in _WORD.findall(search_normalize(text)) if len(t) >= 3 and not t.isdigit()}


def _lexical_coverage(sentence: str, passage: str) -> float:
    wanted = _tokens(sentence)
    if not wanted:
        return 0.0
    return len(wanted & _tokens(passage)) / len(wanted)


def _split(text: str) -> list[str]:
    return [s for s in (part.strip() for part in _SENTENCE_END.split(text)) if s]


def _markers_in(sentence: str) -> list[int]:
    found: list[int] = []
    for match in _MARKER.finditer(fold_digits(sentence)):
        found.extend(int(n) for n in re.split(r"\s*[,،]\s*", match.group(1)))
    return found


def _strip_markers(sentence: str, remove: set[int] | None = None) -> str:
    """Remove markers (all of them, or only those numbered in `remove`)."""

    def replace(match: re.Match[str]) -> str:
        nums = [int(n) for n in re.split(r"\s*[,،]\s*", fold_digits(match.group(1)))]
        if remove is None or all(n in remove for n in nums):
            return ""
        keep = [n for n in nums if n not in remove]
        return "[" + ", ".join(str(n) for n in keep) + "]"

    return re.sub(r"\s+([.!?؟…])", r"\1", _MARKER.sub(replace, sentence)).strip()


@dataclass
class _Sentence:
    raw: str
    plain: str
    valid: list[int]  # markers that map to a supplied source, in order of appearance
    invalid: set[int]
    supported: dict[int, float] = field(default_factory=dict)  # marker -> support score


async def verify(
    answer: str,
    sources: Sequence[SourceText],
    *,
    min_lexical: float,
    min_similarity: float,
    similarity: Similarity | None = None,
) -> Verification:
    by_marker = {s.marker: s for s in sources}
    all_numbers: set[str] = set()
    for source in sources:
        all_numbers |= numbers_of(source.text)

    # Pass 1: parse; score each (sentence, marker) pair by numbers and shared words.
    sentences: list[_Sentence] = []
    semantic: list[tuple[_Sentence, int]] = []  # pairs worth a semantic check
    for raw in _split(answer):
        markers = _markers_in(raw)
        sentence = _Sentence(
            raw=raw,
            plain=_strip_markers(raw),
            valid=[m for m in dict.fromkeys(markers) if m in by_marker],
            invalid={m for m in markers if m not in by_marker},
        )
        sentence_numbers = numbers_of(sentence.plain)
        for marker in sentence.valid:
            passage = by_marker[marker].text
            if not sentence_numbers <= numbers_of(passage):
                continue  # a figure the passage does not contain: never supported by it
            lexical = _lexical_coverage(sentence.plain, passage)
            if lexical >= min_lexical:
                sentence.supported[marker] = min(1.0, lexical)
            else:
                semantic.append((sentence, marker))
        sentences.append(sentence)

    # Pass 2: semantic fallback for pairs that share no words (answers in another language).
    if semantic and similarity is not None:
        scores = await similarity(
            [pair[0].plain for pair in semantic], [by_marker[pair[1]].text for pair in semantic]
        )
        for (sentence, marker), score in zip(semantic, scores, strict=True):
            if score >= min_similarity:
                sentence.supported[marker] = max(
                    sentence.supported.get(marker, 0.0), min(1.0, score)
                )

    # Pass 3: rebuild the text; drop markers that are invalid or unsupported.
    result = Verification(text="")
    kept: list[str] = []
    best: dict[int, float] = {}
    for sentence in sentences:
        result.invalid_markers.extend(sentence.invalid)
        if not sentence.valid:
            kept.append(
                _strip_markers(sentence.raw, sentence.invalid) if sentence.invalid else sentence.raw
            )
            if numbers_of(sentence.plain) - all_numbers:
                result.uncited_unsupported.append(sentence.plain)  # figures no source contains
            continue
        result.cited_sentences += 1
        unsupported = set(sentence.valid) - set(sentence.supported)
        if not sentence.supported:
            result.unsupported_sentences.append(sentence.plain)
        kept.append(_strip_markers(sentence.raw, sentence.invalid | unsupported))
        for marker, score in sentence.supported.items():
            best[marker] = max(best.get(marker, 0.0), score)
    result.text = " ".join(kept).strip()
    result.invalid_markers = sorted(set(result.invalid_markers))
    result.citations = [Citation(m, best[m]) for m in sorted(best)]
    return result
