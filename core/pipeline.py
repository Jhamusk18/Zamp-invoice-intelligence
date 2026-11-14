"""The invoice run: 5 visible stages, written to run_stages so the screen can poll them live.

  1 PDF Received      real-PDF check, fingerprint, store original           (before the background thread)
  2 Text Extracted    text layer or OCR; AI reads fields + snippets (read 1)
  3 Fields Validated  snippets checked against the document; arithmetic; hidden text; re-read ONCE if needed
  4 Policy Checks     every business check, decision and PO money - one database transaction
  5 Decision & Audit  plain-English explanation + vendor email draft; audit entry

Two kinds of failure (locked decision):
  * TechnicalError (bad file, unreadable scan, AI service down)  -> stage FAILED, run_state ERROR, no money touched.
  * Business findings (bank differs, duplicate, ...)              -> never stop the run; all checks always run.
"""
import json
import threading
import time
import traceback
from datetime import date
from pathlib import Path

from core import db, decision, explain, llm, policy, rules
from core.document import (TechnicalError, check_upload, fingerprint, read_document, verify_evidence)
from core.models import CRITICAL_FIELDS, EVIDENCE_FIELDS, InvoiceExtraction

STAGES = ["PDF Received", "Text Extracted", "Fields Validated", "Policy Checks", "Decision & Audit"]
FILES_DIR = db.ROOT / "data" / "files"
COMPARE_FIELDS = ["invoice_number", "invoice_date", "po_reference", "subtotal", "tax", "total", "bank_account", "vendor_gstin"]


# ------------------------------------------------------------------ stage bookkeeping

def _stage(conn, iid, n, status, finding=None):
    now = time.time()
    if status in ("RUNNING",):
        conn.execute("UPDATE run_stages SET status=?, started_at=COALESCE(started_at, ?), finding=COALESCE(?, finding) WHERE invoice_id=? AND stage_no=?",
                     (status, now, finding, iid, n))
    elif status == "RETRYING":
        conn.execute("UPDATE run_stages SET status=?, finding=? WHERE invoice_id=? AND stage_no=?", (status, finding, iid, n))
    else:  # DONE / FAILED
        conn.execute("UPDATE run_stages SET status=?, ended_at=?, started_at=COALESCE(started_at, ?), finding=COALESCE(?, finding) WHERE invoice_id=? AND stage_no=?",
                     (status, now, now, finding, iid, n))


def _reset_stages(conn, iid):
    conn.execute("DELETE FROM run_stages WHERE invoice_id=?", (iid,))
    conn.executemany("INSERT INTO run_stages (invoice_id, stage_no, stage, status) VALUES (?,?,?, 'PENDING')",
                     [(iid, i + 1, s) for i, s in enumerate(STAGES)])


# ------------------------------------------------------------------ entry points

def submit(conn, data: bytes, filename: str, source: str = "upload", background: bool = True, **run_kwargs):
    """Returns (invoice_id, already_seen). Raises TechnicalError for a bad file (nothing is stored)."""
    t0 = time.time()
    check_upload(data, filename)
    h = fingerprint(data)
    old = db.row(conn, "SELECT id FROM invoices WHERE file_hash=?", (h,))
    if old:
        db.audit(conn, "Demo Reviewer" if source == "upload" else "system", "SAME_FILE_UPLOADED_AGAIN", old["id"], filename=filename)
        return old["id"], True
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    path = FILES_DIR / f"{h}.pdf"
    path.write_bytes(data)
    with db.tx(conn):
        cur = conn.execute("INSERT INTO invoices (file_hash, filename, file_path, source, uploaded_at, run_state) VALUES (?,?,?,?,?, 'QUEUED')",
                           (h, filename, str(path.relative_to(db.ROOT)), source, time.time()))
        iid = cur.lastrowid
        _reset_stages(conn, iid)
        conn.execute("UPDATE run_stages SET started_at=? WHERE invoice_id=? AND stage_no=1", (t0, iid))
        _stage(conn, iid, 1, "DONE", f"{len(data) / 1024:.0f} KB PDF · fingerprint {h[:10]}…")
        db.audit(conn, "Demo Reviewer" if source == "upload" else "system", "UPLOADED", iid, filename=filename, sha256=h, size=len(data))
    if background:
        threading.Thread(target=run, args=(iid,), kwargs=run_kwargs, daemon=True).start()
    else:
        run(iid, conn=conn, **run_kwargs)
    return iid, False


def retry(conn, iid, background=True, **run_kwargs):
    """Re-run an invoice that ended in ERROR (e.g. AI service was down)."""
    inv = db.row(conn, "SELECT run_state FROM invoices WHERE id=?", (iid,))
    if not inv or inv["run_state"] != "ERROR":
        raise ValueError("Only failed runs can be retried.")
    with db.tx(conn):
        _reset_stages(conn, iid)
        _stage(conn, iid, 1, "DONE", "Original file reused")
        conn.execute("UPDATE invoices SET run_state='QUEUED', error_message=NULL WHERE id=?", (iid,))
        db.audit(conn, "Demo Reviewer", "RETRY_REQUESTED", iid)
    if background:
        threading.Thread(target=run, args=(iid,), kwargs=run_kwargs, daemon=True).start()
    else:
        run(iid, conn=conn, **run_kwargs)


# ------------------------------------------------------------------ the run

def run(iid: int, conn=None, extractor=None, use_ai_text: bool = True, use_cache: bool = True, today: date | None = None):
    """extractor(conn, file_hash, facts, which) -> (InvoiceExtraction, meta). Default: the AI model (core.llm).
    Tests and the seed history pass a ground-truth extractor instead."""
    own = conn is None
    conn = conn or db.connect()
    stage_no = 2
    try:
        inv_row = db.row(conn, "SELECT * FROM invoices WHERE id=?", (iid,))
        conn.execute("UPDATE invoices SET run_state='RUNNING' WHERE id=?", (iid,))
        data = (db.ROOT / inv_row["file_path"]).read_bytes()
        h = inv_row["file_hash"]
        extractor = extractor or _ai_extractor(use_cache)
        meta = {"reads": []}

        # ---- 2. Text Extracted
        _stage(conn, iid, 2, "RUNNING", "Reading the document…")
        facts = read_document(data)
        conn.execute("UPDATE invoices SET is_scanned=? WHERE id=?", (int(facts.is_scanned), iid))
        _stage(conn, iid, 2, "RUNNING", ("Scanned image → OCR" if facts.is_scanned else "Text layer found") + " · AI reading fields…")
        inv1, m1 = extractor(conn, h, facts, "primary")
        meta["reads"].append(m1)
        if facts.text_source == "NONE":
            src = "Scanned image: OCR not available on this server, so values can't be verified"
        elif facts.is_scanned:
            src = f"Scanned image: OCR read {len(facts.text):,} characters"
        else:
            src = f"Text layer ({facts.page_count} page{'s' if facts.page_count > 1 else ''})"
        fb = f" (first model {m1['fallback_from']} was busy)" if m1.get("fallback_from") else ""
        _stage(conn, iid, 2, "DONE", f"{src} · fields read by {m1['model']}{' (cached)' if m1.get('cached') else ''}{fb}")

        # ---- 3. Fields Validated
        stage_no = 3
        _stage(conn, iid, 3, "RUNNING", "Checking every value against the document…")
        ver1 = _verify(inv1, facts)
        why_retry = _needs_retry(inv1, ver1)
        inv, ver, reads_agree, disagreements = inv1, ver1, None, []
        if why_retry:
            _stage(conn, iid, 3, "RETRYING", f"{why_retry} → second, independent read…")
            inv2, m2 = extractor(conn, h, facts, "retry")
            meta["reads"].append(m2)
            disagreements = _compare(inv1, inv2)
            reads_agree = not disagreements
            ver2 = _verify(inv2, facts)
            if reads_agree or sum(v != "NONE" for v in ver2.values()) > sum(v != "NONE" for v in ver1.values()):
                inv, ver = inv2, ver2
        meta["retry_reason"] = why_retry
        meta["reads_agree"] = reads_agree
        meta["disagreements"] = disagreements
        meta["first_read"] = inv1.model_dump() if why_retry else None
        _store_evidence(conn, iid, inv, ver)
        n_ok = sum(1 for f in EVIDENCE_FIELDS if inv.value(f) not in (None, "") and ver.get(f) != "NONE")
        n_all = sum(1 for f in EVIDENCE_FIELDS if inv.value(f) not in (None, ""))
        msg = f"{n_ok}/{n_all} values confirmed in the {'OCR text' if facts.is_scanned else 'document text'}"
        if why_retry:
            msg += f" · re-read once ({'reads agree' if reads_agree else 'reads DISAGREE'})"
        if facts.hidden_text:
            msg += f" · {len(facts.hidden_text)} hidden text item(s) found"
        _stage(conn, iid, 3, "DONE", msg)

        # ---- 4. Policy Checks (one transaction: snapshot + checks + decision + PO money)
        stage_no = 4
        _stage(conn, iid, 4, "RUNNING", "Running business checks…")
        semantic = _semantic_scores(conn, h, inv) if (llm.available() and extractor_is_ai(extractor)) else None
        with db.tx(conn):
            pv, pol = policy.active(conn)
            snap = rules.load_snapshot(conn, iid)
            result = rules.evaluate(inv, snap, pol, verification=ver,
                                    hidden_text=None if facts.is_scanned else facts.hidden_text,
                                    reads_agree=reads_agree, disagreements=disagreements,
                                    semantic_scores=semantic, today=today)
            status, codes, primary = decision.persist(conn, iid, inv, result, pv)
            conn.execute("UPDATE invoices SET extraction_meta=? WHERE id=?", (json.dumps(meta, default=str), iid))
        counts = {k: sum(1 for f in result.findings if f.result == k) for k in ("PASS", "WARN", "FAIL", "NA")}
        _stage(conn, iid, 4, "DONE", f"{counts['PASS']} passed · {counts['WARN']} need attention · {counts['FAIL']} failed · {counts['NA']} not applicable (policy v{pv})")

        # ---- 5. Decision & Audit
        stage_no = 5
        _stage(conn, iid, 5, "RUNNING", "Writing explanation…")
        expl, email, source = explain.build(conn, iid, h, use_ai=use_ai_text)
        with db.tx(conn):
            conn.execute("UPDATE invoices SET explanation=?, email_draft=?, run_state='DONE' WHERE id=?",
                         (expl, json.dumps(email) if email else None, iid))
            db.audit(conn, "system", "EXPLANATION_WRITTEN", iid, source=source, email_draft=bool(email))
        _stage(conn, iid, 5, "DONE", f"{decision.LABEL[status]} · explanation by {source} · audit logged")
    except TechnicalError as e:
        _fail(conn, iid, stage_no, str(e))
    except Exception as e:  # unexpected bug: still a technical failure, never a silent decision
        traceback.print_exc()
        _fail(conn, iid, stage_no, f"Unexpected error: {e}")
    finally:
        if own:
            conn.close()


def _fail(conn, iid, stage_no, message):
    try:
        conn.execute("ROLLBACK")
    except Exception:
        pass
    _stage(conn, iid, stage_no, "FAILED", message)
    conn.execute("UPDATE invoices SET run_state='ERROR', error_message=? WHERE id=?", (message, iid))
    db.audit(conn, "system", "RUN_FAILED", iid, stage=STAGES[stage_no - 1], error=message)


# ------------------------------------------------------------------ helpers

def _ai_extractor(use_cache):
    def ex(conn, file_hash, facts, which):
        return llm.extract(conn, file_hash, facts.text, facts.page_images_png if facts.is_scanned else [], which, use_cache)
    ex.is_ai = True
    return ex


def extractor_is_ai(ex):
    return getattr(ex, "is_ai", False)


def _verify(inv: InvoiceExtraction, facts) -> dict:
    return {f: verify_evidence(inv.value(f), inv.snippet(f), facts.text, facts.text_source)
            for f in EVIDENCE_FIELDS if inv.value(f) not in (None, "")}


def _arith_ok(inv, tol=1.0):
    amts = [l.amount for l in inv.lines]
    if amts and None not in amts and inv.subtotal is not None and abs(sum(amts) - inv.subtotal) > tol:
        return False
    if None not in (inv.subtotal, inv.tax, inv.total) and abs(inv.subtotal + inv.tax - inv.total) > tol:
        return False
    return True


def _needs_retry(inv, ver):
    if not _arith_ok(inv):
        return "Numbers didn't add up"
    bad = [f for f in CRITICAL_FIELDS if ver.get(f) == "NONE"]
    if bad and all(v == "NONE" for v in ver.values()) and ver:
        return None  # nothing can be verified at all (no OCR): a second read can't fix that, don't spend quota
    if bad:
        return "Couldn't confirm " + ", ".join(b.replace("_", " ") for b in bad) + " in the document"
    return None


def _same(a, b):
    if isinstance(a, (int, float)) or isinstance(b, (int, float)):
        return a is not None and b is not None and abs(float(a) - float(b)) <= 0.5
    na = rules.norm_invoice_number(a) if a else None
    nb = rules.norm_invoice_number(b) if b else None
    return na == nb


def _compare(a, b):
    return [{"field": f, "first": a.value(f), "second": b.value(f)} for f in COMPARE_FIELDS if not _same(a.value(f), b.value(f))]


def _store_evidence(conn, iid, inv, ver):
    with db.tx(conn):
        conn.execute("DELETE FROM field_evidence WHERE invoice_id=?", (iid,))
        conn.executemany("INSERT INTO field_evidence VALUES (?,?,?,?,?)",
                         [(iid, f, str(inv.value(f)), inv.snippet(f), ver.get(f, "NONE"))
                          for f in EVIDENCE_FIELDS if inv.value(f) not in (None, "")])


def _semantic_scores(conn, h, inv):
    """Only when there's no PO number: ask the AI how alike the item descriptions are (meaning, not spelling)."""
    if inv.po_reference or not inv.lines:
        return None
    vend = [v for v in db.rows(conn, "SELECT * FROM vendors")
            if (inv.vendor_gstin and v["gstin"] == inv.vendor_gstin) or rules.name_score(inv.vendor_name, v) >= 80]
    if not vend:
        return None
    pls = db.rows(conn, f"""SELECT l.* FROM po_lines l JOIN purchase_orders p USING (po_number)
                            WHERE p.status='OPEN' AND p.vendor_id IN ({','.join('?' * len(vend))})""", [v["vendor_id"] for v in vend])
    try:
        scores, _ = llm.judge_lines(conn, h, [l.description for l in inv.lines], pls)
        return scores
    except TechnicalError:
        return None  # optional helper: fall back to text similarity, never fail the run for it


# ------------------------------------------------------------------ ground-truth extractor (seed history + tests)

def truth_extractor(truth: InvoiceExtraction):
    """Used for the SAMPLE HISTORY and tests only - never for uploads. It returns the known values and finds each
    value's line in the document text by plain search, so evidence is still verified the normal way."""
    from core.document import _norm, _value_tokens

    def ex(conn, file_hash, facts, which):
        lines = [ln for ln in facts.text.splitlines() if ln.strip()]
        ev = []
        for f in EVIDENCE_FIELDS:
            v = truth.value(f)
            toks = _value_tokens(v)
            hit = next((ln for ln in lines if any(t in _norm(ln) for t in toks)), None)
            if not hit and facts.text_source == "OCR" and toks:  # OCR slips a character: take the closest line
                from rapidfuzz import fuzz
                best = max(lines, key=lambda ln: max(fuzz.partial_ratio(t, _norm(ln)) for t in toks))
                if max(fuzz.partial_ratio(t, _norm(best)) for t in toks) >= 90:
                    hit = best
            if hit:
                ev.append({"field": f, "snippet": hit.strip()})
        from core.models import Evidence
        out = truth.model_copy(update={"evidence": [Evidence(**e) for e in ev]})
        return InvoiceExtraction.model_validate(out.model_dump()), {"model": "ground truth (sample data)", "cached": False}
    return ex
