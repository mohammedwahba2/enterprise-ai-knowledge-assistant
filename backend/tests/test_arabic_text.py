import pytest

from app.modules.processing import arabic as ar


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("أحمد", "احمد"),
        ("إسلام", "اسلام"),
        ("آمن", "امن"),
        ("مُحَمَّد", "محمد"),  # tashkeel
        ("كتـــاب", "كتاب"),  # tatweel
        ("على", "علي"),  # alef maksura folds to ya
        ("ﻻ", "لا"),  # presentation-form ligature (U+FEFB)
        ("ﻣﺤﻤﺪ", "محمد"),  # isolated/medial presentation forms
        ("HELLO World", "hello world"),
    ],
)
def test_search_normalisation_folds_equivalent_spellings(a: str, b: str) -> None:
    assert ar.search_normalize(a) == ar.search_normalize(b)


def test_digits_and_separators_fold_to_ascii_in_both_digit_systems() -> None:
    assert ar.search_normalize("٢٥ يوماً") == ar.search_normalize("25 يوماً")
    assert "25" in ar.search_normalize("۲۵")  # Persian digits
    assert ar.search_normalize("٣٫٥") == "3.5"
    assert ar.search_normalize("١٬٢٣٤") == "1,234"
    assert ar.search_normalize("Policy ٤٫٢") == "policy 4.2"


def test_normalisation_is_idempotent_and_does_not_mangle_plain_text() -> None:
    once = ar.search_normalize("الإجازة السنوية: ٢٥ يوم عمل / 25 working days")
    assert ar.search_normalize(once) == once
    assert ar.search_normalize("annual leave policy") == "annual leave policy"


# ---- extraction repair -----------------------------------------------------------------------

LOGICAL = "يحصل الموظفون على 25 يوم إجازة سنوية في كل سنة ميلادية من الشركة"
LOGICAL2 = "تقدم الطلبات عبر البوابة قبل أسبوعين على الأقل من تاريخ البدء"


def visual(line: str) -> str:
    """What a visual-order PDF generator hands back: the line flipped, digit runs left intact."""
    return ar._reverse_line(line)


def test_visual_order_pages_are_detected_and_repaired() -> None:
    page = "\n".join([visual(LOGICAL), visual(LOGICAL2)])
    assert ar.looks_reversed(page)
    assert ar.fix_reversed_arabic(page) == "\n".join([LOGICAL, LOGICAL2])


def test_logical_order_text_is_left_untouched() -> None:
    page = f"{LOGICAL}\n{LOGICAL2}"
    assert not ar.looks_reversed(page)
    assert ar.fix_reversed_arabic(page) == page


def test_english_and_short_snippets_are_never_reversed() -> None:
    for text in ("Annual leave is 25 working days.", "في", "", "من على"):
        assert ar.fix_reversed_arabic(text) == text


def test_mixed_language_logical_text_keeps_latin_runs_intact() -> None:
    text = "سياسة Employee Handbook 2025 في الشركة على هذا النحو من كل عام"
    assert ar.fix_reversed_arabic(text) == text


def test_clean_extracted_folds_presentation_forms_and_strips_control_junk() -> None:
    raw = "ﻣﺮﺣﺒﺎ\x00 \x07بالعالم\r\n\r\n\r\n\r\nسطر ثان  "
    out = ar.clean_extracted(raw)
    assert "\x00" not in out and "\x07" not in out
    assert "\n\n\n" not in out
    assert "مرحبا" in out and "سطر ثان" in out


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        ("Annual leave is granted to all employees.", "en"),
        ("تُمنح الإجازة السنوية لجميع الموظفين", "ar"),
        ("Employee Handbook دليل الموظف leave policy سياسة الإجازة", "mixed"),
        ("12345 !!!", "en"),
        ("", "en"),
    ],
)
def test_language_detection(text: str, lang: str) -> None:
    assert ar.detect_lang(text) == lang
