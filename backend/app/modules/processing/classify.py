"""Per-page and per-document extraction classification (PLAN section 7.6)."""

import unicodedata
from dataclasses import dataclass
from enum import StrEnum


class PageState(StrEnum):
    TEXT = "text"
    IMAGE_ONLY = "image_only"
    GARBLED = "garbled"


IMAGE_ONLY_RATIO = 0.5  # share of the page covered by images
MIN_MEANINGFUL_CHARS = 8  # fewer letters/digits than this means "no real text layer"
GARBLED_BAD_RATIO = 0.10  # replacement / private-use / unassigned characters
GARBLED_MIN_MEANINGFUL = 0.40  # share of non-space characters that must be letters or digits


def _is_bad(ch: str) -> bool:
    if ch == "�":
        return True
    return unicodedata.category(ch) in ("Co", "Cn", "Cs", "Cc") and ch not in "\n\t\r"


def classify_page(text: str, image_area_ratio: float) -> PageState:
    chars = [c for c in text if not c.isspace()]
    meaningful = sum(1 for c in chars if unicodedata.category(c)[0] in ("L", "N"))
    if meaningful < MIN_MEANINGFUL_CHARS and image_area_ratio >= IMAGE_ONLY_RATIO:
        return PageState.IMAGE_ONLY
    if not chars:
        return PageState.TEXT  # a genuinely blank page is not an extraction failure
    bad = sum(1 for c in chars if _is_bad(c))
    if bad / len(chars) >= GARBLED_BAD_RATIO or meaningful / len(chars) < GARBLED_MIN_MEANINGFUL:
        return PageState.GARBLED
    return PageState.TEXT


@dataclass(frozen=True)
class DocumentOutcome:
    status: str  # ready | ready_partial | unsupported_scanned | unsupported_garbled | failed
    error_code: str | None
    summary: dict[str, int]
    unusable_pages: tuple[int, ...]


def decide(states: list[tuple[int, PageState, int]]) -> DocumentOutcome:
    """Document verdict from (page_number, state, char_count). Never `ready` with silent gaps."""
    text = sum(1 for _, s, _ in states if s is PageState.TEXT)
    image = sum(1 for _, s, _ in states if s is PageState.IMAGE_ONLY)
    garbled = sum(1 for _, s, _ in states if s is PageState.GARBLED)
    summary = {"total": len(states), "text": text, "image_only": image, "garbled": garbled}
    unusable = tuple(n for n, s, _ in states if s is not PageState.TEXT)
    readable_chars = sum(c for _, s, c in states if s is PageState.TEXT)
    if readable_chars == 0:
        if image:
            return DocumentOutcome("unsupported_scanned", "NO_TEXT_LAYER", summary, unusable)
        if garbled:
            return DocumentOutcome("unsupported_garbled", "GARBLED_TEXT", summary, unusable)
        return DocumentOutcome("failed", "EMPTY_DOCUMENT", summary, unusable)
    if unusable:
        return DocumentOutcome("ready_partial", "PARTIAL_TEXT", summary, unusable)
    return DocumentOutcome("ready", None, summary, unusable)
