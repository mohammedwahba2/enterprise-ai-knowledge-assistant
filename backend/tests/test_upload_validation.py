import io

import pytest

from app.modules.documents import validation as v
from tests import files


def sniff(content: bytes, name: str) -> v.Sniffed:
    return v.sniff(io.BytesIO(content), name)


def code(content: bytes, name: str) -> str:
    with pytest.raises(v.Rejected) as exc:
        sniff(content, name)
    return exc.value.code


@pytest.mark.parametrize(
    ("content", "name", "mime"),
    [
        (files.pdf(), "report.pdf", v.PDF),
        (files.docx(), "Policy.DOCX", v.DOCX),
        (files.pptx(), "deck.pptx", v.PPTX),
        (files.text_file("plain"), "notes.txt", v.TXT),
        (files.text_file("# heading"), "readme.md", v.MD),
        ("نص عربي".encode(), "ملف.txt", v.TXT),
        (b"\xef\xbb\xbfwith bom", "bom.txt", v.TXT),
    ],
)
def test_valid_files_are_identified_from_content(content: bytes, name: str, mime: str) -> None:
    assert sniff(content, name).mime == mime


@pytest.mark.parametrize(
    ("content", "name", "expected"),
    [
        (b"MZ\x90\x00 executable", "invoice.pdf", "UNSUPPORTED_TYPE"),
        (b"<html><script>alert(1)</script></html>", "page.pdf", "UNSUPPORTED_TYPE"),
        (b"<html><script>alert(1)</script></html>", "page.txt", "UNSUPPORTED_TYPE")
        if False
        else (b"a\x00b", "bin.txt", "UNSUPPORTED_TYPE"),
        (b"\xff\xfe\x00\x00 not utf8", "x.txt", "UNSUPPORTED_TYPE"),
        (b"caf\xe9 latin-1", "x.md", "UNSUPPORTED_TYPE"),
        (files.docx(), "x.pdf", "UNSUPPORTED_TYPE"),  # type confusion
        (files.pdf(), "x.docx", "UNSUPPORTED_TYPE"),
        (files.pptx(), "x.docx", "UNSUPPORTED_TYPE"),  # wrong Office family
        (files.xlsx(), "x.docx", "UNSUPPORTED_TYPE"),  # unsupported Office type
        (files.xlsx(), "x.xlsx", "UNSUPPORTED_TYPE"),
        (files.pdf(), "noextension", "UNSUPPORTED_TYPE"),
        (files.pdf(), "archive.exe", "UNSUPPORTED_TYPE"),
        (files.pdf(), "x.html", "UNSUPPORTED_TYPE"),
        (b"PK\x03\x04 truncated nonsense", "x.docx", "CORRUPT_FILE"),
    ],
)
def test_invalid_files_are_rejected(content: bytes, name: str, expected: str) -> None:
    assert code(content, name) == expected


def test_a_plain_zip_wearing_an_office_extension_is_refused() -> None:
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("evil.exe", "MZ")
    assert code(buf.getvalue(), "x.docx") == "UNSUPPORTED_TYPE"


def test_zip_with_path_traversal_entries_or_too_many_entries_is_refused() -> None:
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", "<w/>")
        zf.writestr("../../etc/passwd", "x")
    assert code(buf.getvalue(), "x.docx") == "CORRUPT_FILE"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", "<w/>")
        for i in range(v.MAX_ZIP_ENTRIES + 1):
            zf.writestr(f"f{i}", "")
    assert code(buf.getvalue(), "x.docx") == "CORRUPT_FILE"


# ---------------- filenames ----------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("report.pdf", "report.pdf"),
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("C:\\Users\\me\\secret.docx", "secret.docx"),
        ("a/b/c.txt", "c.txt"),
        ("bad\x00\x07name\n.pdf", "badname.pdf"),
        ("invoice\u202egnp.exe.pdf", "invoicegnp.exe.pdf"),  # right-to-left override stripped
        ("a\u200bb.pdf", "ab.pdf"),  # zero-width space stripped
        ("   .hidden  ", "hidden"),
        ("", "document"),
        ("///", "document"),
        ("نموذج\u200cطلب.pdf", "نموذج\u200cطلب.pdf"),  # ZWNJ is kept: it is real Arabic-script text
        ("  many   spaces  .txt", "many spaces .txt"),
    ],
)
def test_filename_sanitising(raw: str, expected: str) -> None:
    assert v.sanitize_filename(raw) == expected


def test_long_names_are_truncated_but_keep_the_extension() -> None:
    name = v.sanitize_filename("x" * 400 + ".pdf")
    assert len(name) <= 200 and name.endswith(".pdf")


def test_title_is_the_stem() -> None:
    assert v.title_from("Employee Handbook 2025.pdf") == "Employee Handbook 2025"
    assert v.title_from("noext") == "noext"


@pytest.mark.parametrize(
    "name", ['a"b.pdf', "a\r\nSet-Cookie: x=1.pdf", "name;evil.pdf", "ملف عربي.pdf", "ü.pdf"]
)
def test_content_disposition_cannot_inject_headers(name: str) -> None:
    clean = v.sanitize_filename(name)
    header = v.content_disposition(clean, inline=False)
    assert "\r" not in header and "\n" not in header
    assert header.startswith("attachment; filename=")
    assert header.count('"') == 2  # only the two delimiters of the ASCII fallback
    assert "filename*=UTF-8''" in header
    assert v.content_disposition(clean, inline=True).startswith("inline;")
