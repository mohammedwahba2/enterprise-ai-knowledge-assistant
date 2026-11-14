"""Structure-aware chunking with page provenance.

Chunks follow headings and paragraphs, aim for ~400-600 tokens, overlap by ~12 %, and always record
the pages they cover. Pure functions: no I/O, deterministic.
"""

import math
import re
from dataclasses import dataclass

from app.modules.processing.arabic import detect_lang, search_normalize

TARGET_TOKENS = 500
MAX_TOKENS = 600
MIN_TOKENS = 150  # prefer to break at a heading once a chunk is at least this large
OVERLAP_RATIO = 0.12

_TERMINAL = ".!?؟…"
_NUMBERED = re.compile(r"^(\d+(?:\.\d+){0,4})[.)]?\s+\S")
_BULLET = re.compile(r"^([-•*▪◦]|\d+[.)]|\(\d+\)|[a-z]\))\s+")
_SENTENCE_SPLIT = re.compile(rf"(?<=[{re.escape(_TERMINAL)}])\s+")


def estimate_tokens(text: str) -> int:
    """A cheap, language-agnostic estimate (no tokenizer dependency): words x 1.3 or chars / 4."""
    words = len(text.split())
    return max(math.ceil(words * 1.3), math.ceil(len(text) / 4)) if text.strip() else 0


@dataclass(frozen=True)
class Page:
    number: int
    text: str


@dataclass(frozen=True)
class Chunk:
    index: int
    page_start: int
    page_end: int
    heading_path: str
    content: str
    token_count: int
    lang: str
    content_search: str


@dataclass
class _Block:
    text: str
    page: int
    heading_path: str
    is_heading: bool = False


def _is_heading(line: str, next_line: str | None) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 80 or next_line is None:
        return False
    if stripped[-1] in _TERMINAL + ",;،؛":
        return False
    if _NUMBERED.match(stripped):
        return len(stripped.split()) <= 12
    words = stripped.split()
    letters = [c for c in stripped if c.isalpha()]
    if not letters:
        return False
    latin_upper = all(c.isupper() for c in letters if c.isascii()) and any(
        c.isascii() for c in letters
    )
    return (latin_upper and len(words) <= 10) or (len(words) <= 6 and stripped[-1] == ":")


def _level(line: str) -> int:
    m = _NUMBERED.match(line.strip())
    return m.group(1).count(".") + 1 if m else 1


def _blocks(pages: list[Page]) -> list[_Block]:
    """Reflow page text into paragraph and heading blocks tagged with page and heading path."""
    out: list[_Block] = []
    stack: list[str] = []
    for page in pages:
        lines = [ln.strip() for ln in page.text.split("\n")]
        para: list[str] = []

        def flush(page_no: int = page.number, para: list[str] = para) -> None:
            if para:
                out.append(_Block(" ".join(para), page_no, " > ".join(stack)))
                para.clear()

        for i, line in enumerate(lines):
            nxt = next((x for x in lines[i + 1 :] if x), None)
            if not line:
                flush()
            elif _is_heading(line, nxt):
                flush()
                level = _level(line)
                del stack[level - 1 :]
                stack.append(line)
                out.append(_Block(line, page.number, " > ".join(stack), is_heading=True))
            else:
                if _BULLET.match(line):
                    flush()
                para.append(line)
                if line[-1] in _TERMINAL and len(line) < 40:
                    flush()
        flush()
    return out


def _word_windows(sentence: str) -> list[str]:
    """Last resort for one endless sentence: greedy windows using the same token estimate."""
    windows: list[str] = []
    current: list[str] = []
    chars = 0
    for word in sentence.split():
        words_after = len(current) + 1
        chars_after = chars + len(word) + (1 if current else 0)
        if (
            current
            and max(math.ceil(words_after * 1.3), math.ceil(chars_after / 4)) > TARGET_TOKENS
        ):
            windows.append(" ".join(current))
            current, chars = [], 0
        chars += len(word) + (1 if current else 0)
        current.append(word)
    if current:
        windows.append(" ".join(current))
    return windows


def _split_oversized(text: str) -> list[str]:
    """Split a paragraph larger than MAX_TOKENS at sentence boundaries, then at words."""
    parts: list[str] = []
    current: list[str] = []
    size = 0
    for sentence in _SENTENCE_SPLIT.split(text):
        tokens = estimate_tokens(sentence)
        if tokens > MAX_TOKENS:  # one giant sentence: fall back to word windows
            if current:
                parts.append(" ".join(current))
                current, size = [], 0
            parts.extend(_word_windows(sentence))
            continue
        if size + tokens > TARGET_TOKENS and current:
            parts.append(" ".join(current))
            current, size = [], 0
        current.append(sentence)
        size += tokens
    if current:
        parts.append(" ".join(current))
    return parts


def chunk_pages(pages: list[Page]) -> list[Chunk]:
    """Split usable pages into chunks. `pages` must be in order and contain only readable text."""
    pieces: list[_Block] = []
    for block in _blocks(pages):
        if block.is_heading or estimate_tokens(block.text) <= MAX_TOKENS:
            pieces.append(block)
        else:
            pieces.extend(
                _Block(p, block.page, block.heading_path) for p in _split_oversized(block.text)
            )

    chunks: list[Chunk] = []
    current: list[_Block] = []
    size = 0

    def emit() -> None:
        content = "\n".join(b.text for b in current).strip()
        if not content or all(b.is_heading for b in current):
            return
        body = [b for b in current if not b.is_heading] or current
        chunks.append(
            Chunk(
                index=len(chunks),
                page_start=min(b.page for b in current),
                page_end=max(b.page for b in current),
                heading_path=body[0].heading_path,
                content=content,
                token_count=estimate_tokens(content),
                lang=detect_lang(content),
                content_search=search_normalize(content),
            )
        )

    def carry_overlap() -> tuple[list[_Block], int]:
        budget = int(TARGET_TOKENS * OVERLAP_RATIO)
        kept: list[_Block] = []
        total = 0
        for b in reversed(current):
            if b.is_heading:
                break
            t = estimate_tokens(b.text)
            if total + t > budget and kept:
                break
            if t > budget * 2:  # never drag a whole large paragraph along
                break
            kept.insert(0, b)
            total += t
        return kept, total

    for piece in pieces:
        tokens = estimate_tokens(piece.text)
        starts_section = piece.is_heading and size >= MIN_TOKENS
        if current and (size + tokens > MAX_TOKENS or starts_section):
            emit()
            if starts_section:
                current, size = [], 0  # a new section starts clean: no overlap across headings
            else:
                current, size = carry_overlap()
        current.append(piece)
        size += tokens
    emit()
    return chunks
