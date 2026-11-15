"""Shared look & feel + small display components. Display only - no business logic here.

Style: blue accent; dark navy top bar and hero; light content area with white cards.
"""
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
STATIC = Path(__file__).parent / "static"

CSS = """
<style>
:root { --navy:#0B1B3A; --navy2:#13285A; --blue:#2563EB; --blue2:#3B82F6; --sky:#EAF1FF; --bg:#F4F7FC; --card:#FFFFFF;
        --line:#DCE4F2; --muted:#5B6B86; --txt:#0F1B33;
        --green:#15803D; --greenbg:#E8F7EE; --amber:#B45309; --amberbg:#FFF4E0; --red:#B91C1C; --redbg:#FDECEC; }

/* ---------- top bar (dark) ---------- */
header[data-testid="stHeader"] { background: var(--navy) !important; height: 3.6rem; border-bottom: 1px solid #1E3570; }
header[data-testid="stHeader"] a, header[data-testid="stHeader"] span, header[data-testid="stHeader"] p { color: #D7E3FF !important; }
header[data-testid="stHeader"] a[aria-current="page"] { background: rgba(59,130,246,.22) !important; border-radius: 8px; }
header[data-testid="stHeader"] a[aria-current="page"] span, header[data-testid="stHeader"] a[aria-current="page"] p { color: #fff !important; font-weight: 600; }
header[data-testid="stHeader"] button svg { fill: #D7E3FF; color: #D7E3FF; }
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none; }
.block-container { padding-top: 4.6rem; max-width: 1320px; }
.stApp { background: var(--bg); }
h1, h2, h3, h4 { letter-spacing: -0.02em; color: var(--txt); }
h1 { font-size: 2rem !important; font-weight: 750 !important; }

/* ---------- building blocks ---------- */
.z-sub { color: var(--muted); margin-top: -0.5rem; margin-bottom: 1.1rem; font-size: .98rem; }
.z-muted { color: var(--muted); font-size: .86rem; }
.z-card { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 18px 20px; box-shadow: 0 1px 2px rgba(15,27,51,.04); }
div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 14px; }
.st-key-card, [class*="st-key-card_"] { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 16px 18px;
  box-shadow: 0 1px 3px rgba(15,27,51,.05); }

.z-pill { display:inline-flex; align-items:center; gap:6px; padding: 3px 11px; border-radius: 999px; font-size: .8rem; font-weight: 650; white-space: nowrap; }
.z-pill.APPROVED { background: var(--greenbg); color: var(--green); }
.z-pill.FLAGGED  { background: var(--amberbg); color: var(--amber); }
.z-pill.REJECTED { background: var(--redbg); color: var(--red); }
.z-pill.ERROR    { background: #EEF1F6; color: var(--muted); }
.z-pill .dot { width:7px; height:7px; border-radius:50%; background: currentColor; }
.z-tag { display:inline-block; font-size:.68rem; padding:0 6px; border-radius:6px; background: var(--sky); color: var(--blue); font-weight:600; margin-top:2px; }
.z-sublabel { display:block; font-size:.74rem; color: var(--muted); margin-top:3px; }

.z-kpi { border-radius: 14px; padding: 16px 18px; background: #fff; border: 1px solid var(--line); border-top: 4px solid var(--line); }
.z-kpi .t { font-size: .85rem; color: var(--muted); font-weight: 600; }
.z-kpi .v { font-size: 1.55rem; font-weight: 750; margin-top: 4px; color: var(--txt); }
.z-kpi .n { font-size: .84rem; color: var(--muted); }
.z-kpi.green { border-top-color: #22C55E; } .z-kpi.amber { border-top-color: #F59E0B; } .z-kpi.red { border-top-color: #EF4444; } .z-kpi.blue { border-top-color: var(--blue2); }

/* stepper */
.z-track { display:flex; align-items:flex-start; justify-content:space-between; margin: 6px 0 4px; }
.z-step { flex:1; text-align:center; position:relative; padding: 0 4px; }
.z-step:not(:last-child)::after { content:""; position:absolute; top:15px; left:calc(50% + 18px); width:calc(100% - 36px); height:3px; background: var(--line); border-radius:2px; }
.z-step.DONE:not(:last-child)::after { background: #22C55E; }
.z-dot { width:32px; height:32px; border-radius:50%; margin:0 auto 6px; display:flex; align-items:center; justify-content:center;
         font-weight:700; font-size:.92rem; border:2px solid var(--line); color: var(--muted); background: #fff; }
.z-step.DONE .z-dot { background: #22C55E; border-color: #22C55E; color:#fff; }
.z-step.RUNNING .z-dot { border-color: var(--blue); color: var(--blue); animation: zpulse 1s infinite; }
.z-step.RETRYING .z-dot { border-color: #F59E0B; color: #B45309; animation: zpulse 1s infinite; }
.z-step.FAILED .z-dot { background: #EF4444; border-color: #EF4444; color: #fff; }
.z-step .l { font-size: .84rem; font-weight: 650; color: var(--txt); }
.z-step .d { font-size: .74rem; color: var(--muted); }
.z-step .f { font-size: .74rem; color: #33445F; margin-top: 3px; line-height: 1.25; min-height: 1.9em; }
@keyframes zpulse { 0%{box-shadow:0 0 0 0 rgba(37,99,235,.45)} 100%{box-shadow:0 0 0 10px rgba(37,99,235,0)} }

/* verdict */
.z-verdict { border-radius: 16px; padding: 18px 20px; background:#fff; border:1px solid var(--line); border-left: 6px solid var(--line); }
.z-verdict.APPROVED { border-left-color:#22C55E; } .z-verdict.FLAGGED { border-left-color:#F59E0B; } .z-verdict.REJECTED { border-left-color:#EF4444; } .z-verdict.ERROR { border-left-color:#94A3B8; }
.z-verdict .row1 { display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
.z-verdict .amt { font-size: 1.6rem; font-weight: 750; color: var(--txt); margin-left:auto; }
.z-verdict .vend { font-weight: 650; font-size: 1.05rem; margin-top: 8px; color: var(--txt); }
.z-verdict .r { color: #33445F; font-size: .95rem; margin-top: 4px; }
.z-verdict .nx { margin-top: 10px; padding: 9px 12px; background: var(--sky); border-radius: 10px; color: #1E3A8A; font-size: .9rem; }

/* checks */
.z-check { display:flex; gap:12px; padding: 12px 2px; border-bottom: 1px solid #EDF1F8; }
.z-check:last-child { border-bottom: 0; }
.z-check .ic { width: 22px; flex: none; font-size: 1rem; }
.z-check .nm { font-weight: 650; color: var(--txt); }
.z-check .ms { color: #33445F; font-size: .9rem; margin-top: 2px; }
.z-check .cmp { color: var(--muted); font-size: .84rem; margin-top: 3px; }
.z-na { color: var(--muted); font-size: .82rem; padding: 4px 0; }

/* history rows */
.z-thead { display:flex; color: var(--muted); font-size:.78rem; font-weight:650; text-transform:uppercase; letter-spacing:.04em; padding: 0 6px 6px; }
[class*="st-key-row_"] { background:#fff; border:1px solid var(--line); border-radius: 12px; padding: 6px 10px; transition: all .12s; }
[class*="st-key-row_"]:hover { border-color: var(--blue2); box-shadow: 0 4px 14px rgba(37,99,235,.10); }
.z-row { display:flex; align-items:center; gap: 10px; min-height: 2.6rem; }
.z-cell { font-size: .9rem; color: var(--txt); line-height: 1.3; padding-right: 6px; }
[class*="st-key-row_"] [data-testid="stMarkdownContainer"] p { margin: 0; }
[class*="st-key-row_"] [data-testid="stMarkdown"], [class*="st-key-row_"] [data-testid="stElementContainer"] { margin-bottom: 0 !important; }
[class*="st-key-row_"] { padding: 10px 12px !important; }
[class*="st-key-row_"] [data-testid="stColumn"] { align-self: center; }
[data-testid="stLogo"] { height: 2.2rem; max-width: 15rem; }
.z-reason { font-size: .86rem; color: #33445F; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* ask panel */
[class*="st-key-ask_"] { background:#fff; border: 1.5px solid #BFD3FF; border-radius: 16px; padding: 16px 16px 10px; }
.st-key-ask_glow { animation: zglow 2.2s ease-out 1; }
@keyframes zglow { 0%{ box-shadow: 0 0 0 0 rgba(37,99,235,.55); border-color:#2563EB } 100%{ box-shadow: 0 0 0 18px rgba(37,99,235,0); border-color:#BFD3FF } }
[class*="st-key-ask_"] .stButton > button { min-height: 2.9rem; justify-content: flex-start; text-align: left; border-radius: 12px; border-color:#D6E2FA; background:#F7FAFF; }
[class*="st-key-ask_"] .stButton > button:hover { border-color: var(--blue2); background: var(--sky); }
.z-teaser-q { border:1px dashed #CBD6EA; border-radius: 12px; padding: 10px 12px; margin: 6px 0; color:#9AA8C0; font-size:.9rem; }
div[data-testid="stChatMessage"] { background: #F7FAFF; border: 1px solid #E3EBFA; border-radius: 12px; }

/* upload drop zone: soft blue fill, dashed border, document icon, raised blue button */
[data-testid="stFileUploaderDropzone"] { background: linear-gradient(180deg, #EEF4FF 0%, #E3EDFD 100%); border: 2px dashed #9FB3D1; border-radius: 16px;
  padding: 56px 30px; min-height: 300px; display:flex; flex-direction: column; align-items:center; justify-content:center; gap: 22px; text-align:center;
  box-shadow: 0 8px 24px rgba(37,99,235,.08); transition: all .15s; }
[data-testid="stFileUploaderDropzone"]:hover { border-color: #2563EB; background: linear-gradient(180deg, #E8F0FF 0%, #DCE8FD 100%); }
[data-testid="stFileUploaderDropzone"]::before { content: ""; width: 66px; height: 80px;
  background: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 66 80'><path d='M8 3h34l21 21v47a6 6 0 0 1-6 6H8a6 6 0 0 1-6-6V9a6 6 0 0 1 6-6z' fill='%23DCE7FB' stroke='%234F7BD9' stroke-width='3' stroke-linejoin='round'/><path d='M42 3v15a6 6 0 0 0 6 6h15' fill='%23C3D5F6' stroke='%234F7BD9' stroke-width='3' stroke-linejoin='round'/><path d='M33 60V36M22 46l11-11 11 11' fill='none' stroke='%234F7BD9' stroke-width='4' stroke-linecap='round' stroke-linejoin='round'/></svg>") no-repeat center / contain; }
[data-testid="stFileUploaderDropzoneInstructions"] { display: none; }
[data-testid="stFileUploaderDropzone"] button { background: linear-gradient(180deg, #2F6BF0, #1D4ED8); color: #fff; border: 0; padding: 10px 26px;
  border-radius: 10px; font-weight: 650; font-size: 1rem; box-shadow: 0 6px 14px rgba(29,78,216,.35); }
[data-testid="stFileUploaderDropzone"] button:hover { background: linear-gradient(180deg, #3B76F5, #2563EB); color: #fff; transform: translateY(-1px); }
[data-testid="stFileUploaderDropzone"] button p, [data-testid="stFileUploaderDropzone"] button span { color: #fff !important; }
[data-testid="stFileUploader"] > label p { font-size: 1.05rem; font-weight: 650; color: #0F1B33; }
.stButton > button[kind="primary"] { background: var(--blue); border: 0; }
.stButton > button[kind="primary"]:hover { background: #1D4ED8; }

/* decision made: a clear coloured strip */
.z-decided { border-radius: 12px; padding: 12px 14px; margin: 4px 0 10px; border: 1px solid transparent; }
.z-decided.APPROVED { background: var(--greenbg); border-color: #BFE8CD; } .z-decided.REJECTED { background: var(--redbg); border-color: #F6C9C9; }
.z-decided .top { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.z-decided .why { margin-top: 6px; color: var(--txt); font-size: .95rem; }

/* the vendor email: looks like an email, clearly separate from the form */
[class*="st-key-mail_"] { background:#fff; border:1px solid #CFDCF5; border-radius:14px; overflow:hidden; padding:0 !important; gap: 0 !important;
  box-shadow: 0 8px 22px rgba(15,27,51,.08); margin-top: 6px; }
.z-mailhead { display:flex; align-items:center; gap:10px; background: linear-gradient(90deg,#0B1B3A,#1E3A8A); padding: 12px 16px; }
.z-mailhead b { color:#fff; font-size: .98rem; } .z-mailhead span { color:#fff; }
.z-draft { margin-left:auto; font-size:.72rem; background: rgba(255,255,255,.16); color:#DCE7FF !important; padding:2px 9px; border-radius:999px; }
.z-mailfield { display:flex; gap:12px; padding: 9px 16px; border-bottom: 1px solid #EDF1F8; font-size: .9rem; color: var(--txt); background: #F8FAFE; }
.z-mailfield > span { width: 62px; flex: none; color: var(--muted); font-weight: 600; }
[class*="st-key-mail_"] [data-testid="stCode"] { margin: 0 !important; }
[class*="st-key-mail_"] [data-testid="stMarkdown"], [class*="st-key-mail_"] [data-testid="stElementContainer"] { margin-bottom: 0 !important; }
[class*="st-key-mail_"] [data-testid="stMarkdownContainer"] { overflow: visible; margin-bottom: 0 !important; }
[class*="st-key-mail_"] [data-testid="stCode"] pre { background: #fff !important; border-radius: 0 !important; padding: 16px 18px !important; }
[class*="st-key-mail_"] [data-testid="stCode"] pre, [class*="st-key-mail_"] [data-testid="stCode"] code {
  font-family: "Source Sans Pro", "Segoe UI", sans-serif !important; font-size: .95rem !important; line-height: 1.6 !important; color: var(--txt) !important; white-space: pre-wrap !important; }
[class*="st-key-mail_"] [data-testid="stHorizontalBlock"] { padding: 10px 16px 14px; border-top: 1px solid #EDF1F8; background: #F8FAFE; }

/* review: keep the PDF in view while scrolling */
.st-key-pdfpane { position: sticky; top: 4.4rem; }
</style>
"""

ICON = {"PASS": "✅", "WARN": "⚠️", "FAIL": "⛔", "NA": "➖"}


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
        st.markdown(f"<div class='z-sub'>{subtitle}</div>", unsafe_allow_html=True)


def pill(inv, with_sub=False):
    if inv["run_state"] != "DONE":
        return f"<span class='z-pill ERROR'><span class='dot'></span>{'Failed' if inv['run_state'] == 'ERROR' else 'Processing…'}</span>"
    s = inv["status"]
    out = f"<span class='z-pill {s}'><span class='dot'></span>{LABEL[s]}</span>"
    if with_sub and inv.get("decided_by") == "reviewer":
        out += f"<span class='z-sublabel'>{'approved' if s == 'APPROVED' else 'rejected'} by reviewer</span>"
    return out


def kpi(kind, title, amount, count):
    st.markdown(f"<div class='z-kpi {kind}'><div class='t'>{html.escape(title)}</div>"
                f"<div class='v'>{inr(amount, decimals=0)}</div><div class='n'>{count} invoice{'s' if count != 1 else ''}</div></div>",
                unsafe_allow_html=True)


def stat(kind, title, value, note):
    """A small number card (used where the value isn't money)."""
    st.markdown(f"<div class='z-kpi {kind}'><div class='t'>{html.escape(title)}</div><div class='v'>{html.escape(str(value))}</div>"
                f"<div class='n'>{html.escape(note)}</div></div>", unsafe_allow_html=True)


def secs(x):
    return "under 0.1 s" if x < 0.1 else f"{x:.1f} s"


def short(finding, n=46):
    if not finding:
        return ""
    t = finding.split(" · ")[0]
    return html.escape(t if len(t) <= n else t[: n - 1] + "…")


def stepper(stages, now):
    parts = []
    for s in stages:
        st_ = s["status"]
        sym = {"DONE": "✓", "FAILED": "✕", "RUNNING": "•", "RETRYING": "↻"}.get(st_, str(s["stage_no"]))
        if s["started_at"] and s["ended_at"]:
            d = secs(s["ended_at"] - s["started_at"])
        elif s["started_at"] and st_ in ("RUNNING", "RETRYING"):
            d = secs(now - s["started_at"]) + "…"
        else:
            d = "waiting"
        f = short(s["finding"]) if st_ in ("DONE", "FAILED", "RETRYING", "RUNNING") else ""
        parts.append(f"<div class='z-step {st_}'><div class='z-dot'>{sym}</div><div class='l'>{html.escape(s['stage'])}</div>"
                     f"<div class='d'>{d}</div><div class='f'>{f}</div></div>")
    st.markdown("<div class='z-track'>" + "".join(parts) + "</div>", unsafe_allow_html=True)


def verdict(inv, next_step=None):
    """Big result card: status pill, amount, vendor, one plain reason, optional 'what to do next'."""
    from core import queries as q
    if inv["run_state"] == "ERROR":
        st.markdown(f"<div class='z-verdict ERROR'><div class='row1'><span class='z-pill ERROR'><span class='dot'></span>Processing failed</span></div>"
                    f"<div class='r'>{html.escape(inv['error_message'] or '')}</div>"
                    f"<div class='nx'>No decision was made and no PO money was touched. Use <b>Retry</b> when ready.</div></div>",
                    unsafe_allow_html=True)
        return
    s = inv["status"]
    reason = inv["primary_reason"] or ""
    rev = ""
    if inv["decided_by"] == "reviewer":
        note = q.reviewer_note(conn(), inv["id"])
        if note:
            rev = f"<div class='r'><b>Reviewer:</b> {html.escape(note['details'].get('reason', ''))} <span class='z-muted'>(system said: {html.escape(reason)})</span></div>"
            reason = ""
    nx = f"<div class='nx'><b>What to do next:</b> {html.escape(next_step)}</div>" if next_step else ""
    st.markdown(f"<div class='z-verdict {s}'><div class='row1'>{pill(inv)}"
                f"<span class='z-muted'>{'decided by a reviewer' if inv['decided_by'] == 'reviewer' else 'decided by the rules'}</span>"
                f"<span class='amt'>{inr(inv['total'], decimals=0)}</span></div>"
                f"<div class='vend'>{html.escape(inv['vendor_name'] or 'Unknown vendor')} · {html.escape(inv['invoice_number'] or '')}</div>"
                + (f"<div class='r'>{html.escape(reason)}</div>" if reason else "") + rev + nx + "</div>", unsafe_allow_html=True)
