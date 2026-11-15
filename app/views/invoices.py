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

# ---- three summary cards in their own colours
tot = sum(s[k]["amount"] for k in ("APPROVED", "FLAGGED", "REJECTED")) or 1
k = st.columns(3)
with k[0]:
    ui.kpi("green", "Ready to Pay", s["APPROVED"]["amount"], s["APPROVED"]["count"], s["APPROVED"]["amount"] / tot)
with k[1]:
    ui.kpi("amber", "Needs Attention", s["FLAGGED"]["amount"], s["FLAGGED"]["count"], s["FLAGGED"]["amount"] / tot)
with k[2]:
    ui.kpi("red", "Blocked", s["REJECTED"]["amount"], s["REJECTED"]["count"], s["REJECTED"]["amount"] / tot)
st.write("")

PAGE = 10
data, total = q.list_invoices(conn, flt, F["sort"], F["page"], PAGE)
st.session_state.review_order = q.ordered_ids(conn, flt, F["sort"])  # for "1 of N" + prev/next on the Review page
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

with st.container(key="card_table"):
    # ---- header row of the table card: title + count · search · status · More filters · Clear
    c = st.columns([1.7, 2.6, 2.0, 1.25, 0.6], vertical_alignment="center")
    c[0].markdown(f"<div class='z-tabletitle'>All invoices <span class='z-count'>{total} total</span></div>", unsafe_allow_html=True)
    c[1].text_input("Search", placeholder="🔍  Search invoice, vendor or PO", key="w_search", on_change=_set, args=("search",), label_visibility="collapsed")
    c[2].multiselect("Status", ["Ready to Pay", "Needs Attention", "Blocked", "Processing / failed"], key="w_statuses", on_change=_set,
                     args=("statuses",), placeholder="All statuses", label_visibility="collapsed")
    n_more = len(F["vendors"]) + (F["period"] != "All time") + (F["sort"] != DEFAULTS["sort"])
    with c[3].popover(f"Filters{f' ({n_more})' if n_more else ''}", use_container_width=True, icon=":material/tune:"):
        st.multiselect("Vendor", q.vendor_names(conn), key="w_vendors", on_change=_set, args=("vendors",), placeholder="All vendors")
        st.selectbox("Invoice date", ["All time", "Last 7 days", "Last 30 days", "Last 90 days", "Custom range"], key="w_period", on_change=_set, args=("period",))
        if F["period"] == "Custom range":
            rng = st.date_input("Between", value=F["custom"] or [], key="w_custom")
            if isinstance(rng, (list, tuple)) and len(rng) == 2 and F["custom"] != rng:
                F["custom"] = rng
                st.rerun()
        st.selectbox("Sort by", list(q.SORTS), key="w_sort", on_change=_set, args=("sort",))
    if active and c[4].button("Clear", type="tertiary"):
        st.session_state.inv_filters = dict(DEFAULTS)
        st.rerun()

    if total == 0:
        st.markdown("<div style='text-align:center;padding:34px 0'>"
                    + ("<b>Nothing matches these filters.</b><br><span class='z-muted'>Try a different search, or clear the filters.</span>" if active else
                       "<b>No invoices yet.</b><br><span class='z-muted'>Upload your first invoice and it will appear here with its decision.</span>")
                    + "</div>", unsafe_allow_html=True)
        if not active and st.button("Upload an invoice", type="primary"):
            st.switch_page(st.session_state.pages["upload"])
        st.stop()

    W = [1.75, 1.85, 0.95, 1.25, 2.4, 0.65]
    st.markdown("<div class='z-thead'>" + "".join(f"<div style='flex:{w} 1 0'>{h}</div>" for w, h in zip(W + [1.0], ["Invoice", "Vendor", "<div style='text-align:right;padding-right:14px'>Amount</div>", "Status", "Reason", "Date", "Action"]))
                + "</div>", unsafe_allow_html=True)
    for r in data:
        with st.container(key=f"row_{r['id']}"):
            c1, c2 = st.columns([sum(W), 1.0], vertical_alignment="center")
            reason = r["primary_reason"] or r["error_message"] or ""
            d = r["invoice_date"] or ""
            date = f"{d[8:10]} {MON[int(d[5:7]) - 1]}" if len(d) == 10 else "—"
            sub = "Sample history" if r["source"] == "seed" else "Uploaded"
            cells = [ui.file_cell(r["invoice_number"] or r["filename"] or "", sub),
                     f"<div class='z-vend'>{ui.avatar(r['vendor_name'] or '?')}<span class='nm'>{html.escape(r['vendor_name'] or '—')}</span></div>",
                     f"<span class='z-amt'>{inr(r['total'], decimals=0) if r['total'] is not None else '—'}</span>",
                     ui.pill(r, with_sub=True),
                     f"<div class='z-reason' title='{html.escape(reason)}'>{html.escape(reason)}</div>",
                     f"<span class='z-muted'>{date}</span>"]
            c1.markdown("<div style='display:flex;flex-direction:row;align-items:center;gap:10px;min-height:3rem'>"
                        + "".join(f"<div class='z-cell' style='flex:{w} 1 0;min-width:0'>{x}</div>" for w, x in zip(W, cells)) + "</div>",
                        unsafe_allow_html=True)
            if c2.button("Open", key=f"open_{r['id']}", icon=":material/arrow_forward:"):
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
