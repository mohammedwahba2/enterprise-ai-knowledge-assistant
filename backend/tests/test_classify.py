import pytest

from app.modules.processing.classify import PageState, classify_page, decide

PROSE = "Employees receive 25 working days of paid annual leave per calendar year. " * 3
ARABIC = "يحصل الموظفون على خمسة وعشرين يوم عمل من الإجازة السنوية المدفوعة في كل سنة. " * 3


@pytest.mark.parametrize(
    ("text", "ratio", "state"),
    [
        (PROSE, 0.0, PageState.TEXT),
        (ARABIC, 0.0, PageState.TEXT),
        (PROSE, 0.95, PageState.TEXT),  # full-page background/watermark image but a real text layer
        ("", 0.97, PageState.IMAGE_ONLY),  # a pure scan
        ("12", 0.9, PageState.IMAGE_ONLY),  # a scan whose only "text" is a page number
        ("Page 3", 0.8, PageState.IMAGE_ONLY),
        ("", 0.0, PageState.TEXT),  # genuinely blank page: not a failure
        (" ���� lorem", 0.0, PageState.GARBLED),
        ("�" * 40 + " word", 0.0, PageState.GARBLED),
        ("§§§ ### ¶¶¶ @@@ !!! ??? ***", 0.0, PageState.GARBLED),  # no letters at all
        ("Contract 2025 — clause 4.2: ٢٥ days", 0.0, PageState.TEXT),
    ],
)
def test_page_classification(text: str, ratio: float, state: PageState) -> None:
    assert classify_page(text, ratio) is state


def test_a_little_noise_in_good_text_is_still_text() -> None:
    assert classify_page(PROSE + "�", 0.0) is PageState.TEXT


def row(n: int, state: PageState, chars: int = 500) -> tuple[int, PageState, int]:
    return (n, state, 0 if state is not PageState.TEXT else chars)


def test_all_readable_is_ready() -> None:
    d = decide([row(1, PageState.TEXT), row(2, PageState.TEXT)])
    assert (d.status, d.error_code, d.unusable_pages) == ("ready", None, ())
    assert d.summary == {"total": 2, "text": 2, "image_only": 0, "garbled": 0}


def test_some_unreadable_pages_make_it_partial_and_name_the_pages() -> None:
    d = decide(
        [
            row(1, PageState.TEXT),
            row(2, PageState.IMAGE_ONLY),
            row(3, PageState.GARBLED),
            row(4, PageState.TEXT),
        ]
    )
    assert (d.status, d.error_code) == ("ready_partial", "PARTIAL_TEXT")
    assert d.unusable_pages == (2, 3)
    assert d.summary == {"total": 4, "text": 2, "image_only": 1, "garbled": 1}


def test_nothing_readable_is_scanned_or_garbled_never_ready() -> None:
    assert (
        decide([row(1, PageState.IMAGE_ONLY), row(2, PageState.IMAGE_ONLY)]).status
        == "unsupported_scanned"
    )
    assert (
        decide([row(1, PageState.IMAGE_ONLY), row(2, PageState.GARBLED)]).error_code
        == "NO_TEXT_LAYER"
    )
    g = decide([row(1, PageState.GARBLED)])
    assert (g.status, g.error_code) == ("unsupported_garbled", "GARBLED_TEXT")


def test_blank_documents_fail_explicitly() -> None:
    d = decide([(1, PageState.TEXT, 0), (2, PageState.TEXT, 0)])
    assert (d.status, d.error_code) == ("failed", "EMPTY_DOCUMENT")
    assert decide([]).status == "failed"
