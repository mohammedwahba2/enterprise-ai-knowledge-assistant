# ruff: noqa: RUF001  (Arabic letters are intentional in this module)
"""Text normalisation for Arabic and English extraction and search (PLAN 7.5, decision D11)."""

import re
import unicodedata

# Tashkeel (harakat), superscript alef, Quranic marks; tatweel is handled separately.
_DIACRITICS = re.compile("[ً-ٰٟۖ-ۭ]")
_TATWEEL = "ـ"
_ALEF_VARIANTS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي"})
# Arabic-Indic (U+0660-0669) and Eastern Arabic-Indic / Persian (U+06F0-06F9) digits -> ASCII
_DIGITS = {
    **{0x0660 + i: ord("0") + i for i in range(10)},
    **{0x06F0 + i: ord("0") + i for i in range(10)},
}
_SEPARATORS = {
    0x066B: ord("."),
    0x066C: ord(","),
    0x060C: ord(","),
}  # decimal sep, thousands sep, Arabic comma
_DIGIT_TABLE = {**_DIGITS, **_SEPARATORS}
# Numbers only: digits and the Arabic decimal/thousands separators, NOT the Arabic comma.
_NUMBER_TABLE = {**_DIGITS, 0x066B: ord("."), 0x066C: ord(",")}

_ARABIC_LETTER = re.compile("[ء-يٮ-ۓۺ-ۿݐ-ݿ]")
_LATIN_LETTER = re.compile("[A-Za-zÀ-ɏ]")
_NON_ARABIC_RUN = re.compile(r"[A-Za-z0-9À-ɏ][A-Za-z0-9À-ɏ.,:/\-_@+%]*")

# Very common Arabic function words: used ONLY to tell logical order from reversed (visual) order.
_COMMON = (
    "في", "من", "على", "إلى", "عن", "هذا", "هذه", "التي", "الذي", "أن", "لا", "ما", "مع", "كل",
    "أو", "ثم", "قد", "هو", "هي", "عند", "بعد", "قبل", "بين", "حتى", "كان", "ذلك", "يتم", "أي",
)  # fmt: skip
_FORWARD = {w for w in _COMMON}
_REVERSED = {w[::-1] for w in _COMMON if w[::-1] != w}


def strip_diacritics(text: str) -> str:
    return _DIACRITICS.sub("", text).replace(_TATWEEL, "")


def fold_digits(text: str) -> str:
    """Arabic-Indic and Persian digits (and their separators) to ASCII, nothing else.

    Applied to the text sent to the embedder at index AND query time: the same question typed with
    ٢٥ or ۲۵ or 25 must embed identically, or its ranking depends on the keyboard (measured with
    bge-m3: all three find the answer but the top-10 order differed). Letters are left untouched.
    """
    return text.translate(_NUMBER_TABLE)


def search_normalize(text: str) -> str:
    """Form used for lexical search, applied identically at index and query time.

    Display text is never replaced by this: citations quote the original.
    Folds: NFKC (presentation forms, full-width), tashkeel + tatweel, alef variants and alef
    maksura, Arabic-Indic/Persian digits and separators to ASCII, Latin case.
    """
    text = unicodedata.normalize("NFKC", text)
    text = strip_diacritics(text).translate(_ALEF_VARIANTS).translate(_DIGIT_TABLE)
    return " ".join(text.casefold().split())


def _words(text: str) -> list[str]:
    return [strip_diacritics(w) for w in re.findall(r"[؀-ۿ]+", text)]


def looks_reversed(text: str) -> bool:
    """True when the Arabic in `text` is in visual (reversed) order rather than logical order."""
    words = _words(text)
    forward = sum(1 for w in words if w in _FORWARD)
    reversed_hits = sum(1 for w in words if w in _REVERSED)
    return reversed_hits >= 3 and reversed_hits > 2 * forward


def _reverse_line(line: str) -> str:
    logical = line[::-1]
    # Latin words and digit runs were reversed by the whole-line flip: flip them back.
    return _NON_ARABIC_RUN.sub(lambda m: m.group(0)[::-1], logical)


def fix_reversed_arabic(text: str) -> str:
    """Repair pages extracted in visual order (some PDF generators); a no-op for logical text."""
    if not looks_reversed(text):
        return text
    return "\n".join(_reverse_line(line) for line in text.split("\n"))


def clean_extracted(text: str) -> str:
    """NFKC-fold presentation forms, drop control junk, repair order, tidy whitespace."""
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch) != "Cc")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    text = fix_reversed_arabic(text)
    lines = [" ".join(line.split()) for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def detect_lang(text: str) -> str:
    """'ar' | 'en' | 'mixed' from the share of Arabic vs Latin letters."""
    arabic = len(_ARABIC_LETTER.findall(text))
    latin = len(_LATIN_LETTER.findall(text))
    total = arabic + latin
    if total == 0:
        return "en"
    share = arabic / total
    return "ar" if share >= 0.8 else "en" if share <= 0.2 else "mixed"
