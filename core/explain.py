"""Summary for the AP team + the vendor email shown after a reviewer picks a decision and reason.

1. Build a ledger (facts only) from the stored findings.
2. Template text is always produced (works without AI, zero cost).
3. If AI is available, it rewrites the text from the ledger. Python then checks every number in the AI's text
   appears in the ledger; if any doesn't, the AI text is thrown away and the template is used.
"""
import json
import re

from core.db import row, rows
from core.decision import LABEL
from core.money import inr

VENDOR_FACING = {"BANK_CHANGED", "QTY_EXCEEDS_RECEIPT", "PRICE_VARIANCE", "PRICE_OVER_LIMIT", "LINE_MISMATCH",
                 "LINE_NOT_ON_PO", "VENDOR_MATH_ERROR", "MISSING_FIELDS", "DUPLICATE_EXACT", "DUPLICATE_SUSPECTED",
                 "PO_INFERRED", "NO_PO", "PROFORMA", "PO_OVERBILLED", "TAX_ID_MISMATCH", "DATE_INVALID",
                 "CURRENCY_MISMATCH", "NOT_AN_INVOICE", "QTY_OVER_PO", "NO_RECEIPT"}

ASK = {
    "BANK_CHANGED": "The bank account on this invoice is different from the one we have on record. For your security we will call you on the phone number in our vendor records to confirm before making any payment. Please do not send new bank details by email.",
    "QTY_EXCEEDS_RECEIPT": "The quantity billed is more than the quantity we have received. Please send a corrected invoice for the received quantity, or share proof of delivery for the balance.",
    "PRICE_VARIANCE": "Some unit prices are higher than the prices on our purchase order. Please send a corrected invoice at the PO prices, or the approved price revision.",
    "PRICE_OVER_LIMIT": "Some unit prices are significantly higher than our purchase order. We can't process this invoice; please send a corrected invoice at the PO prices.",
    "LINE_MISMATCH": "The line items don't match our purchase order line by line. Please check the items and prices and send a corrected invoice.",
    "LINE_NOT_ON_PO": "Some items on the invoice are not on our purchase order. Please confirm which PO they belong to.",
    "VENDOR_MATH_ERROR": "The amounts on the invoice don't add up. Please check the subtotal, tax and total and send a corrected invoice.",
    "MISSING_FIELDS": "Some required details are missing from the invoice. Please send a complete tax invoice.",
    "DUPLICATE_EXACT": "We have already received this invoice. If this is a reminder, no action is needed; if it is a new bill, please issue it with a new invoice number.",
    "DUPLICATE_SUSPECTED": "This invoice looks very similar to one we already received. Please confirm whether it is a separate bill.",
    "PO_INFERRED": "The invoice doesn't mention our purchase order number. Please confirm the PO number for this invoice.",
    "NO_PO": "We couldn't find a purchase order for this invoice. Please share the PO number it relates to.",
    "PROFORMA": "This is a proforma invoice. Please send the final tax invoice so we can process payment.",
    "NOT_AN_INVOICE": "The document we received is not an invoice. Please send the tax invoice.",
    "PO_OVERBILLED": "Together with earlier invoices, this invoice exceeds the value of our purchase order. Please check the amounts billed against this PO.",
    "TAX_ID_MISMATCH": "The GSTIN on the invoice doesn't match our records. Please confirm your GSTIN.",
    "DATE_INVALID": "There is a problem with the dates on the invoice. Please check the invoice and due dates.",
    "CURRENCY_MISMATCH": "The invoice currency is different from our purchase order. Please reissue in the PO currency.",
    "QTY_OVER_PO": "The quantity billed is more than what remains on our purchase order. Please check.",
    "NO_RECEIPT": "We have not yet recorded receipt of these goods. Please share the delivery details.",
}


def ledger(conn, invoice_id):
    inv = row(conn, "SELECT * FROM invoices WHERE id=?", (invoice_id,))
    f = rows(conn, "SELECT check_id, result, reason_code, message FROM findings WHERE invoice_id=? AND result IN ('WARN','FAIL')", (invoice_id,))
    return {
        "invoice": {"invoice_number": inv["invoice_number"], "vendor_name": inv["vendor_name"], "invoice_date": inv["invoice_date"],
                    "subtotal": inr(inv["subtotal"]), "tax": inr(inv["tax"]), "total": inr(inv["total"]),
                    "po_number": inv["po_number"], "po_match": inv["po_match_type"]},
        "decision": LABEL[inv["status"]], "one_line_reason": inv["primary_reason"], "issues": f,
    }


def template_text(led):
    i = led["invoice"]
    if not led["issues"]:
        return (f"Invoice {i['invoice_number']} from {i['vendor_name']} for {i['total']} passed every check"
                + (f" and matches {i['po_number']}" if i["po_number"] else "") + ". It is ready to pay.")
    bullets = " ".join(f"({n + 1}) {x['message']}" for n, x in enumerate(led["issues"][:4]))
    return f"Invoice {i['invoice_number']} from {i['vendor_name']} for {i['total']}: {led['decision']}. {bullets}"


_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbers_ok(text: str, led: dict) -> bool:
    """Every number written by the AI must exist somewhere in the ledger (ignores 1-2 digit list counters)."""
    hay = json.dumps(led, default=str, ensure_ascii=False)
    hay_n = set(n.replace(",", "") for n in _NUM.findall(hay))
    hay_n |= {str(int(float(x))) for x in hay_n if re.fullmatch(r"\d+(\.\d+)?", x)}
    for n in _NUM.findall(text or ""):
        v = n.replace(",", "").rstrip(".")
        if len(v.replace(".", "")) <= 2:
            continue
        if v not in hay_n and v.split(".")[0] not in hay_n:
            return False
    return True


def build(conn, invoice_id, file_hash, use_ai: bool):
    """Returns (summary, None, source) where source is 'ai' or 'template'. (No vendor email here any more.)"""
    from core import llm
    led = ledger(conn, invoice_id)
    expl = template_text(led)
    if not use_ai or not llm.available():
        return expl, None, "template"
    try:
        out, _ = llm.write_text(conn, file_hash, led)
    except Exception:
        return expl, None, "template"
    if not numbers_ok(out["explanation"], led):
        return expl, None, "template (AI text rejected: a number didn't match the ledger)"
    return out["explanation"], None, "ai"


# ------------------------------------------------------------------ vendor email after a human decision (template only)

SIGN = "Kind regards,\nAccounts Payable, Acme Retail India Pvt Ltd"


def reviewer_email(conn, invoice_id, action: str, reason: str):
    """A short, ready-to-copy email for the reviewer's decision. Plain template - no AI, nothing is sent.
    Always addressed to the email ON FILE, never one taken from the invoice."""
    inv = row(conn, "SELECT * FROM invoices WHERE id=?", (invoice_id,))
    v = row(conn, "SELECT name, email FROM vendors WHERE vendor_id=?", (inv["vendor_id"],)) if inv["vendor_id"] else None
    name = (v or {}).get("name") or inv["vendor_name"] or "Vendor"
    to = (v or {}).get("email") or "(no email on file - find the vendor's contact in the vendor master)"
    ref = f"invoice {inv['invoice_number']} dated {inv['invoice_date']} for {inr(inv['total'])}"
    po = f" ({inv['po_number']})" if inv["po_number"] and inv["po_match_type"] == "EXPLICIT" else ""
    codes = json.loads(inv["reason_codes"] or "[]")
    if action == "approve":
        subject = f"Invoice {inv['invoice_number']} approved for payment"
        lines = [f"Dear {name} team,", f"Your {ref}{po} has been approved for payment as per our agreed terms."]
        if "BANK_CHANGED" in codes:
            lines.append("Payment will go to the bank account we confirmed with you by phone.")
    else:
        subject = f"Invoice {inv['invoice_number']} - not processed"
        lines = [f"Dear {name} team,", f"We are unable to process your {ref}{po}.", f"Reason: {reason.rstrip('.')}."]
        asks = [ASK[c] for c in codes if c in VENDOR_FACING and c in ASK]
        if asks:
            lines.append("To help us resolve it:\n" + "\n".join(f"- {a}" for a in dict.fromkeys(asks)))
        lines.append("Please reply to this email or send a corrected invoice.")
    return {"to": to, "subject": subject, "body": "\n\n".join(lines + [SIGN])}
