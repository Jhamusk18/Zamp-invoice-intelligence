"""Reset Demo Data: rebuild the database from sample_data/.

1. Fresh database + schema
2. Company reference data from sample_data/company/*.csv
3. Default policy (v1)
4. SAMPLE HISTORY: the 'seed' invoices in sample_data/invoices.json go through the REAL pipeline and rules engine.
   The only difference from an upload: fields come from the known ground truth instead of an AI call
   (no quota spent, and history is reproducible). They are labelled source='seed' everywhere in the UI.
5. Recorded reviewer actions for the history (e.g. an over-limit invoice approved by the budget owner).
"""
import json
from datetime import date

from core import db, decision, pipeline, policy
from core.models import InvoiceExtraction, Line

SPEC = db.ROOT / "sample_data" / "invoices.json"
HISTORY_DIR = db.ROOT / "sample_data" / "history_invoices"   # pre-loaded into History at reset - never uploaded
TEST_DIR = db.ROOT / "sample_data" / "test_invoices"         # happy path + edge cases - upload these live


def pdf_path(key_or_spec):
    s = key_or_spec if isinstance(key_or_spec, dict) else next(x for x in specs() if x["key"] == key_or_spec)
    return (HISTORY_DIR if s["role"] == "seed" else TEST_DIR) / f"{s['key']}.pdf"
DEMO_TODAY = None  # use the real date


def specs():
    return json.loads(SPEC.read_text())["invoices"]


def truth_of(spec) -> InvoiceExtraction:
    t = json.loads(json.dumps(spec["truth"]))
    rate = t.pop("tax_rate")
    lines = [Line(**l, amount=round(l["quantity"] * l["unit_price"], 2)) for l in t.pop("lines")]
    sub = spec.get("subtotal_printed") or round(sum(l.amount for l in lines), 2)
    tax = round(sub * rate / 100, 2)
    return InvoiceExtraction(document_type=spec.get("document_type", "INVOICE"), lines=lines, subtotal=sub, tax=tax,
                             total=round(sub + tax, 2), **t)


def reset(path=None, verbose=False):
    path = path or db.DB_PATH
    for suffix in ("", "-wal", "-shm"):
        p = type(path)(str(path) + suffix)
        if p.exists():
            p.unlink()
    conn = db.connect(path)
    db.init_schema(conn)
    db.load_company_data(conn)
    policy.ensure_default(conn)
    db.audit(conn, "system", "DEMO_DATA_RESET")
    for s in specs():
        if s["role"] != "seed":
            continue
        data = pdf_path(s).read_bytes()
        iid, _ = pipeline.submit(conn, data, f"{s['key']}.pdf", source="seed", background=False,
                                 extractor=pipeline.truth_extractor(truth_of(s)), use_ai_text=False)
        if s.get("seed_review"):
            r = s["seed_review"]
            decision.reviewer_action(conn, iid, r["action"], r["reason"], actor="Priya (AP Lead) - sample history")
        if verbose:
            inv = db.row(conn, "SELECT invoice_number, status, run_state, error_message FROM invoices WHERE id=?", (iid,))
            print(s["key"], inv)
    return conn


if __name__ == "__main__":
    reset(verbose=True)
