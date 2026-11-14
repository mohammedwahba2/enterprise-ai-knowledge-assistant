"""Hand-built PDFs for processing tests.

Text is stored with a one-byte-per-character code and a /ToUnicode CMap, so ANY Unicode string
(Arabic, presentation forms, visual-order lines, private-use junk) comes back out of the text
extractor exactly as given. That lets tests exercise extraction handling without bundling fonts.
Only text extraction is meaningful; the rendering is not.
"""

from dataclasses import dataclass, field


@dataclass
class PageSpec:
    lines: list[str] = field(default_factory=list)
    image_ratio: float = 0.0  # share of the page covered by one image (a "scan" when no text)


def _hex(codes: list[int]) -> str:
    return "<" + "".join(f"{c:02X}" for c in codes) + ">"


def make_pdf(pages: list[PageSpec]) -> bytes:
    alphabet: dict[str, int] = {}
    for page in pages:
        for line in page.lines:
            for ch in line:
                if ch not in alphabet:
                    if len(alphabet) >= 250:
                        raise ValueError("too many distinct characters for the test generator")
                    alphabet[ch] = len(alphabet) + 1

    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    cmap_entries = "\n".join(
        f"<{code:02X}> <{ord(ch):04X}>" for ch, code in alphabet.items() if ord(ch) <= 0xFFFF
    )
    cmap = (
        "/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
        "/CMapName /Adobe-Identity-UCS def /CMapType 2 def\n"
        "1 begincodespacerange <00> <FF> endcodespacerange\n"
        f"{len(alphabet)} beginbfchar\n{cmap_entries}\nendbfchar\n"
        "endcmap CMapName currentdict /CMap defineresource pop end end"
    ).encode()
    catalog = add(b"")  # patched below
    pages_obj = add(b"")
    cmap_obj = add(b"<</Length %d>>stream\n" % len(cmap) + cmap + b"\nendstream")
    font_obj = add(b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica/ToUnicode %d 0 R>>" % cmap_obj)
    image_obj = add(
        b"<</Type/XObject/Subtype/Image/Width 1/Height 1/ColorSpace/DeviceGray/BitsPerComponent 8/Length 1>>"
        b"stream\n\x80\nendstream"
    )
    kids: list[int] = []
    width, height = 612, 792
    for page in pages:
        ops = []
        if page.image_ratio > 0:
            side = page.image_ratio**0.5
            ops.append(f"q {width * side:.1f} 0 0 {height * side:.1f} 0 0 cm /Im1 Do Q")
        y = 740
        for line in page.lines:
            codes = [alphabet[ch] for ch in line]
            ops.append(f"BT /F1 12 Tf 40 {y} Td {_hex(codes)} Tj ET")
            y -= 16
        stream = "\n".join(ops).encode()
        content = add(b"<</Length %d>>stream\n" % len(stream) + stream + b"\nendstream")
        page_obj = add(
            f"<</Type/Page/Parent {pages_obj} 0 R/MediaBox[0 0 {width} {height}]"
            f"/Resources<</Font<</F1 {font_obj} 0 R>>/XObject<</Im1 {image_obj} 0 R>>>>"
            f"/Contents {content} 0 R>>".encode()
        )
        kids.append(page_obj)
    objects[catalog - 1] = f"<</Type/Catalog/Pages {pages_obj} 0 R>>".encode()
    objects[pages_obj - 1] = (
        "<</Type/Pages/Kids[" + " ".join(f"{k} 0 R" for k in kids) + f"]/Count {len(kids)}>>"
    ).encode()

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<</Size {len(objects) + 1}/Root {catalog} 0 R>>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def encrypted(pdf: bytes, password: str = "secret") -> bytes:
    import io

    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf)))
    writer.encrypt(user_password=password, owner_password=password)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()
