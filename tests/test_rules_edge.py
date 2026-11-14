"""Edge cases raised in review: recurring bills vs duplicates, similar vendor names, lookalikes, no OCR engine."""
import json
from datetime import date
from unittest import mock

import pytest

from core import db, pipeline, policy, rules, seed
from core.models import InvoiceExtraction, Line


@pytest.fixture()
def conn(tmp_path):
    c = seed.reset(tmp_path / "t.db")
    yield c
    c.close()


def inv(**kw):
    base = dict(document_type="INVOICE", vendor_name="Meridian Cloud Services Pvt Ltd", vendor_gstin="29AAHCM7788P1Z3",
                invoice_number="MC-INV-2301", invoice_date="2026-12-01", due_date="2026-12-15", po_reference=None, currency="INR",
                lines=[Line(description="Cloud hosting and managed services - November 2026", quantity=1, unit_price=123050, amount=123050)],
                subtotal=123050, tax=22149, total=145199, bank_account="7712009988", ifsc="ICIC0007712")
    base.update(kw)
    return InvoiceExtraction(**base)


def codes(conn, x):
    _, pol = policy.active(conn)
    r = rules.evaluate(x, rules.load_snapshot(conn, None), pol, today=date(2026, 12, 31))
    return {f.check_id: (f.result, f.reason_code) for f in r.findings}, r


def test_monthly_recurring_bill_is_not_a_duplicate(conn):
    # Meridian billed 1,45,199 on 1 Nov (sample history). Same amount, new number, a month later = normal.
    c, _ = codes(conn, inv())
    assert c["DUPLICATE"][0] == "PASS"


def test_same_amount_within_days_is_suspected(conn):
    c, _ = codes(conn, inv(invoice_number="MC-INV-9999", invoice_date="2026-11-04"))
    assert c["DUPLICATE"] == ("WARN", "DUPLICATE_SUSPECTED")


def test_similar_number_same_amount_is_suspected(conn):
    c, _ = codes(conn, inv(invoice_number="MC-INV-2210A"))
    assert c["DUPLICATE"] == ("WARN", "DUPLICATE_SUSPECTED")


def test_suffix_differences_still_match_vendor(conn):
    c, r = codes(conn, inv(vendor_name="MERIDIAN CLOUD SERVICES PRIVATE LIMITED", vendor_gstin=None))
    assert r.vendor_id == "V007"


def test_two_real_vendors_with_similar_names_are_not_confused(conn):
    # add a genuinely different, approved company with a similar name
    conn.execute("INSERT INTO vendors VALUES ('V099','Meridian Cloud Solutions Pvt Ltd','', '29AAHCM9999Q1Z1','ACTIVE','5555000011','ICIC0000001','x@y.in','INR','Pune')")
    _, r = codes(conn, inv(vendor_name="Meridian Cloud Solutions Pvt Ltd", vendor_gstin="29AAHCM9999Q1Z1", bank_account="5555000011", ifsc="ICIC0000001"))
    assert r.vendor_id == "V099"
    _, r = codes(conn, inv(vendor_name="Meridian Cloud Solutions", vendor_gstin=None, bank_account="5555000011", ifsc="ICIC0000001"))
    assert r.vendor_id == "V099"   # by name only, the closer name wins


def test_lookalike_with_other_gstin_is_blocked_not_softer_than_unknown(conn):
    c, r = codes(conn, inv(vendor_name="Meridian Cloud Servises Pvt Ltd", vendor_gstin="29AAHCM1111Z1Z9"))
    assert c["VENDOR"] == ("FAIL", "VENDOR_LOOKALIKE") and r.vendor_id is None


def test_lookalike_without_gstin_goes_to_a_person(conn):
    # a typo'd name with no GSTIN might be the real vendor: a person checks
    c, _ = codes(conn, inv(vendor_name="Meridan Clowd Servces", vendor_gstin=None))
    assert c["VENDOR"][0] in ("WARN", "PASS")


def test_scan_without_ocr_engine_goes_to_a_person_not_an_error(conn):
    s = next(x for x in seed.specs() if x["key"] == "D2_scanned_no_po")
    with mock.patch("core.document.ocr_pages", return_value=None):
        iid, _ = pipeline.submit(conn, (seed.pdf_path("D2_scanned_no_po")).read_bytes(), "scan.pdf", background=False,
                                 extractor=pipeline.truth_extractor(seed.truth_of(s)), use_ai_text=False)
    i = db.row(conn, "SELECT run_state, status, reason_codes FROM invoices WHERE id=?", (iid,))
    assert i["run_state"] == "DONE" and i["status"] == "FLAGGED" and "UNVERIFIED_FIELD" in json.loads(i["reason_codes"])
