"""Upload validation: content sniffing and filename sanitising. Never trust client metadata."""

import codecs
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from typing import IO

from app.core.errors import AppError

CHUNK = 1024 * 1024
MAX_ZIP_ENTRIES = 5000
MAX_ZIP_UNCOMPRESSED = 1024 * 1024 * 1024  # 1 GiB declared, a cheap zip-bomb guard

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
TXT = "text/plain"
MD = "text/markdown"

_EXTENSIONS = {"pdf": PDF, "docx": DOCX, "pptx": PPTX, "txt": TXT, "md": MD, "markdown": MD}
_OOXML_MARKER = {DOCX: "word/document.xml", PPTX: "ppt/presentation.xml"}


class Rejected(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Sniffed:
    mime: str
    extension: str


def sanitize_filename(raw: str) -> str:
    """A safe DISPLAY name. It is never used in paths or storage keys."""
    name = unicodedata.normalize("NFC", raw or "")
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    # drop control characters and invisible/bidi-override formatting
    # (ZWNJ/ZWJ are kept: Arabic-script text needs them)
    name = "".join(
        ch
        for ch in name
        if unicodedata.category(ch) not in ("Cc", "Cs", "Co", "Cn")
        and (unicodedata.category(ch) != "Cf" or ch in ("‌", "‍"))
    )
    name = re.sub(r"\s+", " ", name).strip(" .")
    if len(name) > 200:
        stem, dot, ext = name.rpartition(".")
        name = (stem[: 200 - len(ext) - 1] + dot + ext) if dot and len(ext) < 10 else name[:200]
    return name or "document"


def title_from(filename: str) -> str:
    stem = filename.rpartition(".")[0] or filename
    return stem[:255] or filename[:255]


def extension_of(filename: str) -> str:
    return filename.rpartition(".")[2].lower() if "." in filename else ""


def _is_text(f: IO[bytes]) -> bool:
    decoder = codecs.getincrementaldecoder("utf-8")()
    f.seek(0)
    first = True
    while chunk := f.read(CHUNK):
        if first and chunk.startswith(codecs.BOM_UTF8):
            chunk = chunk[len(codecs.BOM_UTF8) :]
        first = False
        if b"\x00" in chunk:
            return False
        try:
            decoder.decode(chunk)
        except UnicodeDecodeError:
            return False
    try:
        decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        return False
    return True


def sniff(f: IO[bytes], filename: str) -> Sniffed:
    """Decide the type from CONTENT and require the extension to agree. Raises `Rejected`."""
    ext = extension_of(filename)
    expected = _EXTENSIONS.get(ext)
    if expected is None:
        raise Rejected("UNSUPPORTED_TYPE")
    f.seek(0)
    head = f.read(8)
    if expected == PDF:
        if not head.startswith(b"%PDF-"):
            raise Rejected("UNSUPPORTED_TYPE")
    elif expected in _OOXML_MARKER:
        if not head.startswith(b"PK\x03\x04"):
            raise Rejected("UNSUPPORTED_TYPE")
        f.seek(0)
        try:
            with zipfile.ZipFile(f) as zf:
                infos = zf.infolist()
                if (
                    len(infos) > MAX_ZIP_ENTRIES
                    or sum(i.file_size for i in infos) > MAX_ZIP_UNCOMPRESSED
                ):
                    raise Rejected("CORRUPT_FILE")
                names = {i.filename for i in infos}
                if any(n.startswith(("/", "..")) or "/../" in n for n in names):
                    raise Rejected("CORRUPT_FILE")
        except zipfile.BadZipFile:
            raise Rejected("CORRUPT_FILE") from None
        if _OOXML_MARKER[expected] not in names:
            raise Rejected(
                "UNSUPPORTED_TYPE"
            )  # a zip (or another Office type) wearing this extension
    else:  # text / markdown
        if not _is_text(f):
            raise Rejected("UNSUPPORTED_TYPE")
    f.seek(0)
    return Sniffed(expected, ext)


def content_disposition(filename: str, inline: bool) -> str:
    """RFC 6266/5987 header with an ASCII fallback; the name cannot break out of the header."""
    from urllib.parse import quote

    ascii_name = (
        re.sub(r"[^A-Za-z0-9._-]", "_", filename.encode("ascii", "ignore").decode()) or "document"
    )
    kind = "inline" if inline else "attachment"
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"


def not_found() -> AppError:
    return AppError(404, "NOT_FOUND", "Not Found")
