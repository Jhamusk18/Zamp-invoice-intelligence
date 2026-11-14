import html

import streamlit as st

from app import ui
from core import queries as q
from core.money import inr

conn = ui.conn()

# Filters live in session_state so they survive going to a Review page and back.
DEFAULTS = {"search": "", "statuses": [], "vendors": [], "period": "All time", "custom": None, "sort": "Invoice date (newest)", "page": 1}
F = st.session_state.setdefault("inv_filters", dict(DEFAULTS))


def _set(k):
    F[k] = st.session_state[f"w_{k}"]
    F["page"] = 1


for k in ("search", "statuses", "vendors", "period", "sort"):
    st.session_state[f"w_{k}"] = F[k]

d_from, d_to = q.date_range(F["period"], custom=F["custom"])
flt = {"search": F["search"].strip(), "statuses": F["statuses"], "vendors": F["vendors"], "date_from": d_from, "date_to": d_to}
active = any([flt["search"], flt["statuses"], flt["vendors"], F["period"] != "All time"]) or F["sort"] != DEFAULTS["sort"]
s = q.summary(conn, flt)

ui.header("History", f"{s['ALL']} invoice{'s' if s['ALL'] != 1 else ''}{' matching your filters' if active else ' processed so far'} - "
          "click any row to open its full review.")

# ---- three summary cards, full amounts
k = st.columns(3)
with k[0]:
    ui.kpi("green", "Ready to Pay", s["APPROVED"]["amount"], s["APPROVED"]["count"])
with k[1]:
    ui.kpi("amber", "Needs Attention", s["FLAGGED"]["amount"], s["FLAGGED"]["count"])
with k[2]:
    ui.kpi("red", "Blocked", s["REJECTED"]["amount"], s["REJECTED"]["count"])
st.write("")

# ---- one filter row: search · status · More filters · Clear (only when something is active)
c = st.columns([3, 2.2, 1.3, 0.8], vertical_alignment="center")
c[0].text_input("Search", placeholder="🔍  Search invoice number, vendor or PO", key="w_search", on_change=_set, args=("search",), label_visibility="collapsed")
c[1].multiselect("Status", ["Ready to Pay", "Needs Attention", "Blocked", "Processing / failed"], key="w_statuses", on_change=_set,
                 args=("statuses",), placeholder="All statuses", label_visibility="collapsed")
n_more = len(F["vendors"]) + (F["period"] != "All time") + (F["sort"] != DEFAULTS["sort"])
with c[2].popover(f"More filters{f' ({n_more})' if n_more else ''}", use_container_width=True, icon=":material/tune:"):
    st.multiselect("Vendor", q.vendor_names(conn), key="w_vendors", on_change=_set, args=("vendors",), placeholder="All vendors")
    st.selectbox("Invoice date", ["All time", "Last 7 days", "Last 30 days", "Last 90 days", "Custom range"], key="w_period", on_change=_set, args=("period",))
    if F["period"] == "Custom range":
        rng = st.date_input("Between", value=F["custom"] or [], key="w_custom")
        if isinstance(rng, (list, tuple)) and len(rng) == 2 and F["custom"] != rng:
            F["custom"] = rng
            st.rerun()
    st.selectbox("Sort by", list(q.SORTS), key="w_sort", on_change=_set, args=("sort",))
if active and c[3].button("Clear", type="tertiary"):
    st.session_state.inv_filters = dict(DEFAULTS)
    st.rerun()

PAGE = 10
data, total = q.list_invoices(conn, flt, F["sort"], F["page"], PAGE)
st.session_state.review_order = q.ordered_ids(conn, flt, F["sort"])  # for "1 of N" + prev/next on the Review page

if total == 0:
    with st.container(key="card_empty"):
        if active:
            st.markdown("#### Nothing matches these filters")
            st.markdown("<span class='z-muted'>Try a different search, or clear the filters.</span>", unsafe_allow_html=True)
        else:
            st.markdown("#### No invoices yet")
            st.markdown("<span class='z-muted'>Upload your first invoice and it will appear here with its decision.</span>", unsafe_allow_html=True)
            if st.button("Upload an invoice", type="primary"):
                st.switch_page(st.session_state.pages["upload"])
    st.stop()

# ---- the table: clean rows, status with a small "by reviewer" label, one-line reason (full text on hover)
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
W = [1.25, 1.2, 1.55, 0.9, 3.0, 0.7]
st.markdown("<div class='z-thead'>" + "".join(f"<div style='flex:{w}'>{h}</div>" for w, h in zip(W + [0.55], ["Status", "Invoice", "Vendor", "Amount", "Reason", "Date", ""]))
            + "</div>", unsafe_allow_html=True)
for r in data:
    with st.container(key=f"row_{r['id']}"):
        c1, c2 = st.columns([sum(W), 0.55], vertical_alignment="center")
        tag = "<span class='z-tag'>Sample</span>" if r["source"] == "seed" else ""
        reason = r["primary_reason"] or r["error_message"] or ""
        d = r["invoice_date"] or ""
        date = f"{d[8:10]} {MON[int(d[5:7]) - 1]}" if len(d) == 10 else "—"
        cells = [ui.pill(r, with_sub=True),
                 f"<b>{html.escape(r['invoice_number'] or r['filename'] or '')}</b><br>{tag}",
                 html.escape(r["vendor_name"] or "—"),
                 inr(r["total"], decimals=0) if r["total"] is not None else "—",
                 f"<div class='z-reason' title='{html.escape(reason)}'>{html.escape(reason)}</div>",
                 f"<span class='z-muted'>{date}</span>"]
        c1.markdown("<div class='z-row' style='display:flex;flex-direction:row;align-items:center;gap:10px;min-height:2.6rem'>"
                    + "".join(f"<div class='z-cell' style='flex:{w} 1 0;min-width:0'>{x}</div>" for w, x in zip(W, cells)) + "</div>",
                    unsafe_allow_html=True)
        if c2.button("Open", key=f"open_{r['id']}", icon=":material/arrow_forward:", type="tertiary"):
            st.switch_page(st.session_state.pages["review"], query_params={"id": str(r["id"])})

pages = max(1, -(-total // PAGE))
b = st.columns([4, 0.5, 1, 0.5], vertical_alignment="center")
b[0].markdown(f"<span class='z-muted'>Showing {(F['page'] - 1) * PAGE + 1}–{min(F['page'] * PAGE, total)} of {total}</span>", unsafe_allow_html=True)
if pages > 1:
    if b[1].button("‹", disabled=F["page"] <= 1, use_container_width=True):
        F["page"] -= 1
        st.rerun()
    b[2].markdown(f"<div style='text-align:center'>Page {F['page']} of {pages}</div>", unsafe_allow_html=True)
    if b[3].button("›", disabled=F["page"] >= pages, use_container_width=True):
        F["page"] += 1
        st.rerun()
