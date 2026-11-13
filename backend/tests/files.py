"""Tiny, valid sample files for upload tests (unique content per `text`, so hashes differ)."""

import io
import zipfile


def pdf(text: str = "hello") -> bytes:
    body = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    return (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R>>endobj\n"
        + b"4 0 obj<</Length "
        + str(len(body)).encode()
        + b">>stream\n"
        + body
        + b"\nendstream endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
    )


def _zip(parts: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in parts.items():
            zf.writestr(name, content)
    return buf.getvalue()


def docx(text: str = "hello") -> bytes:
    return _zip(
        {
            "[Content_Types].xml": "<Types/>",
            "word/document.xml": f"<w:document><w:body><w:p><w:t>{text}</w:t></w:p></w:body></w:document>",
        }
    )


def pptx(text: str = "hello") -> bytes:
    return _zip(
        {
            "[Content_Types].xml": "<Types/>",
            "ppt/presentation.xml": f"<p:presentation>{text}</p:presentation>",
        }
    )


def xlsx(text: str = "hello") -> bytes:
    return _zip(
        {"[Content_Types].xml": "<Types/>", "xl/workbook.xml": f"<workbook>{text}</workbook>"}
    )


def text_file(text: str = "hello") -> bytes:
    return f"{text}\n".encode()
