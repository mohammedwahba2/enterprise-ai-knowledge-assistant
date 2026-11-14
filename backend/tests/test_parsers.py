import stat
from pathlib import Path

import pytest

from app.modules.processing import parsers
from app.modules.processing.parsers import OfficeConverter, ProcessingError, parse_pdf, parse_text
from tests.pdfgen import PageSpec, encrypted, make_pdf


def write(tmp_path: Path, data: bytes, name: str = "in.pdf") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_text_pages_are_extracted_in_order_with_zero_image_coverage(tmp_path: Path) -> None:
    pdf = make_pdf(
        [PageSpec(["Employee Handbook", "Annual leave is 25 days"]), PageSpec(["Second page text"])]
    )
    pages = parse_pdf(write(tmp_path, pdf))
    assert [p.number for p in pages] == [1, 2]
    assert "Annual leave is 25 days" in pages[0].text and "Second page text" in pages[1].text
    assert all(p.image_area_ratio == 0 for p in pages)


def test_arabic_text_survives_extraction_in_some_order(tmp_path: Path) -> None:
    """pdfium re-orders right-to-left runs itself, so the ORDER is not guaranteed; the letters are.

    Order repair (visual vs logical) is the pipeline's job and is tested in test_arabic_text.py
    and test_pipeline.py.
    """
    pdf = make_pdf([PageSpec(["مرحبا بالعالم", "ﻣﺮﺣﺒﺎ ﺑﺎﻟﻌﺎﻟﻢ"])])
    text = parse_pdf(write(tmp_path, pdf))[0].text
    letters = sorted(c for c in text if c.isalpha())
    assert letters == sorted(
        c for c in "مرحبابالعالم" * 2 if c.isalpha()
    )  # presentation forms folded by pdfium


def test_image_only_pages_report_their_image_coverage(tmp_path: Path) -> None:
    pdf = make_pdf(
        [
            PageSpec([], image_ratio=0.9),
            PageSpec(["Real text on this one"]),
            PageSpec([], image_ratio=0.0),
        ]
    )
    pages = parse_pdf(write(tmp_path, pdf))
    assert pages[0].text.strip() == "" and pages[0].image_area_ratio > 0.8
    assert pages[1].image_area_ratio == 0 and "Real text" in pages[1].text
    assert pages[2].text.strip() == "" and pages[2].image_area_ratio == 0


def test_encrypted_pdfs_are_reported_not_crashed(tmp_path: Path) -> None:
    pdf = encrypted(make_pdf([PageSpec(["secret content"])]))
    with pytest.raises(ProcessingError) as exc:
        parse_pdf(write(tmp_path, pdf))
    assert exc.value.code == "ENCRYPTED"


@pytest.mark.parametrize(
    "data",
    [
        b"%PDF-1.4\nthis is not really a pdf\n",
        b"%PDF-1.4\n" + b"\x00\xff" * 2000,
        make_pdf([PageSpec(["x"])])[:120],  # truncated
        b"",
    ],
)
def test_corrupt_pdfs_raise_a_clean_error(tmp_path: Path, data: bytes) -> None:
    with pytest.raises(ProcessingError) as exc:
        parse_pdf(write(tmp_path, data))
    assert exc.value.code == "CORRUPT"


def test_page_limit_is_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parsers, "MAX_PAGES", 2)
    pdf = make_pdf([PageSpec([f"page {i}"]) for i in range(3)])
    with pytest.raises(ProcessingError) as exc:
        parse_pdf(write(tmp_path, pdf))
    assert exc.value.code == "TOO_MANY_PAGES"


def test_text_files_get_virtual_pages_at_paragraph_boundaries() -> None:
    paragraphs = [f"Paragraph {i}. " + "word " * 120 for i in range(20)]
    pages = parse_text("\n\n".join(paragraphs).encode())
    assert len(pages) > 2
    joined = "\n\n".join(p.text for p in pages)
    assert all(f"Paragraph {i}." in joined for i in range(20))  # nothing lost
    assert [p.number for p in pages] == list(range(1, len(pages) + 1))
    assert all(
        len(p.text) <= parsers.VIRTUAL_PAGE_CHARS + 700 for p in pages
    )  # a paragraph is never cut mid-way
    assert parse_text(b"") == [] and parse_text(b"  \n\n \n") == []


def test_text_decoding_handles_bom_and_crlf() -> None:
    pages = parse_text(b"\xef\xbb\xbfFirst line\r\nsecond line\r\n\r\nthird")
    assert pages[0].text.startswith("First line") and "\r" not in pages[0].text


# ------------------------------------------------------------ Office conversion wrapper
# Real LibreOffice runs in the worker image (see the live verification); here the wrapper's
# error handling is tested with stand-in executables.


def fake_binary(tmp_path: Path, body: str) -> str:
    script = tmp_path / "fake-soffice"
    script.write_text("#!/bin/sh\n" + body)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def test_converter_returns_the_produced_pdf(tmp_path: Path) -> None:
    src = write(tmp_path, b"PK", "report.docx")
    binary = fake_binary(
        tmp_path,
        'out=""; while [ $# -gt 0 ]; do [ "$1" = "--outdir" ] && out="$2"; last="$1"; shift; done; echo "%PDF-1.4" > "$out/report.pdf"',
    )
    out = OfficeConverter(binary).to_pdf(src)
    assert out.name == "report.pdf" and out.read_bytes().startswith(b"%PDF")


@pytest.mark.parametrize(
    "body",
    ["exit 1", "exit 0", "sleep 30"],  # fails, produces nothing, hangs
)
def test_converter_failures_become_a_stable_error_code(tmp_path: Path, body: str) -> None:
    src = write(tmp_path, b"PK", "report.docx")
    converter = OfficeConverter(fake_binary(tmp_path, body), timeout=1)
    with pytest.raises(ProcessingError) as exc:
        converter.to_pdf(src)
    assert exc.value.code == "CONVERSION_FAILED"


def test_a_missing_binary_is_a_conversion_failure_not_a_crash(tmp_path: Path) -> None:
    src = write(tmp_path, b"PK", "report.docx")
    converter = OfficeConverter("/nonexistent/soffice")
    assert not converter.available()
    with pytest.raises(ProcessingError) as exc:
        converter.to_pdf(src)
    assert exc.value.code == "CONVERSION_FAILED"
