import pandas as pd
import streamlit as st

from app import ui
from core import queries as q
from core.decision import LABEL

conn = ui.conn()
ui.header("History", "Every invoice processed so far, its status and the reason.")

# Filters live in session_state (not only in widgets) so they survive going to a Review page and back.
DEFAULTS = {"search": "", "statuses": [], "vendors": [], "period": "All time", "custom": None, "sort": "Invoice date (newest)", "page": 1}
F = st.session_state.setdefault("inv_filters", dict(DEFAULTS))


def _set(k):
    F[k] = st.session_state[f"w_{k}"]
    F["page"] = 1


for k in ("search", "statuses", "vendors", "period", "sort"):
    st.session_state[f"w_{k}"] = F[k]

c = st.columns([2.6, 1.6, 1.8, 1.3, 0.8])
c[0].text_input("Search", placeholder="🔍 Search invoice number, vendor, PO…", key="w_search", on_change=_set, args=("search",), label_visibility="collapsed")
c[1].multiselect("Status", ["Ready to Pay", "Needs Attention", "Blocked", "Processing / failed"], key="w_statuses",
                 on_change=_set, args=("statuses",), placeholder="All statuses", label_visibility="collapsed")
c[2].multiselect("Vendor", q.vendor_names(conn), key="w_vendors", on_change=_set, args=("vendors",), placeholder="All vendors", label_visibility="collapsed")
c[3].selectbox("Invoice date", ["All time", "Last 7 days", "Last 30 days", "Last 90 days", "Custom range"], key="w_period",
               on_change=_set, args=("period",), label_visibility="collapsed")
if c[4].button("Clear", use_container_width=True, help="Clear filters"):
    st.session_state.inv_filters = dict(DEFAULTS)
    st.rerun()
if F["period"] == "Custom range":
    rng = st.date_input("Invoice date between", value=F["custom"] or [], key="w_custom")
    F["custom"] = rng if isinstance(rng, (list, tuple)) and len(rng) == 2 else None
d_from, d_to = q.date_range(F["period"], custom=F["custom"])
flt = {"search": F["search"].strip(), "statuses": F["statuses"], "vendors": F["vendors"], "date_from": d_from, "date_to": d_to}

# ---- summary cards: calculated from the database for the current filters
s = q.summary(conn, flt)
k = st.columns(4)
with k[0]:
    ui.kpi("green", "Ready to Pay", ui.lakh(s["APPROVED"]["amount"]), f"{s['APPROVED']['count']} invoices · {s['AUTO']} automatic", "✅")
with k[1]:
    ui.kpi("amber", "Needs Attention", ui.lakh(s["FLAGGED"]["amount"]), f"{s['FLAGGED']['count']} invoices", "⚠️")
with k[2]:
    ui.kpi("red", "Blocked", ui.lakh(s["REJECTED"]["amount"]), f"{s['REJECTED']['count']} invoices", "⛔")
with k[3]:
    ui.kpi("purple", "Total Invoices", str(s["ALL"]), "matching filters" if any(flt.values()) else "all time", "🧾")
st.write("")

# ---- table
top = st.columns([4, 1.6])
top[1].selectbox("Sort by", list(q.SORTS), key="w_sort", on_change=_set, args=("sort",), label_visibility="collapsed")
PAGE = 10
data, total = q.list_invoices(conn, flt, F["sort"], F["page"], PAGE)
st.session_state.review_order = q.ordered_ids(conn, flt, F["sort"])  # for "1 of N" + prev/next on the Review page

if total == 0:
    with st.container(border=True):
        if any(flt.values()):
            st.markdown("#### No invoices match these filters.\nTry clearing them.")
        else:
            st.markdown("#### No invoices yet. Upload one to get started.")
            if st.button("Upload Invoice", type="primary"):
                st.switch_page(st.session_state.pages["upload"])
    st.stop()

ICON = {"APPROVED": "🟢", "FLAGGED": "🟠", "REJECTED": "🔴"}


def status_text(r):
    if r["run_state"] == "ERROR":
        return "⚪ Failed run"
    if r["run_state"] != "DONE":
        return "⏳ Processing"
    return f"{ICON[r['status']]} {LABEL[r['status']]}" + (" · reviewer" if r["decided_by"] == "reviewer" else "")


df = pd.DataFrame([{
    "Status": status_text(r), "Invoice Number": r["invoice_number"] or r["filename"], "Vendor": r["vendor_name"] or "—",
    "Amount (₹)": r["total"], "Reason (one line)": r["primary_reason"] or (r["error_message"] or "")[:90],
    "Invoice date": r["invoice_date"], "Source": "Sample history" if r["source"] == "seed" else "Uploaded",
} for r in data])
ev = st.dataframe(df, hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row", key=f"tbl_{F['page']}",
                  column_config={"Amount (₹)": st.column_config.NumberColumn(format="₹ %,.0f"),
                                 "Reason (one line)": st.column_config.TextColumn(width="large"),
                                 "Invoice date": st.column_config.DateColumn(format="DD MMM YYYY")},
                  height=38 + 35 * len(df))
if ev.selection.rows:
    st.switch_page(st.session_state.pages["review"], query_params={"id": str(data[ev.selection.rows[0]]["id"])})

pages = max(1, -(-total // PAGE))
b = st.columns([3, 0.6, 1, 0.6])
b[0].caption(f"Showing {(F['page'] - 1) * PAGE + 1}–{min(F['page'] * PAGE, total)} of {total} invoices · click a row to review it")
if b[1].button("‹", disabled=F["page"] <= 1, use_container_width=True):
    F["page"] -= 1
    st.rerun()
b[2].markdown(f"<div style='text-align:center;padding-top:6px'>Page {F['page']} of {pages}</div>", unsafe_allow_html=True)
if b[3].button("›", disabled=F["page"] >= pages, use_container_width=True):
    F["page"] += 1
    st.rerun()
