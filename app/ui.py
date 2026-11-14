"""Shared look & feel + small display components. Display only - no business logic here."""
import html
import sys
import threading
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import db, seed  # noqa: E402
from core.decision import LABEL  # noqa: E402
from core.money import inr  # noqa: E402

_init_lock = threading.Lock()

CSS = """
<style>
:root { --bg:#0B0A1F; --card:#14122C; --card2:#1A1838; --line:#2B2852; --muted:#9C99BD; --txt:#ECEAF7;
        --purple:#7C5CFF; --purple2:#A78BFA; --green:#22C55E; --amber:#F5B83D; --red:#F05252; }
.stApp { background: radial-gradient(1200px 500px at 85% -10%, rgba(124,92,255,.18), transparent 60%), var(--bg); }
[data-testid="stSidebar"] { background: #0E0C24; border-right: 1px solid var(--line); }
[data-testid="stSidebarNav"] a[aria-current="page"] { background: linear-gradient(90deg,#6D4AFF,#7C5CFF) !important; border-radius: 10px; }
[data-testid="stSidebarNav"] a[aria-current="page"] span { color: white !important; }
.block-container { padding-top: 2rem; max-width: 1400px; }
h1, h2, h3 { letter-spacing: -0.02em; }
.z-sub { color: var(--muted); margin-top: -0.6rem; margin-bottom: 1.2rem; }
.z-card { background: var(--card); border: 1px solid var(--line); border-radius: 16px; padding: 18px 20px; }
.z-kpi { border-radius: 16px; padding: 16px 18px; border: 1px solid var(--line); height: 100%; }
.z-kpi .t { font-size: .85rem; color: var(--muted); display:flex; gap:8px; align-items:center; }
.z-kpi .v { font-size: 1.75rem; font-weight: 700; margin-top: 4px; }
.z-kpi .n { font-size: .82rem; color: var(--muted); }
.z-kpi.green { background: linear-gradient(135deg, rgba(34,197,94,.16), rgba(34,197,94,.04)); border-color: rgba(34,197,94,.35); }
.z-kpi.amber { background: linear-gradient(135deg, rgba(245,184,61,.16), rgba(245,184,61,.04)); border-color: rgba(245,184,61,.35); }
.z-kpi.red   { background: linear-gradient(135deg, rgba(240,82,82,.16), rgba(240,82,82,.04)); border-color: rgba(240,82,82,.35); }
.z-kpi.purple{ background: linear-gradient(135deg, rgba(124,92,255,.18), rgba(124,92,255,.04)); border-color: rgba(124,92,255,.4); }
.z-badge { display:inline-block; padding: 3px 10px; border-radius: 999px; font-size: .78rem; font-weight: 600; white-space: nowrap; }
.z-badge.APPROVED { background: rgba(34,197,94,.15); color: #4ADE80; border: 1px solid rgba(34,197,94,.4); }
.z-badge.FLAGGED  { background: rgba(245,184,61,.15); color: #FBBF24; border: 1px solid rgba(245,184,61,.45); }
.z-badge.REJECTED { background: rgba(240,82,82,.15); color: #F87171; border: 1px solid rgba(240,82,82,.45); }
.z-badge.ERROR    { background: rgba(156,153,189,.15); color: var(--muted); border: 1px solid var(--line); }
.z-badge.SEED     { background: rgba(124,92,255,.12); color: var(--purple2); border: 1px solid rgba(124,92,255,.35); }
.z-track { display:flex; align-items:flex-start; justify-content:space-between; margin: 10px 0 6px; }
.z-step { flex:1; text-align:center; position:relative; }
.z-step:not(:last-child)::after { content:""; position:absolute; top:15px; left:calc(50% + 18px); width:calc(100% - 36px); height:3px; background: var(--line); }
.z-step.DONE:not(:last-child)::after { background: var(--green); }
.z-dot { width:32px; height:32px; border-radius:50%; margin:0 auto 6px; display:flex; align-items:center; justify-content:center;
         font-weight:700; font-size:.95rem; border:2px solid var(--line); color: var(--muted); background: var(--card2); }
.z-step.DONE .z-dot { background: var(--green); border-color: var(--green); color:#06210F; }
.z-step.RUNNING .z-dot, .z-step.RETRYING .z-dot { border-color: var(--purple); color: var(--purple2); animation: zpulse 1s infinite; }
.z-step.RETRYING .z-dot { border-color: var(--amber); color: var(--amber); }
.z-step.FAILED .z-dot { background: var(--red); border-color: var(--red); color: white; }
.z-step .l { font-size: .85rem; font-weight: 600; }
.z-step .d { font-size: .75rem; color: var(--muted); }
@keyframes zpulse { 0%{box-shadow:0 0 0 0 rgba(124,92,255,.6)} 100%{box-shadow:0 0 0 10px rgba(124,92,255,0)} }
.z-verdict { border-radius: 14px; padding: 16px 18px; display:flex; gap:14px; align-items:center; }
.z-verdict.APPROVED { background: linear-gradient(90deg, rgba(34,197,94,.18), rgba(34,197,94,.05)); border:1px solid rgba(34,197,94,.45); }
.z-verdict.FLAGGED  { background: linear-gradient(90deg, rgba(245,184,61,.20), rgba(245,184,61,.05)); border:1px solid rgba(245,184,61,.5); }
.z-verdict.REJECTED { background: linear-gradient(90deg, rgba(240,82,82,.20), rgba(240,82,82,.05)); border:1px solid rgba(240,82,82,.5); }
.z-verdict.ERROR    { background: rgba(156,153,189,.08); border:1px solid var(--line); }
.z-verdict .icon { font-size: 1.8rem; }
.z-verdict .s { font-size: 1.3rem; font-weight: 700; }
.z-verdict.APPROVED .s { color:#4ADE80 } .z-verdict.FLAGGED .s { color:#FBBF24 } .z-verdict.REJECTED .s { color:#F87171 }
.z-verdict .amt { font-size: 1.3rem; font-weight: 700; margin-left: 14px; }
.z-verdict .r { color: var(--muted); font-size: .9rem; margin-top: 2px; }
.z-check { display:flex; gap:10px; padding: 10px 4px; border-bottom: 1px solid var(--line); }
.z-check .ic { width: 22px; flex: none; }
.z-check .nm { font-weight: 600; width: 190px; flex: none; }
.z-check .ms { color: #CFCDE6; font-size: .9rem; }
.z-check .ev { color: var(--muted); font-size: .8rem; margin-top: 2px; }
.z-muted { color: var(--muted); font-size: .85rem; }
.z-demo { background: rgba(124,92,255,.1); border: 1px solid rgba(124,92,255,.35); border-radius: 12px; padding: 10px 12px; font-size: .82rem; color: #CFC6FF; }
div[data-testid="stChatMessage"] { background: var(--card2); border: 1px solid var(--line); border-radius: 12px; }
.stButton > button[kind="primary"] { background: linear-gradient(90deg,#6D4AFF,#8B6CFF); border: 0; }
[data-testid="stFileUploaderDropzone"] { background: rgba(124,92,255,.06); border: 2px dashed rgba(124,92,255,.55); border-radius: 16px; padding: 34px; }
</style>
"""

ICON = {"PASS": "✅", "WARN": "⚠️", "FAIL": "⛔", "NA": "➖"}
STATUS_ICON = {"APPROVED": "✅", "FLAGGED": "⚠️", "REJECTED": "⛔", "ERROR": "❌"}


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def conn():
    """One SQLite connection per browser session. Builds the demo database on first run."""
    if "conn" not in st.session_state:
        with _init_lock:
            if not db.DB_PATH.exists():
                seed.reset()
        st.session_state.conn = db.connect()
    return st.session_state.conn


def header(title, subtitle=None):
    st.markdown(f"# {html.escape(title)}")
    if subtitle:
        st.markdown(f"<div class='z-sub'>{html.escape(subtitle)}</div>", unsafe_allow_html=True)


def badge(inv):
    if inv["run_state"] != "DONE":
        txt = "Failed" if inv["run_state"] == "ERROR" else "Processing…"
        return f"<span class='z-badge ERROR'>{txt}</span>"
    s = inv["status"]
    extra = " · reviewer" if inv.get("decided_by") == "reviewer" else ""
    return f"<span class='z-badge {s}'>{LABEL[s]}{extra}</span>"


def lakh(x):
    if x >= 1e7:
        return f"₹{x / 1e7:.2f}Cr"
    if x >= 1e5:
        return f"₹{x / 1e5:.2f}L"
    return inr(x, decimals=0)


def kpi(kind, title, value, note, icon=""):
    st.markdown(f"<div class='z-kpi {kind}'><div class='t'>{icon} {html.escape(title)}</div>"
                f"<div class='v'>{value}</div><div class='n'>{html.escape(note)}</div></div>", unsafe_allow_html=True)


def tracker(stages, now):
    parts = []
    for s in stages:
        st_ = s["status"]
        sym = {"DONE": "✓", "FAILED": "✕", "RUNNING": "•", "RETRYING": "↻"}.get(st_, str(s["stage_no"]))
        if s["started_at"] and s["ended_at"]:
            d = f"{s['ended_at'] - s['started_at']:.1f} s"
        elif s["started_at"] and st_ in ("RUNNING", "RETRYING"):
            d = f"{now - s['started_at']:.1f} s…"
        else:
            d = {"PENDING": "waiting"}.get(st_, "")
        parts.append(f"<div class='z-step {st_}'><div class='z-dot'>{sym}</div><div class='l'>{html.escape(s['stage'])}</div><div class='d'>{d}</div></div>")
    st.markdown("<div class='z-track'>" + "".join(parts) + "</div>", unsafe_allow_html=True)


def verdict(inv):
    from core import queries as q
    if inv["run_state"] == "ERROR":
        st.markdown(f"<div class='z-verdict ERROR'><div class='icon'>❌</div><div><div class='s'>Processing failed</div>"
                    f"<div class='r'>{html.escape(inv['error_message'] or '')}</div><div class='r'>No decision was made and no PO money was touched.</div></div></div>",
                    unsafe_allow_html=True)
        return
    s = inv["status"]
    who = " · approved by reviewer" if (inv["decided_by"] == "reviewer" and s == "APPROVED") else (" · rejected by reviewer" if inv["decided_by"] == "reviewer" else "")
    st.markdown(f"<div class='z-verdict {s}'><div class='icon'>{STATUS_ICON[s]}</div><div style='flex:1'>"
                f"<div><span class='s'>{LABEL[s]}{who}</span><span class='amt'>{inr(inv['total'], decimals=0)}</span></div>"
                f"<div class='r'><b>{'System reason' if inv['decided_by'] == 'reviewer' else 'Reason'}:</b> {html.escape(inv['primary_reason'] or '')}</div>"
                + (f"<div class='r'><b>Reviewer ({html.escape(note['actor'])}):</b> {html.escape(note['details'].get('reason', ''))}</div>" if (note := (q.reviewer_note(conn(), inv['id']) if inv['decided_by'] == 'reviewer' else None)) else "")
                + "</div></div>", unsafe_allow_html=True)


def demo_note():
    st.sidebar.markdown("<div class='z-demo'>⚡ <b>Prototype</b><br>Sample company data. History invoices are pre-processed "
                        "from known values; uploads are read by AI.</div>", unsafe_allow_html=True)
