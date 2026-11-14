"""SQLite storage.

Two kinds of data live here, and they are kept apart on purpose:
  * Company reference data (vendors, purchase_orders, po_lines, goods_receipts) - imported from
    sample_data/company/*.csv. In a real deployment these come from the company's ERP / PO spreadsheet.
  * Processing data (everything else) - created only by this system.

Only core/* modules write to the database. The Streamlit pages call core functions; they never run SQL.
"""
import csv
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("ZAMP_DB", ROOT / "data" / "zamp.db"))
COMPANY_DIR = ROOT / "sample_data" / "company"

SCHEMA = """
-- ---------- company reference data (read-only for this system) ----------
CREATE TABLE IF NOT EXISTS vendors (
  vendor_id TEXT PRIMARY KEY, name TEXT NOT NULL, aliases TEXT, gstin TEXT,
  status TEXT NOT NULL CHECK (status IN ('ACTIVE','BLOCKED','INACTIVE')),
  bank_account TEXT, ifsc TEXT, email TEXT, currency TEXT, address TEXT);

CREATE TABLE IF NOT EXISTS purchase_orders (
  po_number TEXT PRIMARY KEY, vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
  po_date TEXT, valid_until TEXT, status TEXT CHECK (status IN ('OPEN','CLOSED')),
  po_type TEXT CHECK (po_type IN ('GOODS','SERVICE')), currency TEXT, total_amount REAL);

CREATE TABLE IF NOT EXISTS po_lines (
  po_number TEXT REFERENCES purchase_orders(po_number), line_no INTEGER,
  description TEXT, quantity REAL, unit_price REAL, PRIMARY KEY (po_number, line_no));

CREATE TABLE IF NOT EXISTS goods_receipts (
  grn_number TEXT, po_number TEXT REFERENCES purchase_orders(po_number), line_no INTEGER,
  received_date TEXT, quantity_received REAL, PRIMARY KEY (grn_number, po_number, line_no));

-- ---------- processing data ----------
CREATE TABLE IF NOT EXISTS policies (
  version INTEGER PRIMARY KEY, settings TEXT NOT NULL, created_at REAL, created_by TEXT, note TEXT);

CREATE TABLE IF NOT EXISTS invoices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  file_hash TEXT NOT NULL UNIQUE,            -- SHA-256 fingerprint: same file is never processed twice
  filename TEXT, file_path TEXT, source TEXT CHECK (source IN ('seed','upload','eval')),
  uploaded_at REAL,
  run_state TEXT NOT NULL DEFAULT 'QUEUED' CHECK (run_state IN ('QUEUED','RUNNING','DONE','ERROR')),
  error_message TEXT,
  is_scanned INTEGER,
  -- extracted fields (latest trusted read)
  document_type TEXT, vendor_name TEXT, vendor_gstin TEXT, invoice_number TEXT, invoice_number_norm TEXT,
  invoice_date TEXT, due_date TEXT, po_reference TEXT, currency TEXT,
  subtotal REAL, tax REAL, total REAL, bank_account TEXT, ifsc TEXT,
  -- matches
  vendor_id TEXT, po_number TEXT, po_match_type TEXT CHECK (po_match_type IN ('EXPLICIT','INFERRED','NONE')),
  -- decision
  status TEXT CHECK (status IN ('APPROVED','FLAGGED','REJECTED')),
  decided_by TEXT CHECK (decided_by IN ('system','reviewer')),
  primary_reason TEXT, reason_codes TEXT, policy_version INTEGER, decided_at REAL,
  explanation TEXT, email_draft TEXT, extraction_meta TEXT);

CREATE TABLE IF NOT EXISTS invoice_lines (
  invoice_id INTEGER REFERENCES invoices(id) ON DELETE CASCADE, line_no INTEGER,
  description TEXT, quantity REAL, unit_price REAL, amount REAL, po_line_no INTEGER,
  PRIMARY KEY (invoice_id, line_no));

CREATE TABLE IF NOT EXISTS field_evidence (
  invoice_id INTEGER REFERENCES invoices(id) ON DELETE CASCADE, field TEXT, value TEXT, snippet TEXT,
  verification TEXT CHECK (verification IN ('TEXT','OCR','NONE')), PRIMARY KEY (invoice_id, field));

CREATE TABLE IF NOT EXISTS run_stages (
  invoice_id INTEGER REFERENCES invoices(id) ON DELETE CASCADE, stage_no INTEGER, stage TEXT,
  status TEXT CHECK (status IN ('PENDING','RUNNING','RETRYING','DONE','FAILED')),
  finding TEXT, started_at REAL, ended_at REAL, PRIMARY KEY (invoice_id, stage_no));

CREATE TABLE IF NOT EXISTS findings (
  id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER REFERENCES invoices(id) ON DELETE CASCADE,
  check_id TEXT, check_group TEXT, result TEXT CHECK (result IN ('PASS','WARN','FAIL','NA')),
  reason_code TEXT, message TEXT, expected TEXT, actual TEXT, details TEXT, policy_version INTEGER);

-- PO money state: exactly ONE row per (invoice, PO). Re-processing updates the row, so nothing is counted twice.
CREATE TABLE IF NOT EXISTS po_allocations (
  invoice_id INTEGER REFERENCES invoices(id) ON DELETE CASCADE, po_number TEXT REFERENCES purchase_orders(po_number),
  amount REAL NOT NULL, state TEXT NOT NULL CHECK (state IN ('RESERVED','COMMITTED','RELEASED')),
  updated_at REAL, PRIMARY KEY (invoice_id, po_number));

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, invoice_id INTEGER, actor TEXT NOT NULL,
  action TEXT NOT NULL, details TEXT);

-- append-only: the database itself refuses edits and deletes of audit rows
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log
  BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log
  BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;

CREATE TABLE IF NOT EXISTS chat_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id INTEGER REFERENCES invoices(id) ON DELETE CASCADE,
  ts REAL, role TEXT, content TEXT);

CREATE TABLE IF NOT EXISTS llm_cache (
  cache_key TEXT PRIMARY KEY, model TEXT, response TEXT, created_at REAL,
  input_tokens INTEGER, output_tokens INTEGER,
  raw TEXT,                 -- raw model reply, for debugging and audit
  prompt_version TEXT);

CREATE TABLE IF NOT EXISTS eval_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, started_at REAL, finished_at REAL, split TEXT, policy_version INTEGER,
  summary TEXT, results TEXT);

CREATE INDEX IF NOT EXISTS ix_inv_vendor ON invoices(vendor_id);
CREATE INDEX IF NOT EXISTS ix_inv_status ON invoices(status);
CREATE INDEX IF NOT EXISTS ix_find_inv ON findings(invoice_id);
CREATE INDEX IF NOT EXISTS ix_alloc_po ON po_allocations(po_number);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = Path(path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # UI can read while the pipeline writes
    return conn


@contextmanager
def tx(conn: sqlite3.Connection):
    """Write transaction. BEGIN IMMEDIATE takes SQLite's single write lock up front, so two
    invoices can never check-and-reserve the same PO balance at the same moment."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def init_schema(conn):
    conn.executescript(SCHEMA)


def load_company_data(conn, company_dir: Path = COMPANY_DIR):
    """(Re)load reference data from CSV. Safe to call on an empty database."""
    specs = {
        "vendors": ["vendor_id", "name", "aliases", "gstin", "status", "bank_account", "ifsc", "email", "currency", "address"],
        "purchase_orders": ["po_number", "vendor_id", "po_date", "valid_until", "status", "po_type", "currency", "total_amount"],
        "po_lines": ["po_number", "line_no", "description", "quantity", "unit_price"],
        "goods_receipts": ["grn_number", "po_number", "line_no", "received_date", "quantity_received"],
    }
    with tx(conn):
        for table, cols in specs.items():
            conn.execute(f"DELETE FROM {table}")
            with open(company_dir / f"{table}.csv", newline="") as f:
                rows = [[r[c] for c in cols] for r in csv.DictReader(f)]
            conn.executemany(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", rows)


def audit(conn, actor: str, action: str, invoice_id=None, **details):
    conn.execute("INSERT INTO audit_log (ts, invoice_id, actor, action, details) VALUES (?,?,?,?,?)",
                 (time.time(), invoice_id, actor, action, json.dumps(details, default=str)))


def rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def row(conn, sql, params=()):
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None
