"""Read-only queries for the screens. Every number on the dashboard is calculated here from the database."""
import json
from datetime import date, timedelta

from core.db import row, rows

SORTS = {"Invoice date (newest)": "invoice_date DESC, id DESC", "Invoice date (oldest)": "invoice_date ASC, id ASC",
         "Amount (high → low)": "total DESC", "Amount (low → high)": "total ASC",
         "Status (most severe first)": "CASE status WHEN 'REJECTED' THEN 0 WHEN 'FLAGGED' THEN 1 WHEN 'APPROVED' THEN 2 ELSE 3 END, invoice_date DESC",
         "Recently processed": "id DESC"}
STATUS_KEYS = {"Ready to Pay": "APPROVED", "Needs Attention": "FLAGGED", "Blocked": "REJECTED"}


def _where(f: dict):
    w, p = ["1=1"], []
    if f.get("search"):
        w.append("(invoice_number LIKE ? OR vendor_name LIKE ? OR filename LIKE ? OR po_number LIKE ?)")
        p += [f"%{f['search']}%"] * 4
    st = f.get("statuses") or []
    if st:
        parts = []
        keys = [STATUS_KEYS[s] for s in st if s in STATUS_KEYS]
        if keys:
            parts.append(f"(run_state='DONE' AND status IN ({','.join('?' * len(keys))}))")
            p += keys
        if "Processing / failed" in st:
            parts.append("run_state != 'DONE'")
        w.append("(" + " OR ".join(parts) + ")")
    if f.get("vendors"):
        w.append(f"COALESCE(vendor_name, '') IN ({','.join('?' * len(f['vendors']))})")
        p += f["vendors"]
    if f.get("date_from"):
        w.append("invoice_date >= ?")
        p.append(str(f["date_from"]))
    if f.get("date_to"):
        w.append("invoice_date <= ?")
        p.append(str(f["date_to"]))
    if f.get("source") == "uploads":
        w.append("source='upload'")
    return " AND ".join(w), p


def date_range(choice, today=None, custom=None):
    today = today or date.today()
    days = {"Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90}.get(choice)
    if days:
        return today - timedelta(days=days), today
    if choice == "Custom range" and custom and len(custom) == 2:
        return custom
    return None, None


def summary(conn, f):
    w, p = _where(f)
    out = {s: {"count": 0, "amount": 0.0} for s in ("APPROVED", "FLAGGED", "REJECTED")}
    for r in rows(conn, f"SELECT status, COUNT(*) n, COALESCE(SUM(total),0) amt FROM invoices WHERE {w} AND run_state='DONE' GROUP BY status", p):
        if r["status"] in out:
            out[r["status"]] = {"count": r["n"], "amount": r["amt"]}
    out["ALL"] = row(conn, f"SELECT COUNT(*) n FROM invoices WHERE {w}", p)["n"]
    out["AUTO"] = row(conn, f"SELECT COUNT(*) n FROM invoices WHERE {w} AND status='APPROVED' AND decided_by='system'", p)["n"]
    return out


def list_invoices(conn, f, sort="Invoice date (newest)", page=1, page_size=10):
    w, p = _where(f)
    total = row(conn, f"SELECT COUNT(*) n FROM invoices WHERE {w}", p)["n"]
    data = rows(conn, f"""SELECT id, invoice_number, vendor_name, total, status, decided_by, primary_reason, invoice_date,
                                 run_state, error_message, source, filename, po_number, uploaded_at
                          FROM invoices WHERE {w} ORDER BY {SORTS[sort]} LIMIT ? OFFSET ?""", p + [page_size, (page - 1) * page_size])
    return data, total


def ordered_ids(conn, f, sort):
    w, p = _where(f)
    return [r["id"] for r in rows(conn, f"SELECT id FROM invoices WHERE {w} ORDER BY {SORTS[sort]}", p)]


def vendor_names(conn):
    return [r["v"] for r in rows(conn, "SELECT DISTINCT vendor_name v FROM invoices WHERE vendor_name IS NOT NULL ORDER BY 1")]


def invoice(conn, iid):
    return row(conn, "SELECT * FROM invoices WHERE id=?", (iid,))


def stages(conn, iid):
    return rows(conn, "SELECT * FROM run_stages WHERE invoice_id=? ORDER BY stage_no", (iid,))


def findings(conn, iid):
    out = rows(conn, "SELECT * FROM findings WHERE invoice_id=? ORDER BY id", (iid,))
    for f in out:
        f["details"] = json.loads(f["details"] or "{}")
    return out


def evidence(conn, iid):
    return rows(conn, "SELECT * FROM field_evidence WHERE invoice_id=?", (iid,))


def lines(conn, iid):
    return rows(conn, "SELECT * FROM invoice_lines WHERE invoice_id=? ORDER BY line_no", (iid,))


def audit(conn, iid):
    out = rows(conn, "SELECT * FROM audit_log WHERE invoice_id=? ORDER BY id", (iid,))
    for a in out:
        a["details"] = json.loads(a["details"] or "{}")
    return out


def vendor(conn, vid):
    return row(conn, "SELECT * FROM vendors WHERE vendor_id=?", (vid,)) if vid else None


def po_detail(conn, po_number):
    if not po_number:
        return None
    po = row(conn, "SELECT * FROM purchase_orders WHERE po_number=?", (po_number,))
    if not po:
        return None
    po["lines"] = rows(conn, """SELECT l.*, COALESCE((SELECT SUM(quantity_received) FROM goods_receipts g
                                 WHERE g.po_number=l.po_number AND g.line_no=l.line_no),0) AS received
                                 FROM po_lines l WHERE po_number=? ORDER BY line_no""", (po_number,))
    po["receipts"] = rows(conn, "SELECT * FROM goods_receipts WHERE po_number=? ORDER BY received_date", (po_number,))
    m = {r["state"]: r["s"] for r in rows(conn, "SELECT state, SUM(amount) s FROM po_allocations WHERE po_number=? GROUP BY state", (po_number,))}
    po["committed"], po["reserved"] = m.get("COMMITTED", 0.0), m.get("RESERVED", 0.0)
    po["remaining"] = po["total_amount"] - po["committed"] - po["reserved"]
    po["invoices"] = rows(conn, """SELECT i.id, i.invoice_number, i.invoice_date, a.amount, a.state, i.status
                                    FROM po_allocations a JOIN invoices i ON i.id=a.invoice_id WHERE a.po_number=? ORDER BY i.id""", (po_number,))
    return po


def chat(conn, iid):
    return rows(conn, "SELECT role, content FROM chat_messages WHERE invoice_id=? ORDER BY id", (iid,))


def reviewer_note(conn, iid):
    """Latest human decision on this invoice (who, what, why), or None."""
    a = row(conn, "SELECT actor, action, details, ts FROM audit_log WHERE invoice_id=? AND action LIKE 'REVIEWER_%' ORDER BY id DESC LIMIT 1", (iid,))
    if a:
        a["details"] = json.loads(a["details"] or "{}")
    return a


def reviewer_notes(conn, iid, limit=3):
    """Latest notes a reviewer saved without changing the status."""
    out = rows(conn, "SELECT actor, ts, details FROM audit_log WHERE invoice_id=? AND action='REVIEWER_NOTE' ORDER BY id DESC LIMIT ?", (iid, limit))
    for a in out:
        a["details"] = json.loads(a["details"] or "{}")
    return out
