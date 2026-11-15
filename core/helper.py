"""Invoice Helper: a guided assistant for ONE invoice.

Menu answers are templates filled from stored results - no AI, no cost, always consistent.
It can explain and point to actions on the Review page. It can never approve, reject,
edit data, change rules or send email. Each invoice keeps its own conversation (chat_messages).
"""
import json
import re
import time

from core import queries as q
from core.decision import LABEL
from core.money import inr, mask_account

MENU = {  # order = order shown (most useful first)
    "decided": "Why was this held?",
    "next": "What should I do next?",
    "whats_on": "What's on this invoice?",
    "compare": "Compare with our order",
    "source": "Where did this come from?",
    "start": "Start over",
}
DECIDED_LABEL = {"APPROVED": "Why is it ready to pay?", "FLAGGED": "Why was this held?", "REJECTED": "Why was it blocked?"}
OUT_OF_SCOPE = "I can only help with this invoice's details and decision. Try one of the options below."

KEYWORDS = [  # free-typed text -> menu item (no AI involved)
    ("compare", r"\b(compare|order|po|purchase|received|receipt|grn|quantity|qty)\b"),
    ("source", r"\b(where|source|evidence|snippet|proof|ocr|come from|verified)\b"),
    ("next", r"\b(next|do now|action|should i|email|fix|resolve)\b"),
    ("decided", r"\b(decid|decision|why|status|flag|block|reason|approved|held|hold)\b"),
    ("whats_on", r"\b(what.?s on|details|line items|amount|total|tax|bank|vendor|due|date|number)\b"),
]
FORBIDDEN = r"\b(approve it|reject it|mark|change|edit|update|send|pay it|delete|override)\b"


def has_comparison(conn, iid):
    inv = q.invoice(conn, iid)
    return bool(inv and inv["po_number"])


def label(inv, key):
    return DECIDED_LABEL.get(inv["status"], MENU[key]) if key == "decided" else MENU[key]


def menu_items(conn, iid):
    inv = q.invoice(conn, iid)
    return [(k, label(inv, k)) for k in MENU if k != "start" and (k != "compare" or has_comparison(conn, iid))]


def summary_sentence(inv):
    """One sentence that says the result, used as the helper's first message."""
    r = (inv["primary_reason"] or "").rstrip(".")
    r = r[:1].lower() + r[1:] if r and not r[:2].isupper() else r
    if inv["status"] == "APPROVED":
        return (f"**Ready to Pay** - approved by a reviewer. Want to see what was checked?" if inv["decided_by"] == "reviewer"
                else "**Ready to Pay** - every check passed. Want to see what was checked?")
    head = {"FLAGGED": "Needs attention", "REJECTED": "Blocked"}[inv["status"]]
    return f"**{head}**: {r}. Want to see why?"


def next_step(conn, iid):
    """One sentence for the verdict card: the most important thing to do now."""
    inv = q.invoice(conn, iid)
    if not inv or inv["run_state"] != "DONE":
        return None
    if inv["decided_by"] == "reviewer":
        return None
    if inv["status"] == "APPROVED":
        return "Nothing - it can be paid. You can still pull it back with Reject if you learn something new."
    codes = json.loads(inv["reason_codes"] or "[]")
    first = next((c for c in codes if c in NEXT_STEP), None)
    return NEXT_STEP[first].replace("**", "") if first else "Review the checks below, then approve or reject with a reason."


def greeting(inv):
    return f"I've checked invoice **{inv['invoice_number'] or inv['filename']}** from **{inv['vendor_name'] or 'an unknown vendor'}**. " + summary_sentence(inv)


def ensure_started(conn, iid):
    if not q.chat(conn, iid):
        _save(conn, iid, "assistant", greeting(q.invoice(conn, iid)))


def ask(conn, iid, key=None, text=None):
    """Record the question and the answer. Returns the answer (markdown)."""
    if text is not None:
        _save(conn, iid, "user", text)
        if re.search(FORBIDDEN, text.lower()):
            ans = ("I can't change invoices, approve, reject or send anything. A person does that on the "
                   "**Review page** with a reason, so it's recorded in the audit trail.")
            _save(conn, iid, "assistant", ans)
            return ans
        key = next((k for k, pat in KEYWORDS if re.search(pat, text.lower())), None)
        if key == "compare" and not has_comparison(conn, iid):
            key = None
        if not key:
            _save(conn, iid, "assistant", OUT_OF_SCOPE)
            return OUT_OF_SCOPE
    else:
        _save(conn, iid, "user", label(q.invoice(conn, iid), key))
    if key == "start":
        conn.execute("DELETE FROM chat_messages WHERE invoice_id=?", (iid,))
        ensure_started(conn, iid)
        return None
    ans = ANSWERS[key](conn, iid)
    _save(conn, iid, "assistant", ans)
    return ans


def _save(conn, iid, role, content):
    conn.execute("INSERT INTO chat_messages (invoice_id, ts, role, content) VALUES (?,?,?,?)", (iid, time.time(), role, content))


# ------------------------------------------------------------------ answers

def _whats_on(conn, iid):
    i = q.invoice(conn, iid)
    ls = q.lines(conn, iid)
    t = [f"**{i['vendor_name']}**" + (f" · GSTIN {i['vendor_gstin']}" if i["vendor_gstin"] else ""),
         f"- Invoice **{i['invoice_number']}** · dated {i['invoice_date'] or '—'} · due {i['due_date'] or '—'}",
         f"- PO on invoice: {i['po_reference'] or '*none printed*'}"
         + (f" · matched to **{i['po_number']}** ({'suggested, needs confirming' if i['po_match_type'] == 'INFERRED' else 'stated on invoice'})" if i["po_number"] else ""),
         f"- Bank: {mask_account(i['bank_account'])}" + (f" · IFSC {i['ifsc']}" if i["ifsc"] else ""),
         "", "| Item | Qty | Rate | Amount |", "|---|---:|---:|---:|"]
    t += [f"| {l['description']} | {l['quantity']:g} | {inr(l['unit_price'])} | {inr(l['amount'])} |" for l in ls]
    t += ["", f"Subtotal **{inr(i['subtotal'])}** · Tax {inr(i['tax'])} · Total **{inr(i['total'])}**"]
    return "\n".join(t)


def _decided(conn, iid):
    i = q.invoice(conn, iid)
    fs = q.findings(conn, iid)
    who = "by the system" if i["decided_by"] == "system" else "by a reviewer"
    t = [f"**{LABEL[i['status']]}** - decided {who} under policy v{i['policy_version']}.", ""]
    bad = [f for f in fs if f["result"] in ("WARN", "FAIL")]
    if bad:
        t.append("**Needs attention:**")
        for f in bad:
            t.append(f"- {'⛔' if f['result'] == 'FAIL' else '⚠️'} **{f['details'].get('label', f['check_id'])}**: {f['message']}")
    passed = [f["details"].get("label", f["check_id"]) for f in fs if f["result"] == "PASS"]
    t.append(f"\n**Passed ({len(passed)}):** " + ", ".join(passed))
    return "\n".join(t)


NEXT_STEP = {
    "NOT_AN_INVOICE": "Don't pay a quotation, order or credit note. Ask the vendor for the tax invoice once the goods or services are delivered.",
    "VENDOR_INACTIVE": "Do not pay. The vendor is inactive in the vendor master - check with procurement whether it should be reactivated.",
    "PROFORMA": "Don't pay a proforma. Ask the vendor for the final tax invoice.",
    "TAX_ID_MISMATCH": "Confirm the GSTIN with the vendor using contact details on file before paying.",
    "TAX_ID_INVALID": "Ask the vendor for an invoice with a valid GSTIN.",
    "PO_CLOSED": "Ask procurement whether the closed PO should be reopened, or which PO this belongs to.",
    "PO_EXPIRED": "Ask procurement to extend the PO, or which current PO this belongs to.",
    "PO_OTHER_VENDOR": "The PO belongs to another vendor - ask the vendor for the correct PO number.",
    "CURRENCY_MISMATCH": "Ask the vendor to reissue the invoice in the PO currency.",
    "DATE_INVALID": "Check the invoice and due dates with the vendor.",
    "NO_RECEIPT": "Check with the warehouse whether the goods have arrived before paying.",
    "TAX_RATE_UNUSUAL": "Check the GST rate with the vendor or your tax team.",
    "BANK_CHANGED": "Call the vendor on the phone number **in our vendor records** (not one from the invoice) to confirm the new bank account. Until then, don't pay.",
    "HIDDEN_TEXT": "Open the PDF and check the hidden text. Treat the invoice as suspicious; it was not used in the decision.",
    "DUPLICATE_EXACT": "Nothing to pay - this invoice was already received. Let the vendor know if they expected payment.",
    "DUPLICATE_SUSPECTED": "Compare it with the earlier invoice and confirm with the vendor whether it's a separate bill.",
    "PO_INFERRED": "Check the suggested PO under **Details & Matches** and confirm it on the Review page, or ask the vendor for the PO number.",
    "NO_PO": "Ask the vendor or the requester which PO this belongs to.",
    "QTY_EXCEEDS_RECEIPT": "Check with the warehouse whether the rest was delivered; otherwise ask the vendor for a corrected invoice.",
    "PRICE_VARIANCE": "Ask the buyer whether the higher price was agreed; if not, request a corrected invoice.",
    "PRICE_OVER_LIMIT": "Price is far above the PO: request a corrected invoice.",
    "LINE_MISMATCH": "Compare the line items with the PO and ask the vendor to correct them.",
    "PO_OVERBILLED": "Check the other invoices on this PO (Details & Matches). Ask procurement whether the PO was increased.",
    "VENDOR_MATH_ERROR": "Ask the vendor for a corrected invoice - their arithmetic doesn't add up.",
    "OVER_AUTO_LIMIT": "Everything else may be fine, but an authorised approver must approve amounts above the limit.",
    "UNVERIFIED_FIELD": "Compare the highlighted values with the PDF yourself before deciding.",
    "READS_DISAGREE": "The two reads disagree - check the values against the PDF yourself.",
    "VENDOR_BLOCKED": "Do not pay. The vendor is blocked in the vendor master.",
    "UNKNOWN_VENDOR": "Do not pay. Route the vendor to onboarding first.",
    "VENDOR_LOOKALIKE": "Possible impersonation: confirm the sender's identity with the real vendor using contact details on file.",
}


def _next(conn, iid):
    i = q.invoice(conn, iid)
    codes = json.loads(i["reason_codes"] or "[]")
    if i["status"] == "APPROVED":
        t = ["Nothing to do - it's **Ready to Pay**" + (" (approved by a reviewer)." if i["decided_by"] == "reviewer" else ".")]
    elif i["status"] == "REJECTED" and i["decided_by"] == "reviewer":
        t = ["A reviewer rejected this invoice. See the reason in the **Audit Trail**."]
    else:
        t = ["**Recommended steps:**"] + [f"{n + 1}. {NEXT_STEP[c]}" for n, c in enumerate([c for c in codes if c in NEXT_STEP])]
        if i["status"] == "FLAGGED":
            t.append("\nWhen you're done, **Approve** or **Reject** it on the Review page, with a reason.")
    if i["status"] == "FLAGGED" or (i["status"] == "APPROVED" and i["decided_by"] == "system"):
        t.append("\nWhen you pick a decision and a reason on the Review page, a ready-to-copy email to the vendor appears there. Nothing is sent automatically.")
    return "\n".join(t)


def _compare(conn, iid):
    i = q.invoice(conn, iid)
    po = q.po_detail(conn, i["po_number"])
    ls = q.lines(conn, iid)
    t = [f"Compared with **{po['po_number']}** ({po['po_type'].lower()}):", "",
         "| Item | Ordered | Received | Invoiced | PO rate | Invoice rate |", "|---|---:|---:|---:|---:|---:|"]
    for l in ls:
        pl = next((x for x in po["lines"] if x["line_no"] == l["po_line_no"]), None)
        if not pl:
            t.append(f"| {l['description']} *(not on PO)* | — | — | {l['quantity']:g} | — | {inr(l['unit_price'])} |")
            continue
        rec = pl["received"] if po["po_type"] == "GOODS" else None
        qflag = " ⚠️" if rec is not None and l["quantity"] > rec else ""
        pflag = " ⚠️" if abs(l["unit_price"] - pl["unit_price"]) > 0.005 else ""
        t.append(f"| {pl['description']} | {pl['quantity']:g} | {'n/a (service)' if rec is None else f'{rec:g}'} | **{l['quantity']:g}**{qflag} | {inr(pl['unit_price'])} | **{inr(l['unit_price'])}**{pflag} |")
    t += ["", f"PO value {inr(po['total_amount'])} · paid/approved {inr(po['committed'])} · on hold {inr(po['reserved'])} · **left {inr(po['remaining'])}**"]
    return "\n".join(t)


def _source(conn, iid):
    i = q.invoice(conn, iid)
    ev = q.evidence(conn, iid)
    how = {"TEXT": "✅ found in the PDF text", "OCR": "✅ found in the OCR text", "NONE": "⚠️ **not verified**"}
    t = [("Scanned invoice: values were checked against OCR text (an independent read of the image)." if i["is_scanned"]
          else "Values were checked against the PDF's text layer."), "",
         "| Field | Value | Quote from the document | Check |", "|---|---|---|---|"]
    for e in ev:
        val = mask_account(e["value"]) if e["field"] == "bank_account" else e["value"]
        snip = (e["snippet"] or "—").replace("|", "/")
        if e["field"] == "bank_account" and e["snippet"]:
            snip = snip.replace(e["value"], mask_account(e["value"]))
        t.append(f"| {e['field'].replace('_', ' ')} | {val} | {snip[:70]} | {how[e['verification']]} |")
    return "\n".join(t)


ANSWERS = {"whats_on": _whats_on, "decided": _decided, "next": _next, "compare": _compare, "source": _source}
