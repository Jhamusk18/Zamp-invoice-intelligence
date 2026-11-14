"""Approval policy: versioned, never edited in place.

Saving creates a NEW version. Each decision stores the version it used, so changing the policy
never silently changes historical decisions.
"""
import json
import time

from core.db import audit, row, rows, tx

DEFAULT_POLICY = {
    # price variance bands, per PO line (amounts compared BEFORE tax)
    "tolerance_pct": 2.0,          # within this -> pass
    "tolerance_cap": 10000.0,      # ...and never more than this many rupees per line
    "reject_variance_pct": 5.0,    # above this -> Blocked; between the two -> Needs Attention
    "qty_tolerance_pct": 0.0,      # billed qty may exceed (received - already billed) by this much
    "auto_approve_limit": 100000.0,  # invoice total above this always needs a person
    "vendor_match": "medium",      # strict | medium | flexible
    "fuzzy_dup_amount_pct": 1.0,
    "fuzzy_dup_days": 30,
    "math_tolerance": 1.0,         # rupees of rounding allowed in arithmetic checks
    "rules": {
        "duplicate": True,       # locked
        "bank": True,            # locked
        "short_delivery": True,
        "po_match": True,
        "vendor_name": True,
    },
}
LOCKED_RULES = {"duplicate", "bank"}
VENDOR_MATCH_THRESHOLDS = {"strict": 95, "medium": 88, "flexible": 80}

RULE_INFO = {
    "duplicate": ("Duplicate invoice check", "Flags invoices that look like a repeat (same vendor and number, or same amount and close dates)."),
    "bank": ("Bank account change check", "Flags when the bank account on the invoice differs from the one on the vendor record."),
    "short_delivery": ("Short delivery check", "Flags when the billed quantity is more than what was received (goods only)."),
    "po_match": ("Order match (PO) check", "Matches the invoice to a purchase order and compares prices, items and the remaining balance."),
    "vendor_name": ("Vendor name check", "Checks the vendor name against the vendor record using the chosen strictness."),
}


def normalise(settings: dict) -> dict:
    """Fill missing keys from defaults and force locked rules on."""
    out = json.loads(json.dumps(DEFAULT_POLICY))
    for k, v in (settings or {}).items():
        if k == "rules":
            out["rules"].update(v)
        else:
            out[k] = v
    for r in LOCKED_RULES:
        out["rules"][r] = True
    if out["vendor_match"] not in VENDOR_MATCH_THRESHOLDS:
        raise ValueError("vendor_match must be strict, medium or flexible")
    if not (0 <= out["tolerance_pct"] <= out["reject_variance_pct"] <= 50):
        raise ValueError("Need 0 ≤ tolerance ≤ reject threshold ≤ 50%")
    if out["auto_approve_limit"] < 0 or out["tolerance_cap"] < 0:
        raise ValueError("Amounts cannot be negative")
    return out


def ensure_default(conn):
    if not row(conn, "SELECT version FROM policies LIMIT 1"):
        with tx(conn):
            conn.execute("INSERT INTO policies (version, settings, created_at, created_by, note) VALUES (1,?,?,?,?)",
                         (json.dumps(DEFAULT_POLICY), time.time(), "system", "Default policy"))
            audit(conn, "system", "POLICY_CREATED", version=1, note="Default policy")


def active(conn) -> tuple[int, dict]:
    r = row(conn, "SELECT version, settings FROM policies ORDER BY version DESC LIMIT 1")
    return r["version"], normalise(json.loads(r["settings"]))


def get(conn, version: int) -> dict:
    r = row(conn, "SELECT settings FROM policies WHERE version=?", (version,))
    return normalise(json.loads(r["settings"]))


def save(conn, settings: dict, actor: str = "Demo Reviewer", note: str = "") -> int:
    new = normalise(settings)
    with tx(conn):
        cur_v, cur = active(conn)
        if new == cur:
            return cur_v
        v = cur_v + 1
        conn.execute("INSERT INTO policies (version, settings, created_at, created_by, note) VALUES (?,?,?,?,?)",
                     (v, json.dumps(new), time.time(), actor, note))
        changed = {k: {"from": cur.get(k), "to": new.get(k)} for k in new if new.get(k) != cur.get(k)}
        audit(conn, actor, "POLICY_SAVED", version=v, changes=changed, note=note)
    return v


def history(conn):
    return rows(conn, "SELECT version, created_at, created_by, note FROM policies ORDER BY version DESC")
