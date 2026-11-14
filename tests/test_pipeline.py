"""Hand-checked cases: every demo invoice, through the full pipeline (ground-truth extractor, no AI),
must reach its expected status with all expected reasons. Plus the key safety rules."""
import json
import pytest

from core import db, decision, pipeline, policy, seed
from core.document import TechnicalError, check_upload


@pytest.fixture()
def conn(tmp_path):
    c = seed.reset(tmp_path / "t.db")
    yield c
    c.close()


def run(conn, key):
    s = next(x for x in seed.specs() if x["key"] == key)
    iid, _ = pipeline.submit(conn, (seed.pdf_path(key)).read_bytes(), key + ".pdf", background=False,
                             extractor=pipeline.truth_extractor(seed.truth_of(s)), use_ai_text=False)
    return s, db.row(conn, "SELECT * FROM invoices WHERE id=?", (iid,))


@pytest.mark.parametrize("key", [s["key"] for s in seed.specs() if s["role"] == "demo"])
def test_demo_cases(conn, key):
    s, inv = run(conn, key)
    assert inv["run_state"] == "DONE"
    assert inv["status"] == s["expected"]["status"]
    assert set(s["expected"]["reasons"]) <= set(json.loads(inv["reason_codes"]))


def test_same_file_is_not_processed_twice(conn):
    _, inv = run(conn, "D1_happy_path")
    data = (seed.pdf_path("D1_happy_path")).read_bytes()
    iid, seen = pipeline.submit(conn, data, "again.pdf", background=False)
    assert seen and iid == inv["id"]


def test_not_a_pdf_is_refused():
    with pytest.raises(TechnicalError):
        check_upload(b"hello", "x.pdf")


def test_reviewer_needs_reason_and_cannot_approve_blocked(conn):
    _, inv = run(conn, "X1_duplicate")
    with pytest.raises(PermissionError):
        decision.reviewer_action(conn, inv["id"], "approve", "looks fine to me")
    _, inv = run(conn, "D3_bank_change_injection")
    with pytest.raises(ValueError):
        decision.reviewer_action(conn, inv["id"], "approve", "")
    assert decision.reviewer_action(conn, inv["id"], "approve", "Verified with vendor by phone") == "APPROVED"
    a = db.row(conn, "SELECT state FROM po_allocations WHERE invoice_id=?", (inv["id"],))
    assert a["state"] == "COMMITTED"


def test_audit_log_is_append_only(conn):
    with pytest.raises(Exception):
        conn.execute("DELETE FROM audit_log")


def test_reprocessing_does_not_double_count(conn):
    _, inv = run(conn, "X2_split_po_overbill")
    before = db.rows(conn, "SELECT * FROM po_allocations WHERE invoice_id=?", (inv["id"],))
    pipeline.run(inv["id"], conn=conn, extractor=pipeline.truth_extractor(seed.truth_of(next(s for s in seed.specs() if s["key"] == "X2_split_po_overbill"))), use_ai_text=False)
    after = db.rows(conn, "SELECT * FROM po_allocations WHERE invoice_id=?", (inv["id"],))
    assert len(before) == len(after) == 1 and before[0]["amount"] == after[0]["amount"]


def test_locked_rules_cannot_be_disabled(conn):
    v = policy.save(conn, {**policy.DEFAULT_POLICY, "rules": {**policy.DEFAULT_POLICY["rules"], "bank": False}})
    assert policy.get(conn, v)["rules"]["bank"] is True
