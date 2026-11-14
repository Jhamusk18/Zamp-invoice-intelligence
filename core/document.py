"""Deterministic document facts - no AI involved.

  * Is it really a PDF? Can it be opened? (technical failures -> stop the run)
  * Text layer or scan? For scans, Tesseract OCR gives an INDEPENDENT reference text.
  * Hidden text: tiny or white text the human eye can't see but an AI would read.
  * Evidence verification: does the AI's quoted snippet really appear in the document,
    and does the extracted value really appear in that snippet?
"""
import hashlib
import re
from dataclasses import dataclass, field

import pymupdf
from rapidfuzz import fuzz

MAX_BYTES = 10 * 1024 * 1024
MIN_TEXT_CHARS = 40  # fewer real characters than this on the page -> treat as a scan


class TechnicalError(Exception):
    """A failure that stops the run (bad file, unreadable, service down). Not a business finding."""


@dataclass
class DocFacts:
    page_count: int
    is_scanned: bool
    text: str                      # text layer, or OCR text for scans
    text_source: str               # 'TEXT' or 'OCR'
    hidden_text: list = field(default_factory=list)
    page_images_png: list = field(default_factory=list)  # for the vision model on scans


def fingerprint(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_upload(data: bytes, filename: str = "") -> None:
    if not data:
        raise TechnicalError("The file is empty.")
    if len(data) > MAX_BYTES:
        raise TechnicalError(f"File is {len(data) / 1e6:.1f} MB; the limit is 10 MB.")
    if not data[:1024].lstrip().startswith(b"%PDF-"):
        raise TechnicalError("This file is not a PDF (checked the file contents, not just the name).")


def read_document(data: bytes, ocr: bool = True) -> DocFacts:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:  # corrupt
        raise TechnicalError(f"The PDF could not be opened (it may be corrupt): {e}")
    if doc.needs_pass:
        raise TechnicalError("The PDF is password-protected. Ask the vendor for an unlocked copy.")
    if doc.page_count == 0:
        raise TechnicalError("The PDF has no pages.")
    if doc.page_count > 10:
        raise TechnicalError("The PDF has more than 10 pages; this prototype handles single invoices only.")

    text = "\n".join(p.get_text() for p in doc)
    is_scanned = len(re.sub(r"\s", "", text)) < MIN_TEXT_CHARS
    hidden = [] if is_scanned else find_hidden_text(doc)
    images = []
    if is_scanned:
        for p in doc:
            images.append(p.get_pixmap(dpi=200).tobytes("png"))
        if ocr:
            text = ocr_pages(images)
            if len(re.sub(r"\s", "", text)) < MIN_TEXT_CHARS:
                raise TechnicalError("The scan is unreadable: OCR found almost no text.")
        source = "OCR"
    else:
        source = "TEXT"
    return DocFacts(doc.page_count, is_scanned, text, source, hidden, images)


def ocr_pages(images_png: list[bytes]) -> str:
    import io

    import pytesseract
    from PIL import Image
    try:
        return "\n".join(pytesseract.image_to_string(Image.open(io.BytesIO(b)), config="--psm 6") for b in images_png)
    except pytesseract.TesseractNotFoundError as e:
        raise TechnicalError("OCR engine (Tesseract) is not installed on the server.") from e


def find_hidden_text(doc) -> list[dict]:
    """Text a person can't see: white/near-white colour, tiny font, or outside the page."""
    found = []
    for pno, page in enumerate(doc):
        rect = page.rect
        # Render the page WITHOUT text to see what colour is really behind each span
        # (white text on a dark header band is visible; white text on white paper is not).
        bg = page.get_pixmap(dpi=36, annots=False, clip=rect, colorspace=pymupdf.csRGB)
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    t = span["text"].strip()
                    if len(t) < 3:
                        continue
                    c = span["color"]
                    r, g, b = (c >> 16) & 255, (c >> 8) & 255, c & 255
                    why = None
                    x0, y0, x1, y1 = span["bbox"]
                    sx, sy = bg.width / rect.width, bg.height / rect.height
                    px = (min(bg.width - 1, max(0, int((x0 - 1) * sx))), min(bg.height - 1, max(0, int((y0 + y1) / 2 * sy))))
                    br, bgc, bb = bg.pixel(*px)[:3]
                    if abs(r - br) + abs(g - bgc) + abs(b - bb) < 60:
                        why = "text the same colour as its background"
                    elif span["size"] < 3:
                        why = f"tiny font ({span['size']:.1f} pt)"
                    elif not rect.intersects(pymupdf.Rect(span["bbox"])):
                        why = "outside the visible page"
                    if why:
                        found.append({"page": pno + 1, "reason": why, "text": t[:300]})
    return found


# ---------------- evidence verification ----------------

def _norm(s: str) -> str:
    s = (s or "").lower().replace("₹", " ").replace("rs.", " ")
    s = re.sub(r"(?<=\d),(?=\d)", "", s)  # 1,13,200 -> 113200
    return re.sub(r"\s+", " ", s).strip()


def _value_tokens(value) -> list[str]:
    """How a value may appear in text. Numbers: '113200' or '113200.00'. Dates: several formats."""
    if value is None:
        return []
    if isinstance(value, (int, float)):
        v = float(value)
        toks = [f"{v:.2f}"]
        if v == int(v):
            toks.append(str(int(v)))
        return toks
    s = str(value)
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        y, mo, d = m.groups()
        mon = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"][int(mo) - 1]
        return [f"{d} {mon}", f"{int(d)} {mon}", f"{d}/{mo}/{y}", f"{d}-{mo}-{y}", f"{d}.{mo}.{y}", s]
    return [_norm(s)]


def verify_evidence(value, snippet: str | None, doc_text: str, source: str) -> str:
    """Returns 'TEXT' / 'OCR' if verified against that reference text, else 'NONE'.

    Two conditions, both required:
      1. the snippet appears in the document (exactly for a text layer; fuzzy for OCR, which makes small errors)
      2. the extracted value appears inside the snippet (so the AI can't quote one thing and extract another)
    """
    if value is None or value == "":
        return "NONE"
    doc_n = _norm(doc_text)
    snip_n = _norm(snippet or "")
    if not snip_n:
        return "NONE"
    if source == "TEXT":
        in_doc = snip_n in doc_n
    else:
        in_doc = fuzz.partial_ratio(snip_n, doc_n) >= 88
    if not in_doc:
        return "NONE"
    toks = _value_tokens(value)
    if source == "TEXT":
        ok = any(t in snip_n for t in toks)
    else:
        ok = any(t in snip_n or fuzz.partial_ratio(t, snip_n) >= 90 for t in toks)
    return source if ok else "NONE"
