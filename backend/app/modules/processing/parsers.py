"""Document parsers. They run in the worker, never in the API (untrusted input, native code)."""

import ctypes
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

MAX_PAGES = 2000
MAX_TOTAL_CHARS = 20_000_000
VIRTUAL_PAGE_CHARS = 3500
CONVERSION_TIMEOUT_SECONDS = 120


class ProcessingError(Exception):
    """A document that cannot be processed, with a stable code the UI can explain."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class RawPage:
    number: int
    text: str
    image_area_ratio: float


def parse_pdf(path: Path) -> list[RawPage]:
    """Per-page text and image coverage. Raises ProcessingError for encrypted/corrupt/huge files."""
    try:
        pdf = pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError as exc:
        if getattr(exc, "err_code", None) == pdfium_c.FPDF_ERR_PASSWORD:
            raise ProcessingError("ENCRYPTED", "The PDF is password protected.") from None
        raise ProcessingError("CORRUPT", "The PDF could not be opened.") from None
    try:
        count = len(pdf)
        if count > MAX_PAGES:
            raise ProcessingError("TOO_MANY_PAGES", f"More than {MAX_PAGES} pages.")
        pages: list[RawPage] = []
        total_chars = 0
        for index in range(count):
            page = pdf[index]
            try:
                textpage = page.get_textpage()
                try:
                    text = _repair_lam_alef(textpage, textpage.get_text_bounded())
                finally:
                    textpage.close()
                ratio = _image_ratio(page)
            except pdfium.PdfiumError:
                raise ProcessingError("CORRUPT", f"Page {index + 1} could not be read.") from None
            finally:
                page.close()
            total_chars += len(text)
            if total_chars > MAX_TOTAL_CHARS:
                raise ProcessingError("TOO_MANY_PAGES", "The document contains too much text.")
            pages.append(RawPage(index + 1, text, ratio))
        return pages
    finally:
        pdf.close()


_ARABIC_LETTER = re.compile("[\u0621-\u064a]")
_ALEF_FORMS = frozenset("\u0627\u0623\u0625\u0622\u0671")  # alef, hamza above/below, madda, wasla
_LAM = "\u0644"


def _repair_lam_alef(textpage: pdfium.PdfTextPage, text: str) -> str:
    """Undo pdfium's swapped lam-alef ligatures.

    Word processors draw lam+alef as ONE ligature glyph whose ToUnicode entry is two characters.
    pdfium emits those two characters in the wrong order for right-to-left text ("ثلاثين" comes
    out as "ثالثين", "السلام" as "السالم"), which silently breaks Arabic search. The two characters
    of a ligature share one glyph box, while a genuine alef+lam (the definite article) occupies two
    boxes, so only boxed-together (alef-form, lam) pairs are swapped and a real "ال" is untouched.
    Pages without Arabic letters skip the slow per-character pass entirely.
    """
    if not _ARABIC_LETTER.search(text):
        return text
    handle = textpage.raw
    count = int(pdfium_c.FPDFText_CountChars(handle))
    chars: list[str] = []
    boxes: list[tuple[float, float]] = []
    left, right, bottom, top = (ctypes.c_double() for _ in range(4))
    for index in range(count):
        code = int(pdfium_c.FPDFText_GetUnicode(handle, index))
        if code == 0:
            continue
        pdfium_c.FPDFText_GetCharBox(handle, index, left, right, bottom, top)
        chars.append(chr(code))
        boxes.append((round(left.value, 3), round(right.value, 3)))
    swapped = False
    i = 1
    while i < len(chars):
        if chars[i] == _LAM and chars[i - 1] in _ALEF_FORMS and boxes[i] == boxes[i - 1]:
            chars[i - 1], chars[i] = chars[i], chars[i - 1]
            swapped = True
            i += 2
        else:
            i += 1
    return "".join(chars) if swapped else text


def _image_ratio(page: pdfium.PdfPage) -> float:
    width, height = page.get_size()
    area = max(width * height, 1.0)
    covered = 0.0
    for obj in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE]):
        left, bottom, right, top = obj.get_bounds()
        covered += max(0.0, min(right, width) - max(left, 0.0)) * max(
            0.0, min(top, height) - max(bottom, 0.0)
        )
    return float(min(1.0, covered / area))


def parse_text(data: bytes) -> list[RawPage]:
    """Plain text and Markdown have no pages: split into virtual pages at paragraph boundaries."""
    text = data.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [p for p in re.split(r"\n\s*\n", text)]
    pages: list[list[str]] = [[]]
    size = 0
    for paragraph in paragraphs:
        if size and size + len(paragraph) > VIRTUAL_PAGE_CHARS:
            pages.append([])
            size = 0
        pages[-1].append(paragraph)
        size += len(paragraph) + 2
    return [
        RawPage(i + 1, "\n\n".join(chunk), 0.0)
        for i, chunk in enumerate(pages)
        if any(p.strip() for p in chunk)
    ]


class OfficeConverter:
    """DOCX/PPTX -> PDF with headless LibreOffice, so page numbers match what users see."""

    def __init__(self, binary: str = "soffice", timeout: int = CONVERSION_TIMEOUT_SECONDS) -> None:
        self.binary = binary
        self.timeout = timeout

    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    def to_pdf(self, source: Path) -> Path:
        out_dir = Path(tempfile.mkdtemp(prefix="lo-out-"))
        profile = Path(tempfile.mkdtemp(prefix="lo-profile-"))
        cmd = [
            self.binary, "--headless", "--norestore", "--nolockcheck", "--nodefault",
            f"-env:UserInstallation=file://{profile}", "--convert-to", "pdf",
            "--outdir", str(out_dir), str(source),
        ]  # fmt: skip
        try:
            subprocess.run(  # noqa: S603  (fixed argv, no shell, no user-controlled flags)
                cmd, check=True, capture_output=True, timeout=self.timeout,
                env={
                    "HOME": str(profile), "LANG": "C.UTF-8",
                    "PATH": "/usr/bin:/bin:/usr/local/bin",
                },
            )  # fmt: skip
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            raise ProcessingError(
                "CONVERSION_FAILED", "The document could not be converted for processing."
            ) from None
        finally:
            shutil.rmtree(profile, ignore_errors=True)
        produced = out_dir / f"{source.stem}.pdf"
        if not produced.exists() or produced.stat().st_size == 0:
            raise ProcessingError(
                "CONVERSION_FAILED", "The document could not be converted for processing."
            )
        return produced
