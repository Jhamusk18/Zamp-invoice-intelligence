"""Generate the sample invoice PDFs from sample_data/invoices.json.

History invoices (role "seed") -> sample_data/history_invoices/   (pre-loaded into History)
Test invoices (role "demo")    -> sample_data/test_invoices/      (upload these live)

Three vendor layouts (classic / modern / minimal) so extraction can't rely on one template.
'scanned: true'  -> page is rasterised, skewed and noised, and saved as an image-only PDF (no text layer).
'hidden_text'    -> tiny white text is drawn on the page (prompt-injection attempt).
'subtotal_printed' -> the printed subtotal overrides the true sum (vendor arithmetic error).

Run:  python scripts/make_sample_invoices.py
"""
import io
import json
import random
import sys
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageFilter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.money import inr  # noqa: E402

SPEC = ROOT / "sample_data" / "invoices.json"
OUT = {"seed": ROOT / "sample_data" / "history_invoices", "demo": ROOT / "sample_data" / "test_invoices"}
VENDORS = {}


def load_vendor_addresses():
    import csv
    with open(ROOT / "sample_data" / "company" / "vendors.csv") as f:
        for r in csv.DictReader(f):
            VENDORS[r["gstin"]] = r


def totals(t, subtotal_printed=None):
    for ln in t["lines"]:
        ln["amount"] = round(ln["quantity"] * ln["unit_price"], 2)
    sub = subtotal_printed if subtotal_printed is not None else sum(l["amount"] for l in t["lines"])
    tax = round(sub * t["tax_rate"] / 100, 2)
    return sub, tax, round(sub + tax, 2)


def fmt_date(iso):
    y, m, d = iso.split("-")
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{int(d):02d} {months[int(m) - 1]} {y}"


BUYER = ["Bill to:", "Acme Retail India Pvt Ltd", "4th Floor, Prestige Tower", "MG Road, Bengaluru 560001",
         "GSTIN: 29AAACA9999K1Z2"]


def draw_lines_table(c, t, y, x0=40, widths=(260, 60, 90, 105), header_fill=None, grid=True):
    heads = ["Description", "Qty", "Rate (INR)", "Amount (INR)"]
    xs = [x0]
    for w in widths[:-1]:
        xs.append(xs[-1] + w)
    if header_fill:
        c.setFillColor(header_fill)
        c.rect(x0, y - 4, sum(widths), 18, fill=1, stroke=0)
        c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9)
    for i, h in enumerate(heads):
        if i == 0:
            c.drawString(xs[i] + 4, y + 2, h)
        else:
            c.drawRightString(xs[i] + widths[i] - 4, y + 2, h)
    c.setFillColor(colors.black)
    y -= 20
    c.setFont("Helvetica", 9)
    for ln in t["lines"]:
        c.drawString(xs[0] + 4, y, ln["description"])
        c.drawRightString(xs[1] + widths[1] - 4, y, f'{ln["quantity"]:g}')
        c.drawRightString(xs[2] + widths[2] - 4, y, inr(ln["unit_price"], symbol=False))
        c.drawRightString(xs[3] + widths[3] - 4, y, inr(ln["amount"], symbol=False))
        if grid:
            c.setStrokeColor(colors.lightgrey)
            c.line(x0, y - 6, x0 + sum(widths), y - 6)
        y -= 20
    return y, x0 + sum(widths)


def draw_totals(c, y, right, sub, tax, total, rate, bold_total=True):
    c.setFont("Helvetica", 9.5)
    for label, val in [("Subtotal", sub), (f"GST @ {rate}%", tax)]:
        c.drawRightString(right - 110, y, label)
        c.drawRightString(right - 4, y, inr(val, symbol=False))
        y -= 16
    c.setFont("Helvetica-Bold", 11 if bold_total else 9.5)
    c.drawRightString(right - 110, y, "Total (INR)")
    c.drawRightString(right - 4, y, inr(total, symbol=False))
    return y - 24


def draw_bank(c, x, y, t):
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x, y, "Payment details")
    c.setFont("Helvetica", 9)
    c.drawString(x, y - 14, f'Bank A/c No: {t["bank_account"]}')
    c.drawString(x, y - 28, f'IFSC: {t["ifsc"]}')
    return y - 44


def layout_classic(c, t, v, sub, tax, total):
    W, H = A4
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, H - 60, t["vendor_name"])
    c.setFont("Helvetica", 9)
    c.drawString(40, H - 76, v["address"])
    c.drawString(40, H - 89, f'GSTIN: {t["vendor_gstin"]}')
    c.setFont("Helvetica-Bold", 20)
    c.drawRightString(W - 40, H - 60, t.get("_title") or "TAX INVOICE")
    c.setFont("Helvetica", 9.5)
    lb = t.get("_labels") or ["Invoice No:", "Invoice Date:", "Due Date:"]
    rows = [(lb[0], t["invoice_number"]), (lb[1], fmt_date(t["invoice_date"])), (lb[2], fmt_date(t["due_date"]))]
    if t.get("po_reference"):
        rows.append(("PO Number:", t["po_reference"]))
    y = H - 82
    for k, val in rows:
        c.drawRightString(W - 140, y, k)
        c.drawRightString(W - 40, y, val)
        y -= 14
    y = H - 160
    c.setFont("Helvetica", 9)
    for i, s in enumerate(BUYER):
        c.setFont("Helvetica-Bold" if i == 0 else "Helvetica", 9)
        c.drawString(40, y, s)
        y -= 13
    y -= 20
    c.setStrokeColor(colors.black)
    c.rect(40, y - 6, 515, 20, fill=0)
    y, right = draw_lines_table(c, t, y)
    y = draw_totals(c, y - 10, right, sub, tax, total, t["tax_rate"])
    draw_bank(c, 40, y, t)
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(40, 60, "This is a computer generated invoice. Subject to Bengaluru jurisdiction.")


def layout_modern(c, t, v, sub, tax, total):
    W, H = A4
    band = colors.HexColor("#1F3A5F")
    c.setFillColor(band)
    c.rect(0, H - 110, W, 110, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(40, H - 50, t["vendor_name"].upper())
    c.setFont("Helvetica", 9)
    c.drawString(40, H - 66, v["address"])
    c.drawString(40, H - 80, f'GST No. {t["vendor_gstin"]}  |  {v["email"]}')
    c.setFont("Helvetica-Bold", 26)
    c.drawRightString(W - 40, H - 55, "Invoice")
    c.setFillColor(colors.black)
    y = H - 140
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "INVOICE #")
    c.drawString(180, y, "DATE")
    c.drawString(300, y, "PAYMENT DUE")
    c.drawString(430, y, "YOUR ORDER REF")
    c.setFont("Helvetica", 10)
    c.drawString(40, y - 15, t["invoice_number"])
    c.drawString(180, y - 15, fmt_date(t["invoice_date"]))
    c.drawString(300, y - 15, fmt_date(t["due_date"]))
    c.drawString(430, y - 15, t.get("po_reference") or "-")
    y -= 50
    for i, s in enumerate(BUYER):
        c.setFont("Helvetica-Bold" if i == 0 else "Helvetica", 9)
        c.drawString(40, y, s)
        y -= 13
    y -= 20
    y, right = draw_lines_table(c, t, y, header_fill=band, grid=True)
    y = draw_totals(c, y - 10, right, sub, tax, total, t["tax_rate"])
    c.setFillColor(colors.HexColor("#EEF2F7"))
    c.rect(36, y - 52, 260, 66, fill=1, stroke=0)
    c.setFillColor(colors.black)
    draw_bank(c, 44, y, t)
    c.setFont("Helvetica", 8)
    c.drawString(40, 60, "Thank you for your business. Please quote the invoice number with your payment.")


def layout_minimal(c, t, v, sub, tax, total):
    W, H = A4
    c.setFont("Courier-Bold", 14)
    c.drawString(40, H - 55, t["vendor_name"])
    c.setFont("Courier", 9)
    c.drawString(40, H - 70, v["address"])
    c.drawString(40, H - 82, f'GSTIN {t["vendor_gstin"]}')
    c.setFont("Courier-Bold", 12)
    c.drawString(40, H - 115, f'BILL No. {t["invoice_number"]}      Dated {fmt_date(t["invoice_date"])}')
    c.setFont("Courier", 9)
    c.drawString(40, H - 130, f'Payment due by {fmt_date(t["due_date"])}'
                 + (f'   Ref: {t["po_reference"]}' if t.get("po_reference") else ""))
    y = H - 160
    for s in BUYER[1:3]:
        c.drawString(40, y, s)
        y -= 12
    y -= 20
    c.setFont("Courier-Bold", 9)
    c.drawString(40, y, "-" * 92)
    y -= 14
    c.drawString(40, y, "Particulars")
    c.drawRightString(330, y, "Qty")
    c.drawRightString(430, y, "Rate")
    c.drawRightString(550, y, "Amount")
    y -= 10
    c.drawString(40, y, "-" * 92)
    y -= 16
    c.setFont("Courier", 9)
    for ln in t["lines"]:
        c.drawString(40, y, ln["description"][:44])
        c.drawRightString(330, y, f'{ln["quantity"]:g}')
        c.drawRightString(430, y, inr(ln["unit_price"], symbol=False))
        c.drawRightString(550, y, inr(ln["amount"], symbol=False))
        y -= 16
    c.drawString(40, y, "-" * 92)
    y -= 18
    for label, val in [("Taxable value", sub), (f"Add: GST {t['tax_rate']}%", tax)]:
        c.drawRightString(430, y, label)
        c.drawRightString(550, y, inr(val, symbol=False))
        y -= 14
    c.setFont("Courier-Bold", 11)
    c.drawRightString(430, y, "GRAND TOTAL Rs.")
    c.drawRightString(550, y, inr(total, symbol=False))
    y -= 40
    c.setFont("Courier", 9)
    c.drawString(40, y, f'Kindly remit to A/c {t["bank_account"]}  IFSC {t["ifsc"]}')
    c.drawString(40, y - 40, "For " + t["vendor_name"])
    c.drawString(40, y - 70, "Authorised Signatory")


LAYOUTS = {"classic": layout_classic, "modern": layout_modern, "minimal": layout_minimal}


def make_pdf(spec) -> bytes:
    t = json.loads(json.dumps(spec["truth"]))
    v = VENDORS.get(t["vendor_gstin"]) or spec["vendor_info"]  # unknown / lookalike vendors aren't in the vendor master
    if spec.get("doc_title"):
        t["_title"], t["_labels"] = spec["doc_title"], spec.get("doc_labels")
    sub, tax, total = totals(t, spec.get("subtotal_printed"))
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f'Invoice {t["invoice_number"]}')
    LAYOUTS[spec["layout"]](c, t, v, sub, tax, total)
    if spec.get("hidden_text"):
        c.setFillColor(colors.white)
        c.setFont("Helvetica", 1.5)
        c.drawString(60, 120, spec["hidden_text"])
    c.showPage()
    c.save()
    data = buf.getvalue()
    if spec.get("scanned"):
        data = scanify(data, seed=hash(spec["key"]) % 1000)
    return data


def scanify(pdf_bytes: bytes, seed: int = 1) -> bytes:
    """Rasterise, skew, add grain, and save as an image-only PDF (no text layer)."""
    rnd = random.Random(seed)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pix = doc[0].get_pixmap(dpi=200, colorspace=fitz.csGRAY)
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    img = img.rotate(rnd.uniform(-1.2, 1.2), expand=False, fillcolor=255, resample=Image.BICUBIC)
    px = img.load()
    for _ in range(int(img.width * img.height * 0.002)):
        x, y = rnd.randrange(img.width), rnd.randrange(img.height)
        px[x, y] = rnd.randrange(80, 200)
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    img = img.point(lambda p: min(255, int(p * 0.93 + 14)))  # photocopy grey
    out = io.BytesIO()
    img.save(out, format="PDF", resolution=200)
    return out.getvalue()


def main(only=None):
    """only: list of key prefixes (e.g. ["X4", "X5"]) to (re)generate just those files; existing PDFs stay byte-identical."""
    load_vendor_addresses()
    for d in OUT.values():
        d.mkdir(parents=True, exist_ok=True)
    specs = json.loads(SPEC.read_text())["invoices"]
    for s in specs:
        if only and not any(s["key"].startswith(o) for o in only):
            continue
        path = OUT[s["role"]] / f'{s["key"]}.pdf'
        path.write_bytes(make_pdf(s))
        print("wrote", path.relative_to(ROOT))


if __name__ == "__main__":
    main(sys.argv[1:] or None)
