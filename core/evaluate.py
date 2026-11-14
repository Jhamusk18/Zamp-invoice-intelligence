"""Eval Benchmark.

Each case runs through the REAL pipeline (AI extraction, cached by file fingerprint) in its own fresh copy of the sample
company, so cases can't affect each other. Two scores per case:
  * extraction: extracted fields vs the ground truth the PDF was generated from
  * decision:   status (and required reason codes) vs the expected label
Labels: the hand-checked demo set has hand-written expected outcomes. Generated eval sets get their expected outcome
by running the rules engine on the ground-truth record ("decision given perfect extraction") - so they measure the
AI + pipeline, not the rules themselves. Rule logic is covered by the hand-checked set and unit tests.
"""
import json
import shutil
import tempfile
import time
from pathlib import Path

from core import db, pipeline, seed
from core.models import EVIDENCE_FIELDS

# rough paid-tier prices per 1M tokens, only to show what a run WOULD cost beyond the free tier (USD)
PRICE = {"input": 0.10, "output": 0.40}
FIELDS = ["vendor_gstin", "invoice_number", "invoice_date", "po_reference", "subtotal", "tax", "total", "bank_account"]


def cases(set_name="demo"):
    out = []
    for s in seed.specs():
        if set_name == "demo" and s["role"] == "demo":
            out.append({"key": s["key"], "title": s.get("title", s["key"]), "layout": s["layout"] + (" (scan)" if s.get("scanned") else ""),
                        "category": s.get("title", ""), "pdf": seed.PDF_DIR / f"{s['key']}.pdf", "truth": seed.truth_of(s),
                        "expected": s["expected"], "split": "held-out"})
    evalfile = db.ROOT / "sample_data" / "eval" / "eval_set.json"
    if set_name != "demo" and evalfile.exists():
        for s in json.loads(evalfile.read_text())["cases"]:
            if set_name in ("all", s["split"]):
                out.append({**s, "pdf": evalfile.parent / s["file"], "truth": seed.truth_of(s)})
    return out


def _same(a, b):
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (int, float)) or isinstance(b, (int, float)):
        try:
            return abs(float(a) - float(b)) < 0.5
        except ValueError:
            return False
    from core.rules import norm_invoice_number
    return norm_invoice_number(str(a)) == norm_invoice_number(str(b))


def run(set_name="demo", use_cache=True, progress=None):
    tmp = Path(tempfile.mkdtemp(prefix="zamp_eval_"))
    base = tmp / "base.db"
    seed.reset(base).close()
    results = []
    cs = cases(set_name)
    t_start = time.time()
    for n, c in enumerate(cs):
        if progress:
            progress(n, len(cs), c["title"])
        path = tmp / f"case_{n}.db"
        shutil.copy(base, path)
        conn = db.connect(path)
        t0 = time.time()
        iid, _ = pipeline.submit(conn, c["pdf"].read_bytes(), c["pdf"].name, source="eval", background=False, use_cache=use_cache, use_ai_text=False)
        inv = db.row(conn, "SELECT * FROM invoices WHERE id=?", (iid,))
        meta = json.loads(inv["extraction_meta"] or "{}")
        tin = sum(r.get("input_tokens") or 0 for r in meta.get("reads", []))
        tout = sum(r.get("output_tokens") or 0 for r in meta.get("reads", []))
        truth = c["truth"]
        fields = {f: _same(inv[f], truth.value(f)) for f in FIELDS} if inv["run_state"] == "DONE" else {}
        codes = json.loads(inv["reason_codes"] or "[]")
        exp = c["expected"]
        status_ok = inv["run_state"] == "DONE" and inv["status"] == exp["status"]
        reasons_ok = set(exp.get("reasons", [])) <= set(codes)
        results.append({"key": c["key"], "title": c["title"], "category": c["category"], "layout": c["layout"], "split": c["split"],
                        "expected": exp["status"], "got": inv["status"] if inv["run_state"] == "DONE" else "ERROR",
                        "status_ok": status_ok, "reasons_ok": reasons_ok, "missing_reasons": sorted(set(exp.get("reasons", [])) - set(codes)),
                        "extra_reasons": sorted(set(codes) - set(exp.get("reasons", []))),
                        "fields_ok": sum(fields.values()), "fields_total": len(FIELDS), "wrong_fields": [f for f, ok in fields.items() if not ok],
                        "retried": bool(meta.get("retry_reason")), "seconds": round(time.time() - t0, 1),
                        "tokens_in": tin, "tokens_out": tout, "cached": all(r.get("cached") for r in meta.get("reads", [])) if meta.get("reads") else False,
                        "error": inv["error_message"]})
        conn.close()
    shutil.rmtree(tmp, ignore_errors=True)
    summary = summarise(results)
    summary["seconds"] = round(time.time() - t_start, 1)
    return summary, results


def summarise(results):
    n = len(results) or 1
    fa = [r for r in results if r["expected"] != "APPROVED" and r["got"] == "APPROVED"]  # false approvals: the costly error
    ff = [r for r in results if r["expected"] == "APPROVED" and r["got"] != "APPROVED"]  # false alarms: wasted AP time
    tin = sum(r["tokens_in"] for r in results)
    tout = sum(r["tokens_out"] for r in results)
    return {"cases": len(results), "decision_accuracy": sum(r["status_ok"] for r in results) / n,
            "reason_accuracy": sum(r["status_ok"] and r["reasons_ok"] for r in results) / n,
            "field_accuracy": sum(r["fields_ok"] for r in results) / max(1, sum(r["fields_total"] for r in results if r["got"] != "ERROR")),
            "false_approvals": len(fa), "false_alarms": len(ff), "errors": sum(r["got"] == "ERROR" for r in results),
            "straight_through": sum(r["got"] == "APPROVED" for r in results) / n,
            "tokens_in": tin, "tokens_out": tout,
            "cost_per_invoice_usd": (tin * PRICE["input"] + tout * PRICE["output"]) / 1e6 / n}


def save(conn, set_name, summary, results, policy_version):
    with db.tx(conn):
        conn.execute("INSERT INTO eval_runs (started_at, finished_at, split, policy_version, summary, results) VALUES (?,?,?,?,?,?)",
                     (time.time() - summary.get("seconds", 0), time.time(), set_name, policy_version, json.dumps(summary), json.dumps(results)))
