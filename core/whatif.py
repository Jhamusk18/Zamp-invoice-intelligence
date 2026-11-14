"""What-if: re-run every processed invoice under PROPOSED settings. Read-only - nothing is saved.

Uses the stored extraction (no AI calls, no cost) and the same rules engine. Each invoice is compared with what the
system originally decided under the policy version it was processed with.
Simplification (stated on the page): each invoice is re-checked against the invoices processed before it, using
today's PO money state for those earlier invoices.
"""
import json

from core import queries as q, rules
from core.db import rows
from core.decision import LABEL, SEVERITY, STATUS_FOR, decide
from core.models import InvoiceExtraction, Line


def rebuild(conn, inv):
    lines = [Line(description=l["description"], quantity=l["quantity"], unit_price=l["unit_price"], amount=l["amount"]) for l in q.lines(conn, inv["id"])]
    x = InvoiceExtraction(document_type=inv["document_type"] or "INVOICE", lines=lines,
                          **{k: inv[k] for k in ("vendor_name", "vendor_gstin", "invoice_number", "invoice_date", "due_date",
                                                 "po_reference", "currency", "subtotal", "tax", "total", "bank_account", "ifsc")})
    ver = {e["field"]: e["verification"] for e in q.evidence(conn, inv["id"])}
    fs = q.findings(conn, inv["id"])
    hidden = next((f["details"].get("items") for f in fs if f["check_id"] == "HIDDEN_TEXT" and f["result"] == "WARN"), [])
    if inv["is_scanned"]:
        hidden = None
    meta = json.loads(inv["extraction_meta"] or "{}")
    original = STATUS_FOR[max((SEVERITY[f["result"]] for f in fs), default=0)]
    return x, ver, hidden, meta, original


def simulate(conn, proposed: dict):
    out = []
    for inv in rows(conn, "SELECT * FROM invoices WHERE run_state='DONE' AND source IN ('seed','upload') ORDER BY id"):
        x, ver, hidden, meta, original = rebuild(conn, inv)
        snap = rules.load_snapshot(conn, inv["id"])
        res = rules.evaluate(x, snap, proposed, verification=ver or None, hidden_text=hidden,
                             reads_agree=meta.get("reads_agree"), disagreements=meta.get("disagreements"))
        new, codes, primary = decide(res.findings)
        if new != original:
            out.append({"id": inv["id"], "Invoice": inv["invoice_number"], "Vendor": inv["vendor_name"], "Amount": inv["total"],
                        "Was": LABEL[original], "Would be": LABEL[new], "Why": primary if new != "APPROVED" else "All checks would pass",
                        "direction": SEVERITY_ORDER[new] - SEVERITY_ORDER[original]})
    return out


SEVERITY_ORDER = {"APPROVED": 0, "FLAGGED": 1, "REJECTED": 2}
