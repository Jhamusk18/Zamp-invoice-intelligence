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
    "decided": "Why?",
    "next": "What should I do?",
    "whats_on": "Invoice details",
    "compare": "Compare with order",
    "source": "Was it read correctly?",
    "start": "Start over",
}
DECIDED_LABEL = {"APPROVED": "Why is it OK?", "FLAGGED": "Why is it held?", "REJECTED": "Why is it blocked?"}
OUT_OF_SCOPE = "Sorry, I can only help with this invoice 🙂 Pick one of the options below."

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
    state = {"APPROVED": "It's **ready to pay** ✅", "FLAGGED": "It **needs your attention** ⚠️", "REJECTED": "It's **blocked** ⛔"}[inv["status"]]
    return (f"Hi! 👋 I've checked invoice **{inv['invoice_number'] or inv['filename']}** from {inv['vendor_name'] or 'an unknown vendor'}. "
            f"{state}\n\nLet me know what you'd like to know.")


def ensure_started(conn, iid):
    if not q.chat(conn, iid):
        _save(conn, iid, "assistant", greeting(q.invoice(conn, iid)))


def ask(conn, iid, key=None, text=None):
    """Record the question and the answer. Returns the answer (markdown)."""
    if text is not None:
        _save(conn, iid, "user", text)
        if re.search(FORBIDDEN, text.lower()):
            ans = "I can't approve or change anything. You do that with the buttons on the Review page."
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


# ------------------------------------------------------------------ plain-language sentences (shared with the Review page)

TITLES = {"DOC_TYPE": "Document type", "REQUIRED_FIELDS": "Required details", "EVIDENCE": "Values found in the PDF", "HIDDEN_TEXT": "Hidden text",
          "READS_AGREE": "Second read", "ARITHMETIC": "Amounts add up", "VENDOR": "Vendor", "TAX_ID": "GSTIN", "BANK": "Bank account",
          "DUPLICATE": "Duplicate", "PO_MATCH": "Purchase order", "PO_LINES": "Items vs order", "PO_BALANCE": "Order budget",
          "RECEIPT": "Goods received", "DATES": "Dates", "CURRENCY": "Currency", "AUTO_LIMIT": "Approval limit"}


def plain_title(f):
    return TITLES.get(f["check_id"], f["details"].get("label", f["check_id"]))


def _first(msg):
    t = msg.split(". ")[0].rstrip(".")
    return re.sub(r"\s*\((score|similarity|allowed|PO value|approved|paid)[^)]*\)", "", t) + "."


def short_text(f):
    """One plain sentence a non-technical reviewer can act on."""
    code, d = f["reason_code"], f["details"]
    if code == "BANK_CHANGED":
        return f"The invoice asks us to pay {f['actual']}, but our records have {f['expected']}. Call the vendor before paying."
    if code == "HIDDEN_TEXT":
        return "The PDF hides text that tries to get it approved. It was ignored, but treat this invoice as suspicious."
    if code == "PO_INFERRED":
        best = (d.get("candidates") or [{}])[0].get("po_number", "a likely order")
        return f"No PO number on the invoice. Best guess: {best} - please confirm."
    if code == "NO_PO":
        return "No PO number on the invoice, and no matching order was found."
    if code in ("LINE_NOT_ON_PO", "PRICE_VARIANCE", "LINE_MISMATCH", "PRICE_OVER_LIMIT", "QTY_OVER_PO"):
        bad = [x for x in d.get("lines", []) if x.get("result") != "PASS"]
        if bad:
            x = bad[0]
            note = x["note"].split(" (")[0].replace("vs PO", "vs the order").replace("not on the PO", "isn't on the order").replace("on the PO", "on the order")
            more = f" (+{len(bad) - 1} more)" if len(bad) > 1 else ""
            return f"{x['invoice_line']}: {note}{more}."
    if code == "QTY_EXCEEDS_RECEIPT":
        rows = [r for r in d.get("rows", []) if r["invoiced"] > r["received"] - r.get("billed_before", 0)]
        if rows:
            r = rows[0]
            return f"Billed {r['invoiced']:g}, but only {max(r['received'] - r.get('billed_before', 0), 0):g} received and not yet billed."
    if code == "DUPLICATE_EXACT":
        return f"We already have this invoice ({f['actual']} is the same as an earlier one). Don't pay it twice."
    if code == "OVER_AUTO_LIMIT":
        return f"{f['actual']} is above the {f['expected'].replace('≤ ', '')} limit, so a person must approve it."
    if code == "UNVERIFIED_FIELD":
        return "Some values couldn't be found in the PDF. Compare them with the document yourself."
    if code == "VENDOR_MATH_ERROR":
        return "The invoice's own numbers don't add up - ask the vendor for a corrected invoice."
    if code == "VENDOR_LOOKALIKE":
        return "The name looks like one of our vendors, but it's a different company. Possible impersonation."
    if code == "UNKNOWN_VENDOR":
        return "This vendor isn't on our approved list."
    if code == "VENDOR_BLOCKED":
        return "This vendor is blocked in our records - don't pay."
    if code == "NOT_AN_INVOICE":
        return "This is not an invoice (for example a quotation), so there's nothing to pay."
    return _first(f["message"])



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
    "VENDOR_NAME_MISMATCH": "The GSTIN matches but the name doesn't - confirm with the vendor (contact details on file) that this is their invoice.",
    "MISSING_FIELDS": "Ask the vendor for a complete tax invoice (number, date, total and GSTIN).",
    "LINE_NOT_ON_PO": "Ask the requester or vendor which PO the extra items belong to.",
    "QTY_OVER_PO": "The quantity is more than what's left on the PO - ask procurement whether the PO was increased.",
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


# ------------------------------------------------------------------ answers: short, simple English, end with "Anything else?"
MORE = "\nAnything else?"
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _date(d):
    return f"{int(d[8:10])} {MON[int(d[5:7]) - 1]} {d[:4]}" if d and len(d) == 10 else "not shown"


def _whats_on(conn, iid):
    i = q.invoice(conn, iid)
    ls = q.lines(conn, iid)
    items = "; ".join(f"{l['quantity']:g} × {l['description']}" for l in ls[:2]) + (f" (+{len(ls) - 2} more)" if len(ls) > 2 else "")
    t = [f"**{i['vendor_name']}** · invoice **{i['invoice_number']}**",
         f"• Date: {_date(i['invoice_date'])}",
         f"• Total: **{inr(i['total'], decimals=0)}** (incl. {inr(i['tax'], decimals=0)} GST)",
         f"• Items: {items}",
         f"• Order: {i['po_number'] or 'no PO number'}" + (" (our best guess)" if i["po_match_type"] == "INFERRED" else "")]
    return "\n".join(t) + MORE


def _decided(conn, iid):
    i = q.invoice(conn, iid)
    fs = q.findings(conn, iid)
    if i["decided_by"] == "reviewer":
        note = q.reviewer_note(conn, iid)
        why = f" Their note: “{note['details'].get('reason', '')}”" if note else ""
        return f"A reviewer marked it **{LABEL[i['status']]}**.{why}" + MORE
    bad = sorted([f for f in fs if f["result"] in ("WARN", "FAIL")], key=lambda f: f["result"] != "FAIL")
    passed = sum(1 for f in fs if f["result"] == "PASS")
    if not bad:
        return f"Everything matched ✅ All {passed} checks passed, so it's **Ready to Pay**." + MORE
    head = "It's **blocked** because:" if i["status"] == "REJECTED" else "It's **on hold** because:"
    lines = [f"• {short_text(f)}" for f in bad[:3]] + ([f"• …and {len(bad) - 3} more"] if len(bad) > 3 else [])
    return "\n".join([head] + lines + [f"\nThe other {passed} checks passed ✅"]) + MORE


def _next(conn, iid):
    i = q.invoice(conn, iid)
    codes = json.loads(i["reason_codes"] or "[]")
    if i["decided_by"] == "reviewer":
        return "Nothing - a reviewer has already decided this one." + MORE
    if i["status"] == "APPROVED":
        return "Nothing - it can be paid 👍" + MORE
    first = next((c for c in codes if c in NEXT_STEP), None)
    step = NEXT_STEP[first].replace("**", "") if first else "Look at the problems on this page."
    if i["status"] == "REJECTED":
        return f"Don't pay it. {step}" + MORE
    return (f"1. {step}\n2. Then choose **Ready to Pay** or **Blocked** on the Review page.\n"
            "3. Copy the email we prepare for the vendor.") + MORE


def _compare(conn, iid):
    i = q.invoice(conn, iid)
    po = q.po_detail(conn, i["po_number"])
    t = [f"Compared with order **{po['po_number']}**:"]
    for l in q.lines(conn, iid):
        pl = next((x for x in po["lines"] if x["line_no"] == l["po_line_no"]), None)
        if not pl:
            t.append(f"• {l['description']}: ⚠️ not on the order")
            continue
        flags = []
        if abs(l["unit_price"] - pl["unit_price"]) > 0.005:
            flags.append(f"price {inr(l['unit_price'], decimals=0)} vs {inr(pl['unit_price'], decimals=0)} ⚠️")
        if po["po_type"] == "GOODS":
            ok = l["quantity"] <= pl["received"]
            flags.append(f"ordered {pl['quantity']:g}, received {pl['received']:g}, billed {l['quantity']:g} {'✅' if ok else '⚠️'}")
        else:
            flags.append(f"ordered {pl['quantity']:g}, billed {l['quantity']:g} ✅")
        t.append(f"• {pl['description']}: " + "; ".join(flags))
    t.append(f"\nLeft on the order: **{inr(po['remaining'], decimals=0)}**")
    return "\n".join(t) + MORE


def _source(conn, iid):
    i = q.invoice(conn, iid)
    ev = q.evidence(conn, iid)
    bad = [e["field"].replace("_", " ") for e in ev if e["verification"] == "NONE"]
    how = "the scan" if i["is_scanned"] else "the PDF"
    if not bad:
        return f"Yes ✅ I found all {len(ev)} values in {how} again, so they were read correctly." + MORE
    return (f"Mostly. I found {len(ev) - len(bad)} of {len(ev)} values in {how}.\n"
            f"⚠️ Please check these yourself: {', '.join(bad)}.") + MORE


ANSWERS = {"whats_on": _whats_on, "decided": _decided, "next": _next, "compare": _compare, "source": _source}
