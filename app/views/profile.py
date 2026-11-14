from datetime import datetime

import streamlit as st

from app import ui
from app.sections import assumptions, rules
from core.db import rows

conn = ui.conn()
ME = "Demo Reviewer"

c1, c2 = st.columns([0.12, 1])
c1.markdown("<div style='width:72px;height:72px;border-radius:50%;background:linear-gradient(135deg,#6D4AFF,#A78BFA);"
            "display:flex;align-items:center;justify-content:center;font-size:1.6rem;font-weight:700;margin-top:18px'>DR</div>",
            unsafe_allow_html=True)
with c2:
    st.markdown("# Demo Reviewer")
    st.markdown("<div class='z-sub'>AP Reviewer · Acme Retail India (sample company) · prototype account, no login</div>", unsafe_allow_html=True)

tab_me, tab_rules, tab_about = st.tabs(["My activity", "Approval rules", "About this prototype"])

with tab_me:
    acts = rows(conn, """SELECT a.ts, a.action, a.details, i.id, i.invoice_number, i.vendor_name, i.total
                         FROM audit_log a JOIN invoices i ON i.id = a.invoice_id
                         WHERE a.actor = ? AND a.action IN ('REVIEWER_APPROVE','REVIEWER_REJECT','UPLOADED')
                         ORDER BY a.id DESC""", (ME,))
    import json
    up = sum(a["action"] == "UPLOADED" for a in acts)
    ap = sum(a["action"] == "REVIEWER_APPROVE" for a in acts)
    rj = sum(a["action"] == "REVIEWER_REJECT" for a in acts)
    k = st.columns(3)
    with k[0]:
        ui.kpi("purple", "Invoices uploaded", str(up), "by you", "⬆️")
    with k[1]:
        ui.kpi("green", "Approved by you", str(ap), "with a reason", "✅")
    with k[2]:
        ui.kpi("red", "Rejected by you", str(rj), "with a reason", "⛔")
    st.write("")
    if not acts:
        st.markdown("<div class='z-card z-muted'>No activity yet. Upload an invoice, or approve / reject one from History.</div>", unsafe_allow_html=True)
    else:
        label = {"UPLOADED": "⬆️ Uploaded", "REVIEWER_APPROVE": "✅ Approved", "REVIEWER_REJECT": "⛔ Rejected"}
        data = [{"When": datetime.fromtimestamp(a["ts"]).strftime("%d %b %Y %H:%M"), "Action": label[a["action"]],
                 "Invoice": a["invoice_number"] or "—", "Vendor": a["vendor_name"] or "—", "Amount (₹)": a["total"],
                 "Reason": json.loads(a["details"] or "{}").get("reason", ""), "id": a["id"]} for a in acts]
        ev = st.dataframe(data, hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row",
                          column_order=["When", "Action", "Invoice", "Vendor", "Amount (₹)", "Reason"],
                          column_config={"Amount (₹)": st.column_config.NumberColumn(format="₹ %,.0f")})
        st.caption("Click a row to open that invoice.")
        if ev.selection.rows:
            st.switch_page(st.session_state.pages["review"], query_params={"id": str(data[ev.selection.rows[0]]["id"])})

with tab_rules:
    rules.render()

with tab_about:
    assumptions.render()
