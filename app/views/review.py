import html
import json
from datetime import datetime

import pymupdf
import streamlit as st

from app import helper_panel, ui
from core import db, decision, queries as q
from core.decision import LABEL
from core.money import inr, mask_account

conn = ui.conn()
try:
    iid = int(st.query_params.get("id"))
except (TypeError, ValueError):
    iid = None
inv = q.invoice(conn, iid) if iid else None
if not inv:
    ui.header("Invoice Review")
    st.info("Pick an invoice from the History page.")
    if st.button("Go to History", type="primary"):
        st.switch_page(st.session_state.pages["invoices"])
    st.stop()

# ---------------- header: breadcrumb, title, prev / next within the current list order
order = st.session_state.get("review_order") or q.ordered_ids(conn, {}, "Invoice date (newest)")
if iid not in order:
    order = q.ordered_ids(conn, {}, "Invoice date (newest)")
pos = order.index(iid) if iid in order else 0
h = st.columns([6, 0.5, 0.9, 0.5])
if h[0].button("← History", type="tertiary"):
    st.switch_page(st.session_state.pages["invoices"])
if h[1].button("‹", disabled=pos == 0, help="Previous invoice"):
    st.switch_page(st.session_state.pages["review"], query_params={"id": str(order[pos - 1])})
h[2].markdown(f"<div style='text-align:center;padding-top:6px'>{pos + 1} of {len(order)}</div>", unsafe_allow_html=True)
if h[3].button("›", disabled=pos >= len(order) - 1, help="Next invoice"):
    st.switch_page(st.session_state.pages["review"], query_params={"id": str(order[pos + 1])})

st.markdown(f"# Invoice Review — {html.escape(inv['invoice_number'] or inv['filename'])}")
src = "Sample history (processed from known values, no AI)" if inv["source"] == "seed" else "Uploaded"
st.markdown(f"<div class='z-sub'>{html.escape(inv['vendor_name'] or 'Unknown vendor')} · {inr(inv['total'], decimals=0)} · "
            f"{inv['invoice_date'] or '—'} · {src}{' · policy v' + str(inv['policy_version']) if inv['policy_version'] else ''}</div>",
            unsafe_allow_html=True)

left, right = st.columns([1, 1.25], gap="large")

# ---------------- left: original document + extracted data
with left:
    t_pdf, t_data = st.tabs(["Invoice (PDF)", "Extracted Data"])
    with t_pdf:
        data = (db.ROOT / inv["file_path"]).read_bytes()
        doc = pymupdf.open(stream=data, filetype="pdf")
        z = st.session_state.setdefault(f"zoom_{iid}", 1.0)
        pg = st.session_state.setdefault(f"page_{iid}", 0)
        tb = st.columns([1, 1.3, 1, 1, 1, 2.2])
        if tb[0].button("‹", key="pp", disabled=pg == 0):
            st.session_state[f"page_{iid}"] -= 1
            st.rerun()
        tb[1].markdown(f"<div style='padding-top:6px;text-align:center'>{pg + 1} / {doc.page_count}</div>", unsafe_allow_html=True)
        if tb[2].button("›", key="np", disabled=pg >= doc.page_count - 1):
            st.session_state[f"page_{iid}"] += 1
            st.rerun()
        if tb[3].button("−", key="zo", disabled=z <= 0.6):
            st.session_state[f"zoom_{iid}"] = round(z - 0.25, 2)
            st.rerun()
        if tb[4].button("+", key="zi", disabled=z >= 2.5):
            st.session_state[f"zoom_{iid}"] = round(z + 0.25, 2)
            st.rerun()
        tb[5].download_button("Download", data, file_name=inv["filename"] or "invoice.pdf", mime="application/pdf", icon=":material/download:")
        st.caption(f"Zoom {int(z * 100)}% · {'scanned image (original scan shown)' if inv['is_scanned'] else 'original PDF'}")
        png = doc[pg].get_pixmap(dpi=int(110 * z)).tobytes("png")
        with st.container(height=640):
            st.image(png, use_container_width=z <= 1.0)
    with t_data:
        if inv["run_state"] != "DONE":
            st.info("No extracted data - processing didn't finish.")
        else:
            how = {"TEXT": "✅ Verified (text)", "OCR": "✅ Verified (OCR)", "NONE": "⚠️ Not verified"}
            ev = q.evidence(conn, iid)
            st.dataframe([{"Field": e["field"].replace("_", " ").title(),
                           "Value": mask_account(e["value"]) if e["field"] == "bank_account" else e["value"],
                           "Quote from the document": (e["snippet"] or "—").replace(e["value"], mask_account(e["value"])) if e["field"] == "bank_account" and e["snippet"] else (e["snippet"] or "—"),
                           "Check": how[e["verification"]]} for e in ev], hide_index=True, use_container_width=True)
            st.markdown("**Line items**")
            st.dataframe([{"Description": l["description"], "Qty": l["quantity"], "Rate (₹)": l["unit_price"], "Amount (₹)": l["amount"]}
                          for l in q.lines(conn, iid)], hide_index=True, use_container_width=True)
            st.caption(f"Subtotal {inr(inv['subtotal'])} · Tax {inr(inv['tax'])} · Total {inr(inv['total'])}")
            meta = json.loads(inv["extraction_meta"] or "{}")
            for r in meta.get("reads", []):
                st.caption(f"Read by **{r.get('model')}**" + (" (cached)" if r.get("cached") else "")
                           + (f" · {r.get('input_tokens', 0)}+{r.get('output_tokens', 0)} tokens" if r.get("input_tokens") else ""))
            if meta.get("disagreements"):
                st.warning("The two reads disagreed:")
                st.dataframe(meta["disagreements"], hide_index=True)

# ---------------- right: decision + tabs
with right:
    ui.verdict(inv)
    if inv["run_state"] != "DONE":
        st.stop()
    tabs = st.tabs(["Validation Checklist", "Details & Matches", "Email Draft", "Audit Trail"])
    fs = q.findings(conn, iid)
    with tabs[0]:
        for g in ["Document", "Vendor", "Duplicate", "Purchase order", "Policy"]:
            items = [f for f in fs if f["check_group"] == g]
            if not items:
                continue
            st.markdown(f"<div class='z-muted' style='margin-top:10px;text-transform:uppercase;letter-spacing:.06em'>{g}</div>", unsafe_allow_html=True)
            rows = []
            for f in items:
                ex = ""
                if f["expected"] or f["actual"]:
                    ex = f"<div class='ev'>Expected: <b>{html.escape(str(f['expected'] or '—'))}</b> · Found: <b>{html.escape(str(f['actual'] or '—'))}</b></div>"
                rows.append(f"<div class='z-check'><div class='ic'>{ui.ICON[f['result']]}</div><div class='nm'>{html.escape(f['details'].get('label', f['check_id']))}</div>"
                            f"<div><div class='ms'>{html.escape(f['message'])}</div>{ex}</div></div>")
            st.markdown("".join(rows), unsafe_allow_html=True)
        st.caption("✅ passed · ⚠️ needs attention · ⛔ blocks payment · ➖ not applicable")

    with tabs[1]:
        v = q.vendor(conn, inv["vendor_id"])
        st.markdown("##### Vendor record")
        if v:
            st.markdown(f"**{v['name']}** · {v['vendor_id']} · status **{v['status']}**  \nGSTIN {v['gstin']} · bank {mask_account(v['bank_account'])} · IFSC {v['ifsc']}  \n{v['email']} · {v['address']}")
        else:
            st.markdown("*Not matched to an approved vendor.*")
        po = q.po_detail(conn, inv["po_number"])
        st.markdown("##### Purchase order")
        if po:
            st.markdown(f"**{po['po_number']}** ({po['po_type'].lower()}, {po['status'].lower()}, valid until {po['valid_until']}) · "
                        + ("matched from the PO number on the invoice" if inv["po_match_type"] == "EXPLICIT" else "⚠️ **suggested match - needs confirming**"))
            m = st.columns(4)
            m[0].metric("PO total", inr(po["total_amount"], decimals=0))
            m[1].metric("Paid / approved", inr(po["committed"], decimals=0))
            m[2].metric("On hold", inr(po["reserved"], decimals=0))
            m[3].metric("Remaining", inr(po["remaining"], decimals=0))
            ls = q.lines(conn, iid)
            rows3 = []
            for l in ls:
                pl = next((x for x in po["lines"] if x["line_no"] == l["po_line_no"]), None)
                rows3.append({"Invoice item": l["description"], "PO item": pl["description"] if pl else "— not on PO",
                              "Ordered": pl["quantity"] if pl else None,
                              "Received": (pl["received"] if po["po_type"] == "GOODS" else None) if pl else None,
                              "Invoiced": l["quantity"], "PO rate": pl["unit_price"] if pl else None, "Invoice rate": l["unit_price"]})
            st.markdown("**Line comparison** " + ("(3-way: ordered · received · invoiced)" if po["po_type"] == "GOODS" else "(2-way: service, no goods receipt)"))
            st.dataframe(rows3, hide_index=True, use_container_width=True)
            st.markdown("**All invoices against this PO**")
            st.dataframe([{"Invoice": x["invoice_number"], "Date": x["invoice_date"], "Amount (pre-tax)": x["amount"],
                           "PO money": {"COMMITTED": "Committed", "RESERVED": "Reserved (on hold)", "RELEASED": "Released"}[x["state"]],
                           "Status": LABEL.get(x["status"], "")} for x in po["invoices"]], hide_index=True, use_container_width=True)
            if po["receipts"]:
                st.markdown("**Goods receipts**")
                st.dataframe([{"GRN": r["grn_number"], "Line": r["line_no"], "Received on": r["received_date"], "Qty": r["quantity_received"]}
                              for r in po["receipts"]], hide_index=True, use_container_width=True)
        else:
            st.markdown("*No purchase order matched.*")
        cands = next((f["details"].get("candidates") for f in fs if f["check_id"] == "PO_MATCH" and f["details"].get("candidates")), None)
        if cands:
            st.markdown("**PO candidates considered** (score = 0.5 × items + 0.35 × amount + 0.15 × dates)")
            st.dataframe(cands, hide_index=True)

    with tabs[2]:
        if inv["email_draft"]:
            e = json.loads(inv["email_draft"])
            st.markdown(f"**To:** {e['to']}  \n**Subject:** {e['subject']}")
            st.code(e["body"], language=None, wrap_lines=True)
            st.caption("Draft only - use the copy icon. Nothing is sent automatically. Sent to the address on file, never one taken from the invoice.")
        else:
            st.info("No vendor email needed for this invoice.")
        if inv["explanation"]:
            st.markdown("**Explanation for the AP team**")
            st.markdown(f"<div class='z-card'>{html.escape(inv['explanation'])}</div>", unsafe_allow_html=True)

    with tabs[3]:
        for a in q.audit(conn, iid):
            d = {k: v for k, v in a["details"].items() if v not in (None, "", [], {})}
            st.markdown(f"<div class='z-check'><div class='ic'>•</div><div class='nm' style='width:150px'>{datetime.fromtimestamp(a['ts']):%d %b %H:%M:%S}</div>"
                        f"<div><div class='ms'><b>{html.escape(a['action'].replace('_', ' ').title())}</b> · {html.escape(a['actor'])}</div>"
                        f"<div class='ev'>{html.escape(json.dumps(d, default=str)[:400])}</div></div></div>", unsafe_allow_html=True)
        st.caption("Append-only: the database rejects edits and deletions of audit entries.")

    # ---------------- human decision
    st.write("")
    with st.container(border=True):
        acts = decision.allowed_actions(inv)
        st.markdown("**Decision (manual)**")
        if not acts:
            st.caption("No action available: " + ("this invoice was blocked by the system and can't be approved with a click." if inv["status"] == "REJECTED" and inv["decided_by"] == "system"
                                                 else "a reviewer has already decided."))
        else:
            if "approve" in acts and "BANK_CHANGED" in (inv["reason_codes"] or ""):
                st.warning("Bank account differs from the record. Only approve after calling the vendor on the number **on file**.", icon="📞")
            # One dropdown: every allowed choice says what it does (approve / reject) and why. Then one Submit.
            ICON_A = {"approve": "✅ Approve", "reject": "⛔ Reject"}
            opts = [(a, r) for a in ("approve", "reject") if a in acts for r in decision.REVIEW_REASONS[a]]
            opts += [(a, None) for a in ("approve", "reject") if a in acts]  # "other reason" per action
            labels = ["— choose a decision —"] + [f"{ICON_A[a]} — {r}" if r else f"{ICON_A[a]} — other reason (type below)" for a, r in opts]
            pick = st.selectbox("Decision and reason *", labels, key=f"dec_{iid}")
            chosen = opts[labels.index(pick) - 1] if pick != labels[0] else None
            note = st.text_input("Your own reason / note" + (" *" if chosen and chosen[1] is None else " (optional)"),
                                 placeholder="e.g. confirmed with Ravi in procurement", key=f"note_{iid}")
            if chosen:
                a, r = chosen
                eff = "**Ready to Pay** (PO amount committed)" if a == "approve" else "**Blocked** (PO amount released)"
                st.caption(f"On submit this invoice becomes {eff}, and your reason is saved in the audit trail.")
            if st.button("Submit decision", type="primary", icon=":material/send:", disabled=chosen is None, key=f"submit_{iid}"):
                a, r = chosen
                reason = (r + (f" - {note.strip()}" if note.strip() else "")) if r else note.strip()
                try:
                    new = decision.reviewer_action(conn, iid, a, reason)
                    for k in (f"dec_{iid}", f"note_{iid}"):
                        st.session_state.pop(k, None)
                    st.toast(f"Saved: {LABEL[new]}. Recorded in the audit trail.", icon="✅")
                    st.rerun()
                except (ValueError, PermissionError) as e:
                    st.error(str(e))

with st.expander("✨ Invoice Helper for this invoice"):
    helper_panel.render(conn, iid, "rv")
