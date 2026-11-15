"""Turns findings into a status, and is the ONLY code that changes an invoice's status or PO money.

Status = the most severe finding:   any FAIL -> REJECTED,  else any WARN -> FLAGGED,  else APPROVED.
PO money state (one row per invoice+PO, so re-processing can never count twice):
    APPROVED -> COMMITTED     FLAGGED -> RESERVED     REJECTED -> RELEASED
"""
import json
import time

from core.db import audit, row, tx
from core.rules import PRIORITY, REASON_LABEL, norm_invoice_number

SEVERITY = {"PASS": 0, "NA": 0, "WARN": 1, "FAIL": 2}
STATUS_FOR = {0: "APPROVED", 1: "FLAGGED", 2: "REJECTED"}
ALLOC_FOR = {"APPROVED": "COMMITTED", "FLAGGED": "RESERVED", "REJECTED": "RELEASED"}
LABEL = {"APPROVED": "Ready to Pay", "FLAGGED": "Needs Attention", "REJECTED": "Rejected"}


def _order(f):
    return (-SEVERITY[f.result], PRIORITY.index(f.reason_code) if f.reason_code in PRIORITY else 999)


def decide(findings):
    bad = sorted([f for f in findings if f.result in ("WARN", "FAIL")], key=_order)
    status = STATUS_FOR[max((SEVERITY[f.result] for f in findings), default=0)]
    codes = []
    for f in bad:
        if f.reason_code and f.reason_code not in codes:
            codes.append(f.reason_code)
    if bad:
        first = bad[0].message.split(". ")[0].rstrip(".") + "."
        primary = first
    else:
        primary = "All checks passed."
    return status, codes, primary


def persist(conn, invoice_id: int, inv, result, policy_version: int, actor="system"):
    """Write findings, lines, matches, status and PO money for one invoice. Call INSIDE a tx()."""
    status, codes, primary = decide(result.findings)
    conn.execute("DELETE FROM findings WHERE invoice_id=?", (invoice_id,))
    conn.executemany(
        """INSERT INTO findings (invoice_id, check_id, check_group, result, reason_code, message, expected, actual, details, policy_version)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        [(invoice_id, f.check_id, f.group, f.result, f.reason_code, f.message, f.expected, f.actual,
          json.dumps({"label": f.label, **f.details}, default=str), policy_version) for f in result.findings])
    conn.execute("DELETE FROM invoice_lines WHERE invoice_id=?", (invoice_id,))
    conn.executemany("INSERT INTO invoice_lines VALUES (?,?,?,?,?,?,?)",
                     [(invoice_id, i, l.description, l.quantity, l.unit_price, l.amount, result.line_map.get(i))
                      for i, l in enumerate(inv.lines)])
    conn.execute(
        """UPDATE invoices SET document_type=?, vendor_name=?, vendor_gstin=?, invoice_number=?, invoice_number_norm=?,
             invoice_date=?, due_date=?, po_reference=?, currency=?, subtotal=?, tax=?, total=?, bank_account=?, ifsc=?,
             vendor_id=?, po_number=?, po_match_type=?, status=?, decided_by='system', primary_reason=?, reason_codes=?,
             policy_version=?, decided_at=? WHERE id=?""",
        (inv.document_type, inv.vendor_name, inv.vendor_gstin, inv.invoice_number, norm_invoice_number(inv.invoice_number),
         inv.invoice_date, inv.due_date, inv.po_reference, inv.currency, inv.subtotal, inv.tax, inv.total, inv.bank_account,
         inv.ifsc, result.vendor_id, result.po_number, result.po_match_type, status, primary, json.dumps(codes),
         policy_version, time.time(), invoice_id))
    _set_allocation(conn, invoice_id, result.po_number, result.allocation_amount, ALLOC_FOR[status])
    audit(conn, actor, "DECIDED", invoice_id, status=status, label=LABEL[status], reasons=codes, policy_version=policy_version,
          po=result.po_number, po_match=result.po_match_type)
    return status, codes, primary


def _set_allocation(conn, invoice_id, po_number, amount, state):
    # an invoice re-matched to a different PO releases the old one
    conn.execute("UPDATE po_allocations SET state='RELEASED', updated_at=? WHERE invoice_id=? AND po_number IS NOT ?",
                 (time.time(), invoice_id, po_number))
    if po_number and amount is not None:
        prev = row(conn, "SELECT state FROM po_allocations WHERE invoice_id=? AND po_number=?", (invoice_id, po_number))
        conn.execute("""INSERT INTO po_allocations (invoice_id, po_number, amount, state, updated_at) VALUES (?,?,?,?,?)
                        ON CONFLICT(invoice_id, po_number) DO UPDATE SET amount=excluded.amount, state=excluded.state, updated_at=excluded.updated_at""",
                     (invoice_id, po_number, amount, state, time.time()))
        if not prev or prev["state"] != state:
            audit(conn, "system", "PO_" + state, invoice_id, po=po_number, amount=amount, previous=prev["state"] if prev else None)


# ------------------------------------------------------------------ human decisions

REVIEW_REASONS = {
    "approve": ["Confirmed with vendor (phone number on file)", "Confirmed with budget owner", "Within recurring contract",
                "Confirmed suggested PO is correct", "Quantity confirmed with warehouse"],
    "reject": ["Duplicate of an invoice already paid", "Vendor could not confirm bank change", "Price not agreed",
               "Goods not received", "Not our order", "Ask vendor for a corrected invoice"],
}


def allowed_actions(inv_row) -> set:
    """Who can do what. A system 'Rejected' can never be approved by a click."""
    if not inv_row or inv_row["run_state"] != "DONE":
        return set()
    s = inv_row["status"]
    if s == "FLAGGED":
        return {"approve", "reject"}
    if s == "APPROVED":
        return {"reject"}  # pull back before payment
    return set()


def reviewer_action(conn, invoice_id: int, action: str, reason: str, actor: str = "Demo Reviewer"):
    reason = (reason or "").strip()
    if action not in ("approve", "reject"):
        raise ValueError("Unknown action.")
    if len(reason) < 5:
        raise ValueError("A reason is required (at least a few words).")
    with tx(conn):
        inv = row(conn, "SELECT * FROM invoices WHERE id=?", (invoice_id,))
        if action not in allowed_actions(inv):
            raise PermissionError(f"Can't {action} an invoice that is {LABEL.get(inv['status'], inv['status'])}"
                                  + (" (decided by the system)." if inv and inv["status"] == "REJECTED" else "."))
        new = "APPROVED" if action == "approve" else "REJECTED"
        conn.execute("UPDATE invoices SET status=?, decided_by='reviewer', decided_at=? WHERE id=?", (new, time.time(), invoice_id))
        audit(conn, actor, "REVIEWER_" + action.upper(), invoice_id, reason=reason, previous=inv["status"], new=new,
              open_reasons=json.loads(inv["reason_codes"] or "[]"))
        a = row(conn, "SELECT po_number, amount FROM po_allocations WHERE invoice_id=? AND state!='RELEASED'", (invoice_id,))
        if a:
            _set_allocation(conn, invoice_id, a["po_number"], a["amount"], ALLOC_FOR[new])
    return new


def reason_label(code):
    return REASON_LABEL.get(code, code)


def reviewer_note_only(conn, invoice_id: int, note: str, actor: str = "Demo Reviewer"):
    """Save a reviewer's note without changing the status (e.g. 'called the vendor, waiting for reply').
    Recorded in the append-only audit trail like every other action."""
    note = (note or "").strip()
    if len(note) < 5:
        raise ValueError("Write a short note first (at least a few words).")
    with tx(conn):
        inv = row(conn, "SELECT status, run_state FROM invoices WHERE id=?", (invoice_id,))
        if not inv or inv["run_state"] != "DONE":
            raise PermissionError("This invoice hasn't finished processing.")
        audit(conn, actor, "REVIEWER_NOTE", invoice_id, reason=note, status=inv["status"])
