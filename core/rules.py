"""Business checks. Pure Python, deterministic, no AI.

evaluate() takes an extracted invoice + a read-only snapshot of company data and returns EVERY finding.
Business findings never stop evaluation - all checks always run. The decision is made afterwards
(core/decision.py) from the full list.

Result meaning:  PASS / NA  -> fine        WARN -> Needs Attention        FAIL -> Blocked
"""
import re
from dataclasses import dataclass, field
from datetime import date

from rapidfuzz import fuzz

from core.db import rows
from core.models import CRITICAL_FIELDS, InvoiceExtraction
from core.money import inr, mask_account
from core.policy import VENDOR_MATCH_THRESHOLDS

GROUPS = ["Document", "Vendor", "Duplicate", "Purchase order", "Policy"]

# When several problems exist, the one-line reason shown is the most severe, then the earliest in this list.
PRIORITY = ["NOT_AN_INVOICE", "DUPLICATE_EXACT", "VENDOR_BLOCKED", "VENDOR_INACTIVE", "UNKNOWN_VENDOR",
            "PRICE_OVER_LIMIT", "BANK_CHANGED", "HIDDEN_TEXT", "VENDOR_LOOKALIKE", "TAX_ID_MISMATCH",
            "VENDOR_NAME_MISMATCH", "DUPLICATE_SUSPECTED", "READS_DISAGREE", "UNVERIFIED_FIELD", "MISSING_FIELDS",
            "VENDOR_MATH_ERROR", "PO_OVERBILLED", "QTY_EXCEEDS_RECEIPT", "NO_RECEIPT", "PRICE_VARIANCE",
            "LINE_MISMATCH", "LINE_NOT_ON_PO", "QTY_OVER_PO", "PO_INFERRED", "NO_PO", "PO_OTHER_VENDOR",
            "PO_CLOSED", "PO_EXPIRED", "CURRENCY_MISMATCH", "DATE_INVALID", "PROFORMA", "TAX_RATE_UNUSUAL",
            "TAX_ID_INVALID", "OVER_AUTO_LIMIT"]

REASON_LABEL = {
    "NOT_AN_INVOICE": "Document is not an invoice", "DUPLICATE_EXACT": "Already received this invoice",
    "VENDOR_BLOCKED": "Vendor is blocked", "VENDOR_INACTIVE": "Vendor is inactive",
    "UNKNOWN_VENDOR": "Vendor is not on the approved list", "PRICE_OVER_LIMIT": "Price far above the PO",
    "BANK_CHANGED": "Bank account differs from the vendor record", "HIDDEN_TEXT": "Hidden text found in the PDF",
    "VENDOR_LOOKALIKE": "Vendor name looks like, but isn't, an approved vendor",
    "TAX_ID_MISMATCH": "GSTIN differs from the vendor record", "VENDOR_NAME_MISMATCH": "Vendor name differs from the record",
    "DUPLICATE_SUSPECTED": "Possible duplicate", "READS_DISAGREE": "Two reads of the invoice disagree",
    "UNVERIFIED_FIELD": "Key value could not be verified in the document", "MISSING_FIELDS": "Required information missing",
    "VENDOR_MATH_ERROR": "Invoice arithmetic doesn't add up", "PO_OVERBILLED": "Would exceed the PO balance",
    "QTY_EXCEEDS_RECEIPT": "Billed more than received", "NO_RECEIPT": "Goods not received yet",
    "PRICE_VARIANCE": "Price above the PO", "LINE_MISMATCH": "Line items don't match the PO",
    "LINE_NOT_ON_PO": "Item not on the PO", "QTY_OVER_PO": "Quantity above the PO",
    "PO_INFERRED": "No PO number - suggested match needs confirming", "NO_PO": "No matching purchase order",
    "PO_OTHER_VENDOR": "PO belongs to another vendor", "PO_CLOSED": "PO is closed", "PO_EXPIRED": "PO has expired",
    "CURRENCY_MISMATCH": "Currency differs from the PO", "DATE_INVALID": "Date problem", "PROFORMA": "Proforma, not a tax invoice",
    "TAX_RATE_UNUSUAL": "Unusual tax rate", "TAX_ID_INVALID": "GSTIN format invalid", "OVER_AUTO_LIMIT": "Above the auto-approve limit",
}

GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
GST_RATES = {0, 5, 12, 18, 28}
LINE_MATCH_MIN = 0.60
PO_INFER_MIN = 0.60


@dataclass
class Finding:
    check_id: str
    group: str
    label: str
    result: str                 # PASS / WARN / FAIL / NA
    message: str
    reason_code: str | None = None
    expected: str | None = None
    actual: str | None = None
    details: dict = field(default_factory=dict)


@dataclass
class EvalResult:
    findings: list
    vendor_id: str | None = None
    po_number: str | None = None
    po_match_type: str = "NONE"
    line_map: dict = field(default_factory=dict)   # invoice line index -> po line_no
    allocation_amount: float | None = None


# ---------------------------------------------------------------- snapshot of company data

@dataclass
class Snapshot:
    vendors: list
    pos: dict
    po_lines: dict
    received: dict          # (po, line_no) -> qty received
    prior_invoices: list    # processed before this one
    billed_amount: dict     # po -> {'committed': x, 'reserved': y}  (earlier invoices only)
    billed_qty: dict        # (po, line_no) -> qty billed by earlier active invoices


def load_snapshot(conn, invoice_id: int | None) -> Snapshot:
    """Read-only view of company data + invoices processed BEFORE this one.
    'Before' = lower id, so re-evaluating an old invoice (what-if) doesn't see later ones."""
    limit = invoice_id if invoice_id is not None else 10**12
    pos = {p["po_number"]: p for p in rows(conn, "SELECT * FROM purchase_orders")}
    po_lines = {}
    for l in rows(conn, "SELECT * FROM po_lines ORDER BY po_number, line_no"):
        po_lines.setdefault(l["po_number"], []).append(l)
    received = {(r["po_number"], r["line_no"]): r["q"] for r in rows(
        conn, "SELECT po_number, line_no, SUM(quantity_received) q FROM goods_receipts GROUP BY 1,2")}
    prior = rows(conn, """SELECT id, vendor_id, vendor_name, invoice_number, invoice_number_norm, total, invoice_date, status
                          FROM invoices WHERE id < ? AND run_state='DONE'""", (limit,))
    billed_amount = {}
    for a in rows(conn, """SELECT po_number, state, SUM(amount) s FROM po_allocations
                           WHERE invoice_id < ? AND state IN ('RESERVED','COMMITTED') GROUP BY 1,2""", (limit,)):
        billed_amount.setdefault(a["po_number"], {"COMMITTED": 0.0, "RESERVED": 0.0})[a["state"]] = a["s"]
    billed_qty = {}
    for b in rows(conn, """SELECT a.po_number, l.po_line_no, SUM(l.quantity) q FROM invoice_lines l
                           JOIN po_allocations a ON a.invoice_id = l.invoice_id
                           WHERE l.invoice_id < ? AND a.state IN ('RESERVED','COMMITTED') AND l.po_line_no IS NOT NULL
                           GROUP BY 1,2""", (limit,)):
        billed_qty[(b["po_number"], b["po_line_no"])] = b["q"]
    return Snapshot(rows(conn, "SELECT * FROM vendors"), pos, po_lines, received, prior, billed_amount, billed_qty)


# ---------------------------------------------------------------- helpers

_SUFFIX = re.compile(r"\b(pvt|private|ltd|limited|llp|inc|co|company|corp|corporation|the)\b")


def norm_name(s):
    s = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    return re.sub(r"\s+", " ", _SUFFIX.sub(" ", s)).strip()


def name_score(a, vendor):
    names = [vendor["name"]] + [x for x in (vendor.get("aliases") or "").split("|") if x]
    return max(fuzz.token_sort_ratio(norm_name(a), norm_name(n)) for n in names)


def norm_invoice_number(s):
    if not s:
        return None
    s = re.sub(r"[^A-Z0-9]", "", s.upper())
    s = re.sub(r"^(INVOICE|INV|BILL|NO)+", "", s)
    return s.lstrip("0") or "0"


def norm_po(s):
    d = re.sub(r"\D", "", s or "")
    return d or None


def digits(s):
    return re.sub(r"\D", "", s or "")


def parse_date(s):
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def desc_score(a, b):
    return fuzz.token_set_ratio(norm_name(a), norm_name(b)) / 100


def close(a, b, tol):
    return a is not None and b is not None and abs(a - b) <= tol


# ---------------------------------------------------------------- the checks

def evaluate(inv: InvoiceExtraction, snap: Snapshot, policy: dict, *, verification: dict | None = None,
             hidden_text: list | None = None, reads_agree: bool | None = None, disagreements: list | None = None,
             semantic_scores: dict | None = None, today: date | None = None) -> EvalResult:
    """semantic_scores: optional {(invoice_line_index, po_number, po_line_no): 0..1} from the AI meaning-judge.
    Python still does all scoring and deciding; the AI only says how alike two descriptions are."""
    today = today or date.today()
    rules = policy["rules"]
    F = []
    res = EvalResult(F)

    def add(*a, **k):
        F.append(Finding(*a, **k))

    def dscore(i, po, line):
        if semantic_scores and (i, po, line["line_no"]) in semantic_scores:
            return max(semantic_scores[(i, po, line["line_no"])], desc_score(inv.lines[i].description, line["description"]))
        return desc_score(inv.lines[i].description, line["description"])

    # ======================= Document =======================
    dt = inv.document_type
    if dt == "INVOICE":
        add("DOC_TYPE", "Document", "Document type", "PASS", "It is a tax invoice.")
    elif dt == "PROFORMA":
        add("DOC_TYPE", "Document", "Document type", "WARN", "This is a proforma invoice, not a tax invoice. Ask for the final tax invoice before paying.", "PROFORMA", "Tax invoice", "Proforma")
    else:
        add("DOC_TYPE", "Document", "Document type", "FAIL", f"This document is a {dt.replace('_', ' ').lower()}, not an invoice. Nothing is payable.", "NOT_AN_INVOICE", "Tax invoice", dt.replace("_", " ").title())

    missing = [f for f in ("vendor_name", "invoice_number", "invoice_date", "total") if not inv.value(f)]
    if missing:
        add("REQUIRED_FIELDS", "Document", "Required fields", "WARN", "Missing: " + ", ".join(m.replace("_", " ") for m in missing) + ".", "MISSING_FIELDS", details={"missing": missing})
    else:
        add("REQUIRED_FIELDS", "Document", "Required fields", "PASS", "Vendor, invoice number, date and total are all present.")

    if verification is None:
        add("EVIDENCE", "Document", "Evidence check", "NA", "Not run for this record.")
    else:
        unver = [f for f in CRITICAL_FIELDS if inv.value(f) not in (None, "") and verification.get(f) == "NONE"]
        src = "OCR text" if "OCR" in verification.values() else "document text"
        if unver and all(v == "NONE" for v in verification.values()):
            add("EVIDENCE", "Document", "Evidence check", "WARN", "Scanned invoice and no OCR text to check against, so no value could be confirmed. A person must compare the key values with the PDF.", "UNVERIFIED_FIELD", details={"fields": unver})
        elif unver:
            add("EVIDENCE", "Document", "Evidence check", "WARN", "Could not confirm in the document: " + ", ".join(u.replace("_", " ") for u in unver) + ". A person must check these against the PDF.", "UNVERIFIED_FIELD", details={"fields": unver})
        else:
            add("EVIDENCE", "Document", "Evidence check", "PASS", f"Every key value was found in the {src}.")

    if hidden_text:
        add("HIDDEN_TEXT", "Document", "Hidden text scan", "WARN",
            f"Found {len(hidden_text)} piece(s) of text a person can't see ({hidden_text[0]['reason']}): \"{hidden_text[0]['text'][:120]}\". It was ignored, and the invoice is held.",
            "HIDDEN_TEXT", details={"items": hidden_text})
    elif hidden_text is None:
        add("HIDDEN_TEXT", "Document", "Hidden text scan", "NA", "Scanned image - there is no text layer to hide text in.")
    else:
        add("HIDDEN_TEXT", "Document", "Hidden text scan", "PASS", "No hidden text.")

    if reads_agree is False:
        add("READS_AGREE", "Document", "Second read", "WARN", "The invoice was read twice and the reads disagree on: " + ", ".join(d["field"] for d in (disagreements or [])) + ". The extraction can't be trusted without a person.", "READS_DISAGREE", details={"disagreements": disagreements})
    elif reads_agree is True:
        add("READS_AGREE", "Document", "Second read", "PASS", "Numbers didn't add up on the first read, so it was re-read; both reads agree.")
    else:
        add("READS_AGREE", "Document", "Second read", "NA", "Not needed - numbers added up on the first read.")

    # arithmetic
    tol = policy["math_tolerance"]
    problems = []
    for i, l in enumerate(inv.lines):
        if l.quantity is not None and l.unit_price is not None and l.amount is not None and not close(l.quantity * l.unit_price, l.amount, tol):
            problems.append(f"line {i + 1}: {l.quantity:g} × {inr(l.unit_price)} ≠ {inr(l.amount)}")
    amounts = [l.amount for l in inv.lines]
    line_sum = round(sum(a for a in amounts if a is not None), 2) if amounts and None not in amounts else None
    if line_sum is not None and inv.subtotal is not None and not close(line_sum, inv.subtotal, tol):
        problems.append(f"items add up to {inr(line_sum)} but the subtotal says {inr(inv.subtotal)}")
    if None not in (inv.subtotal, inv.tax, inv.total) and not close(inv.subtotal + inv.tax, inv.total, tol):
        problems.append(f"subtotal {inr(inv.subtotal)} + tax {inr(inv.tax)} ≠ total {inr(inv.total)}")
    if problems:
        add("ARITHMETIC", "Document", "Amounts & tax", "WARN", "The invoice's own numbers don't add up: " + "; ".join(problems) + ".", "VENDOR_MATH_ERROR", details={"problems": problems})
    else:
        rate = round(inv.tax / inv.subtotal * 100, 1) if inv.subtotal and inv.tax is not None else None
        if rate is not None and not any(abs(rate - g) <= 0.2 for g in GST_RATES):
            add("ARITHMETIC", "Document", "Amounts & tax", "WARN", f"Numbers add up, but tax is {rate}% of the subtotal, which isn't a standard GST rate.", "TAX_RATE_UNUSUAL", "0/5/12/18/28%", f"{rate}%")
        else:
            add("ARITHMETIC", "Document", "Amounts & tax", "PASS", "Line items, subtotal, tax and total all add up" + (f" (GST {rate:g}%)." if rate is not None else "."))

    # ======================= Vendor =======================
    vendor = None
    threshold = VENDOR_MATCH_THRESHOLDS[policy["vendor_match"]]
    g = (inv.vendor_gstin or "").upper().replace(" ", "")
    by_gstin = next((v for v in snap.vendors if g and v["gstin"] == g), None)
    if by_gstin:
        vendor = by_gstin
        sc = name_score(inv.vendor_name, vendor)
        if sc >= threshold or not rules["vendor_name"]:
            note = "" if sc >= threshold else " (name check is turned off)"
            add("VENDOR", "Vendor", "Vendor check", "PASS", f"Matched {vendor['name']} by GSTIN{note}.", expected=vendor["name"], actual=inv.vendor_name)
        else:
            add("VENDOR", "Vendor", "Vendor check", "WARN", f"GSTIN belongs to {vendor['name']}, but the name on the invoice is \"{inv.vendor_name}\" (similarity {sc:.0f}%, needs {threshold}%).", "VENDOR_NAME_MISMATCH", vendor["name"], inv.vendor_name)
    else:
        scored = sorted(((name_score(inv.vendor_name, v), v) for v in snap.vendors), key=lambda x: -x[0]) if inv.vendor_name else []
        best_s, best_v = scored[0] if scored else (0, None)
        # A GSTIN we can trust (confirmed in the document, or structured input) that belongs to NO approved vendor means a
        # different legal entity - however close the name. That's impersonation, not a match.
        gstin_trusted = bool(g) and GSTIN_RE.match(g) and (verification is None or verification.get("vendor_gstin") in ("TEXT", "OCR"))
        if best_v and best_s >= 70 and gstin_trusted:
            add("VENDOR", "Vendor", "Vendor check", "FAIL",
                f"\"{inv.vendor_name}\" looks like approved vendor {best_v['name']} ({best_s:.0f}% similar), but GSTIN {g} belongs to a "
                f"different company (on file: {best_v['gstin']}). Possible impersonation - don't pay.",
                "VENDOR_LOOKALIKE", best_v["gstin"], g, details={"lookalike_of": best_v["vendor_id"]})
            best_v = None
        elif best_v and best_s >= threshold:
            vendor = best_v
            add("VENDOR", "Vendor", "Vendor check", "PASS", f"Matched {vendor['name']} by name ({best_s:.0f}% similar).", expected=vendor["name"], actual=inv.vendor_name)
        elif best_v and best_s >= 70:
            # similar name, no trustworthy GSTIN (missing, or not confirmed in the document): might be a typo or misread -> a person
            add("VENDOR", "Vendor", "Vendor check", "WARN",
                f"\"{inv.vendor_name}\" looks like approved vendor {best_v['name']} ({best_s:.0f}% similar), but there's no confirmed "
                "GSTIN to prove it's the same company. Check before paying.",
                "VENDOR_LOOKALIKE", best_v["name"], inv.vendor_name, details={"lookalike_of": best_v["vendor_id"]})
        else:
            add("VENDOR", "Vendor", "Vendor check", "FAIL", f"\"{inv.vendor_name or 'Unknown'}\" is not on the approved vendor list. Route to vendor onboarding.", "UNKNOWN_VENDOR", "An approved vendor", inv.vendor_name)
    if vendor and vendor["status"] != "ACTIVE":
        code = "VENDOR_BLOCKED" if vendor["status"] == "BLOCKED" else "VENDOR_INACTIVE"
        F[-1] = Finding("VENDOR", "Vendor", "Vendor check", "FAIL", f"{vendor['name']} is {vendor['status'].lower()} in the vendor master. Invoices from this vendor are not paid.", code, "ACTIVE", vendor["status"])
    res.vendor_id = vendor["vendor_id"] if vendor else None

    # tax id
    if not g:
        add("TAX_ID", "Vendor", "GSTIN check", "WARN" if vendor else "NA", "No GSTIN printed on the invoice." if vendor else "Vendor not identified.", "MISSING_FIELDS" if vendor else None)
    elif not GSTIN_RE.match(g):
        add("TAX_ID", "Vendor", "GSTIN check", "WARN", f"GSTIN \"{g}\" is not a valid format.", "TAX_ID_INVALID", "15-character GSTIN", g)
    elif vendor and vendor["gstin"] != g:
        add("TAX_ID", "Vendor", "GSTIN check", "WARN", "GSTIN on the invoice differs from the vendor record.", "TAX_ID_MISMATCH", vendor["gstin"], g)
    elif vendor:
        add("TAX_ID", "Vendor", "GSTIN check", "PASS", "GSTIN matches the vendor record.", expected=vendor["gstin"], actual=g)
    else:
        add("TAX_ID", "Vendor", "GSTIN check", "NA", "Vendor not identified.")

    # bank (locked rule)
    if not vendor:
        add("BANK", "Vendor", "Bank account check", "NA", "Vendor not identified, so there is no account on file to compare.")
    elif not inv.bank_account:
        add("BANK", "Vendor", "Bank account check", "PASS", "No bank details on the invoice; payment would go to the account on file.")
    elif digits(inv.bank_account) != digits(vendor["bank_account"]) or (inv.ifsc and vendor["ifsc"] and inv.ifsc.upper() != vendor["ifsc"].upper()):
        add("BANK", "Vendor", "Bank account check", "WARN",
            f"Invoice account {mask_account(digits(inv.bank_account))} differs from the account on file {mask_account(vendor['bank_account'])}. Verify by phone using the number on file - not one from the invoice.",
            "BANK_CHANGED", mask_account(vendor["bank_account"]), mask_account(digits(inv.bank_account)))
    else:
        add("BANK", "Vendor", "Bank account check", "PASS", f"Matches the account on file ({mask_account(vendor['bank_account'])}).", mask_account(vendor["bank_account"]), mask_account(digits(inv.bank_account)))

    # ======================= Duplicate (locked) =======================
    num = norm_invoice_number(inv.invoice_number)
    vkey = res.vendor_id
    same_vendor = [p for p in snap.prior_invoices
                   if (vkey and p["vendor_id"] == vkey) or (not vkey and norm_name(p["vendor_name"]) == norm_name(inv.vendor_name))]
    exact = next((p for p in same_vendor if num and p["invoice_number_norm"] == num), None)
    if exact:
        add("DUPLICATE", "Duplicate", "Duplicate check", "FAIL",
            f"Same vendor and same invoice number as {exact['invoice_number']} (already received; status {exact['status']}). \"{inv.invoice_number}\" and \"{exact['invoice_number']}\" are the same number once formatting is removed.",
            "DUPLICATE_EXACT", "A new invoice number", inv.invoice_number, details={"duplicate_of": exact["id"]})
    else:
        d0 = parse_date(inv.invoice_date)
        fuzzy = None
        for p in same_vendor:
            amt_ok = inv.total and p["total"] and abs(inv.total - p["total"]) <= p["total"] * policy["fuzzy_dup_amount_pct"] / 100
            dp = parse_date(p["invoice_date"])
            date_ok = d0 and dp and abs((d0 - dp).days) <= policy["fuzzy_dup_days"]
            num_sim = fuzz.ratio(num or "", p["invoice_number_norm"] or "") >= 85
            # Same amount ALONE is normal (monthly rent, recurring freight). Suspect a duplicate only when the number is
            # also similar (INV-1001 vs INV-1001A), or the same amount arrives within a few days.
            if amt_ok and (num_sim or date_ok):
                fuzzy = (p, "similar invoice number" if num_sim else f"dated within {policy['fuzzy_dup_days']} days")
                break
        if fuzzy:
            p, why = fuzzy
            add("DUPLICATE", "Duplicate", "Duplicate check", "WARN",
                f"Looks like {p['invoice_number']}: same vendor, amount within {policy['fuzzy_dup_amount_pct']:g}% and {why}, but a different number.",
                "DUPLICATE_SUSPECTED", details={"duplicate_of": p["id"]})
        else:
            add("DUPLICATE", "Duplicate", "Duplicate check", "PASS", "No earlier invoice with this number, or with the same amount and a close date, from this vendor.")

    # ======================= Purchase order =======================
    po = None
    if not rules["po_match"]:
        for cid, lbl in [("PO_MATCH", "PO matching"), ("PO_LINES", "Line items vs PO"), ("PO_BALANCE", "PO balance"), ("RECEIPT", "Goods received (3-way)")]:
            add(cid, "Purchase order", lbl, "NA", "Order match check is turned off in Approval Rules.")
    else:
        ref = norm_po(inv.po_reference)
        if ref:
            po = next((p for n, p in snap.pos.items() if norm_po(n) == ref), None)
        if po and vendor and po["vendor_id"] != vendor["vendor_id"]:
            add("PO_MATCH", "Purchase order", "PO matching", "WARN", f"{po['po_number']} belongs to a different vendor.", "PO_OTHER_VENDOR", vendor["vendor_id"], po["vendor_id"])
            po = None
        elif po:
            res.po_match_type = "EXPLICIT"
            d0 = parse_date(inv.invoice_date)
            if po["status"] == "CLOSED":
                add("PO_MATCH", "Purchase order", "PO matching", "WARN", f"{po['po_number']} is closed.", "PO_CLOSED", "OPEN", "CLOSED")
            elif d0 and po["valid_until"] and d0 > parse_date(po["valid_until"]):
                add("PO_MATCH", "Purchase order", "PO matching", "WARN", f"{po['po_number']} expired on {po['valid_until']}; invoice is dated {inv.invoice_date}.", "PO_EXPIRED", f"on/before {po['valid_until']}", inv.invoice_date)
            elif po["currency"] and inv.currency and po["currency"] != inv.currency.upper():
                add("PO_MATCH", "Purchase order", "PO matching", "WARN", f"Invoice is in {inv.currency}, the PO is in {po['currency']}.", "CURRENCY_MISMATCH", po["currency"], inv.currency)
            else:
                add("PO_MATCH", "Purchase order", "PO matching", "PASS", f"Matches {po['po_number']} (open, {po['po_type'].lower()}).", po["po_number"], inv.po_reference)
        elif vendor:
            # infer: score each open PO of this vendor on descriptions, amount and dates (Python arithmetic)
            cands = []
            for p in (p for p in snap.pos.values() if p["vendor_id"] == vendor["vendor_id"] and p["status"] == "OPEN"):
                lines = snap.po_lines.get(p["po_number"], [])
                if not inv.lines or not lines:
                    continue
                d = sum(max(dscore(i, p["po_number"], l) for l in lines) for i in range(len(inv.lines))) / len(inv.lines)
                used = sum(snap.billed_amount.get(p["po_number"], {}).values())
                remaining = p["total_amount"] - used
                sub = inv.subtotal or 0
                a = max(0.0, 1 - min(abs(sub - p["total_amount"]), abs(sub - remaining)) / max(p["total_amount"], 1))
                d0, pd, pv = parse_date(inv.invoice_date), parse_date(p["po_date"]), parse_date(p["valid_until"])
                t = 1.0 if (d0 and pd and pd <= d0 and (not pv or d0 <= pv)) else 0.0
                score = 0.5 * d + 0.35 * a + 0.15 * t
                cands.append({"po_number": p["po_number"], "score": round(score, 2), "description": round(d, 2), "amount": round(a, 2), "dates": t})
            cands.sort(key=lambda c: -c["score"])
            why = f"No PO number on the invoice{'' if not ref else f' (\"{inv.po_reference}\" not found)'}"
            if cands and cands[0]["score"] >= PO_INFER_MIN:
                po = snap.pos[cands[0]["po_number"]]
                res.po_match_type = "INFERRED"
                add("PO_MATCH", "Purchase order", "PO matching", "WARN",
                    f"{why}. Best match is {po['po_number']} (score {cands[0]['score']:.2f}: items {cands[0]['description']:.2f}, amount {cands[0]['amount']:.2f}). A person must confirm - inferred matches are never auto-approved.",
                    "PO_INFERRED", "PO number on invoice", inv.po_reference or "none", details={"candidates": cands[:3]})
            else:
                add("PO_MATCH", "Purchase order", "PO matching", "WARN", f"{why}, and no open PO of this vendor fits.", "NO_PO", details={"candidates": cands[:3]})
        else:
            add("PO_MATCH", "Purchase order", "PO matching", "NA" if not ref else "WARN", "Vendor not identified, so no PO can be matched." if not ref else f"PO \"{inv.po_reference}\" not found.", None if not ref else "NO_PO")

        if po:
            res.po_number = po["po_number"]
            plines = snap.po_lines.get(po["po_number"], [])
            # ---- line by line ----
            tolp, cap, rej = policy["tolerance_pct"], policy["tolerance_cap"], policy["reject_variance_pct"]
            lres, worst, worst_code = [], "PASS", None
            rank = {"PASS": 0, "WARN": 1, "FAIL": 2}
            for i, l in enumerate(inv.lines):
                best = max(plines, key=lambda pl: dscore(i, po["po_number"], pl)) if plines else None
                s = dscore(i, po["po_number"], best) if best else 0
                r, code, note = "PASS", None, ""
                if not best or s < LINE_MATCH_MIN:
                    r, code, note = "WARN", "LINE_NOT_ON_PO", "not on the PO"
                else:
                    res.line_map[i] = best["line_no"]
                    if l.unit_price is not None and best["unit_price"]:
                        var = (l.unit_price - best["unit_price"]) / best["unit_price"] * 100
                        qty = l.quantity or 0
                        diff = (l.unit_price - best["unit_price"]) * qty
                        allowed = min(tolp / 100 * best["unit_price"] * qty, cap)
                        if abs(diff) <= allowed + 0.005 and abs(var) <= tolp + 1e-9:
                            note = "price matches" if abs(var) < 0.005 else f"price {var:+.1f}% (within {tolp:g}%)"
                        elif var > rej:
                            r, code, note = "FAIL", "PRICE_OVER_LIMIT", f"price {var:+.1f}% vs PO (over the {rej:g}% limit)"
                        elif var > 0:
                            r, code, note = "WARN", "PRICE_VARIANCE", f"price {var:+.1f}% vs PO ({inr(diff)} over, allowed {inr(allowed)})"
                        else:
                            r, code, note = "WARN", "LINE_MISMATCH", f"price {var:+.1f}% vs PO - billed below the PO price; check it is the right item"
                    if po["po_type"] == "SERVICE" and l.quantity is not None:
                        left = best["quantity"] - snap.billed_qty.get((po["po_number"], best["line_no"]), 0)
                        if l.quantity > left + 1e-9 and r == "PASS":
                            r, code, note = "WARN", "QTY_OVER_PO", f"qty {l.quantity:g} but only {left:g} left on the PO"
                lres.append({"invoice_line": l.description, "po_line": best["description"] if best and s >= LINE_MATCH_MIN else None,
                             "match": round(s, 2), "qty": l.quantity, "invoice_price": l.unit_price,
                             "po_price": best["unit_price"] if best and s >= LINE_MATCH_MIN else None, "result": r, "note": note})
                if rank[r] > rank[worst] or (rank[r] == rank[worst] and r != "PASS" and PRIORITY.index(code) < PRIORITY.index(worst_code)):
                    worst, worst_code = r, code
            msg = "All lines match the PO." if worst == "PASS" else "; ".join(f"{x['invoice_line']}: {x['note']}" for x in lres if x["result"] != "PASS") + "."
            if worst == "PASS" and any("within" in x["note"] for x in lres):
                msg = "All lines match the PO within tolerance: " + "; ".join(f"{x['invoice_line']}: {x['note']}" for x in lres) + "."
            add("PO_LINES", "Purchase order", "Line items vs PO", worst, msg, worst_code, details={"lines": lres})

            # ---- balance across all invoices on this PO (split invoices) ----
            ba = snap.billed_amount.get(po["po_number"], {"COMMITTED": 0.0, "RESERVED": 0.0})
            used = ba.get("COMMITTED", 0) + ba.get("RESERVED", 0)
            sub = inv.subtotal or 0
            allowed_over = min(tolp / 100 * po["total_amount"], cap)
            after = used + sub
            bal = {"po_total": po["total_amount"], "committed": ba.get("COMMITTED", 0), "reserved": ba.get("RESERVED", 0), "this_invoice": sub, "after": after}
            if after > po["total_amount"] + allowed_over + 0.005:
                add("PO_BALANCE", "Purchase order", "PO balance", "WARN",
                    f"PO {po['po_number']} is {inr(po['total_amount'])}. Already billed {inr(used)} (paid/approved {inr(ba.get('COMMITTED', 0))}, on hold {inr(ba.get('RESERVED', 0))}). This invoice adds {inr(sub)} → {inr(after)}, over by {inr(after - po['total_amount'])} (allowed {inr(allowed_over)}).",
                    "PO_OVERBILLED", f"≤ {inr(po['total_amount'] + allowed_over)}", inr(after), details=bal)
            else:
                add("PO_BALANCE", "Purchase order", "PO balance", "PASS", f"{inr(po['total_amount'] - after)} of {inr(po['total_amount'])} left after this invoice.", details=bal)
            res.allocation_amount = sub

            # ---- three-way: billed vs received ----
            if po["po_type"] == "SERVICE":
                add("RECEIPT", "Purchase order", "Goods received (3-way)", "NA", "Service PO - no goods receipt, so a 2-way match (invoice vs PO) is used.")
            elif not rules["short_delivery"]:
                add("RECEIPT", "Purchase order", "Goods received (3-way)", "NA", "Short delivery check is turned off in Approval Rules.")
            else:
                issues, rows3 = [], []
                for i, l in enumerate(inv.lines):
                    ln = res.line_map.get(i)
                    if ln is None or l.quantity is None:
                        continue
                    pl = next(x for x in plines if x["line_no"] == ln)
                    rec = snap.received.get((po["po_number"], ln), 0)
                    before = snap.billed_qty.get((po["po_number"], ln), 0)
                    avail = rec - before
                    rows3.append({"item": pl["description"], "ordered": pl["quantity"], "received": rec, "billed_before": before, "invoiced": l.quantity})
                    if l.quantity > avail * (1 + policy["qty_tolerance_pct"] / 100) + 1e-9:
                        issues.append(f"{pl['description']}: billing {l.quantity:g}, received {rec:g}" + (f", {before:g} already billed" if before else "") + f" → only {max(avail, 0):g} can be billed")
                if not rows3:
                    add("RECEIPT", "Purchase order", "Goods received (3-way)", "NA", "No line could be matched to the PO, so quantities can't be compared.")
                elif all(r["received"] == 0 for r in rows3):
                    add("RECEIPT", "Purchase order", "Goods received (3-way)", "WARN", "No goods receipt recorded for this PO yet.", "NO_RECEIPT", details={"rows": rows3})
                elif issues:
                    add("RECEIPT", "Purchase order", "Goods received (3-way)", "WARN", "; ".join(issues) + ".", "QTY_EXCEEDS_RECEIPT", details={"rows": rows3})
                else:
                    add("RECEIPT", "Purchase order", "Goods received (3-way)", "PASS", "Billed quantities are covered by goods received.", details={"rows": rows3})
        elif not any(f.check_id == "PO_LINES" for f in F):
            for cid, lbl in [("PO_LINES", "Line items vs PO"), ("PO_BALANCE", "PO balance"), ("RECEIPT", "Goods received (3-way)")]:
                add(cid, "Purchase order", lbl, "NA", "No purchase order matched.")

    # ======================= Policy =======================
    d0, dd = parse_date(inv.invoice_date), parse_date(inv.due_date)
    dprob = []
    if d0 and d0 > today:
        dprob.append(f"invoice is dated in the future ({inv.invoice_date})")
    if d0 and dd and dd < d0:
        dprob.append("due date is before the invoice date")
    if d0 and po and parse_date(po["po_date"]) and d0 < parse_date(po["po_date"]):
        dprob.append(f"invoice is dated before the PO ({po['po_date']})")
    if inv.invoice_date and not d0:
        dprob.append(f"invoice date \"{inv.invoice_date}\" can't be read")
    add("DATES", "Policy", "Dates", "WARN" if dprob else "PASS", ("; ".join(dprob) + ".").capitalize() if dprob else "Dates are consistent.", "DATE_INVALID" if dprob else None)

    if inv.currency and inv.currency.upper() != "INR" and not any(f.reason_code == "CURRENCY_MISMATCH" for f in F):
        add("CURRENCY", "Policy", "Currency", "WARN", f"Invoice is in {inv.currency}; the company pays this vendor in INR.", "CURRENCY_MISMATCH", "INR", inv.currency)
    else:
        add("CURRENCY", "Policy", "Currency", "PASS" if not any(f.reason_code == "CURRENCY_MISMATCH" for f in F) else "NA", "INR." if inv.currency else "No currency printed; INR assumed (domestic vendor).")

    lim = policy["auto_approve_limit"]
    if inv.total is not None and inv.total > lim:
        add("AUTO_LIMIT", "Policy", "Auto-approve limit", "WARN", f"Total {inr(inv.total)} is above the auto-approve limit of {inr(lim)}, so a person must approve it.", "OVER_AUTO_LIMIT", f"≤ {inr(lim)}", inr(inv.total))
    else:
        add("AUTO_LIMIT", "Policy", "Auto-approve limit", "PASS", f"Total is within the auto-approve limit of {inr(lim)}.")
    return res
