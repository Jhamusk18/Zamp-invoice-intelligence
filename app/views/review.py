import html
import json
from datetime import datetime

import pymupdf
import streamlit as st

from app import helper_panel, ui
from core import db, decision, helper, queries as q
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
    st.info("Pick an invoice from History.")
    if st.button("Go to History", type="primary"):
        st.switch_page(st.session_state.pages["history"])
    st.stop()

# ---------------- compact header: breadcrumb · title · facts · prev/next · Ask
order = st.session_state.get("review_order") or q.ordered_ids(conn, {}, "Invoice date (newest)")
if iid not in order:
    order = q.ordered_ids(conn, {}, "Invoice date (newest)")
pos = order.index(iid) if iid in order else 0
name = inv["invoice_number"] or inv["filename"]

h = st.columns([5.2, 1.9, 0.45, 0.8, 0.45], vertical_alignment="center")
with h[0]:
    if st.button(f"History  /  {name}", type="tertiary", icon=":material/arrow_back:"):
        st.switch_page(st.session_state.pages["history"])
with h[1].popover("Ask about this invoice", icon=":material/chat:", use_container_width=True):
    helper_panel.render(conn, iid, "rv", height=300)
if h[2].button("‹", disabled=pos == 0, help="Previous invoice"):
    st.switch_page(st.session_state.pages["review"], query_params={"id": str(order[pos - 1])})
h[3].markdown(f"<div style='text-align:center' class='z-muted'>{pos + 1} of {len(order)}</div>", unsafe_allow_html=True)
if h[4].button("›", disabled=pos >= len(order) - 1, help="Next invoice"):
    st.switch_page(st.session_state.pages["review"], query_params={"id": str(order[pos + 1])})

src = "sample history (values known, no AI)" if inv["source"] == "seed" else "uploaded"
st.markdown(f"<h1 style='margin:2px 0 0'>{html.escape(name)}</h1>"
            f"<div class='z-sub' style='margin-top:2px'><b style='color:#0F1B33'>{html.escape(inv['vendor_name'] or 'Unknown vendor')}</b> · "
            f"{inr(inv['total'], decimals=0) if inv['total'] is not None else '—'} · invoice date {inv['invoice_date'] or '—'}"
            f"<span class='z-muted'> &nbsp;·&nbsp; {src}{' · policy v' + str(inv['policy_version']) if inv['policy_version'] else ''}</span></div>",
            unsafe_allow_html=True)

left, right = st.columns([1, 1.15], gap="large")

# ---------------- left (sticky): the original document
with left:
    with st.container(key="pdfpane"):
        data = (db.ROOT / inv["file_path"]).read_bytes()
        doc = pymupdf.open(stream=data, filetype="pdf")
        z = st.session_state.setdefault(f"zoom_{iid}", 1.0)
        pg = st.session_state.setdefault(f"page_{iid}", 0)
        tb = st.columns([0.7, 1.1, 0.7, 0.7, 0.7, 2.3], vertical_alignment="center")
        if tb[0].button("‹", key="pp", disabled=pg == 0, help="Previous page"):
            st.session_state[f"page_{iid}"] -= 1
            st.rerun()
        tb[1].markdown(f"<div style='text-align:center' class='z-muted'>page {pg + 1}/{doc.page_count}</div>", unsafe_allow_html=True)
        if tb[2].button("›", key="np", disabled=pg >= doc.page_count - 1, help="Next page"):
            st.session_state[f"page_{iid}"] += 1
            st.rerun()
        if tb[3].button("−", key="zo", disabled=z <= 0.6, help="Zoom out"):
            st.session_state[f"zoom_{iid}"] = round(z - 0.25, 2)
            st.rerun()
        if tb[4].button("+", key="zi", disabled=z >= 2.5, help="Zoom in"):
            st.session_state[f"zoom_{iid}"] = round(z + 0.25, 2)
            st.rerun()
        tb[5].download_button("Download", data, file_name=inv["filename"] or "invoice.pdf", mime="application/pdf",
                              icon=":material/download:", use_container_width=True)
        png = doc[pg].get_pixmap(dpi=int(110 * z)).tobytes("png")
        with st.container(height=700, border=True):
            st.image(png, use_container_width=z <= 1.0)
        st.markdown(f"<div class='z-muted'>Zoom {int(z * 100)}% · {'original scan' if inv['is_scanned'] else 'original PDF'}</div>", unsafe_allow_html=True)

# ---------------- right: result → your decision → tabs
GROUP = {"Document": "Document", "Duplicate": "Document", "Vendor": "Vendor & bank", "Purchase order": "Order & goods", "Policy": "Policy"}
NOT_SHOWN = "not shown on the invoice"


def plain(f):
    """A plain-language comparison line (no 'Expected / Found')."""
    e, a = f["expected"], f["actual"]
    if not (e or a):
        return ""
    a_ = a or NOT_SHOWN
    c = f["check_id"]
    if c == "BANK":
        return f"The invoice lists {a_}; our records have {e}."
    if c == "TAX_ID":
        return f"GSTIN on the invoice: {a_}; our records: {e}."
    if c == "VENDOR":
        return f"Name on the invoice: “{a_}”; our vendor record: {e}."
    if c == "PO_MATCH":
        return f"PO number on the invoice: {a_}; matched to: {e}."
    if c == "AUTO_LIMIT":
        return f"Invoice total {a_}; limit {e.replace('≤ ', '')}."
    if c == "PO_BALANCE":
        return f"After this invoice the PO would be billed {a_}; the most it allows is {e.replace('≤ ', '')}."
    if c == "DUPLICATE":
        return f"Invoice number: {a_}."
    if c == "DOC_TYPE":
        return f"This document is a {a_.lower()}."
    return f"On the invoice: {a_}; our records: {e or '—'}."


def check_html(f, with_cmp=True):
    cmp = plain(f) if with_cmp else ""
    return (f"<div class='z-check'><div class='ic'>{ui.ICON[f['result']]}</div><div><div class='nm'>{html.escape(f['details'].get('label', f['check_id']))}</div>"
            f"<div class='ms'>{html.escape(f['message'])}</div>" + (f"<div class='cmp'>{html.escape(cmp)}</div>" if cmp else "") + "</div></div>")


with right:
    ui.verdict(inv, helper.next_step(conn, iid))
    if inv["run_state"] != "DONE":
        st.stop()

    # ---- your decision, right under the result
    with st.container(key="card_decision"):
        st.markdown("**Your decision**")
        acts = decision.allowed_actions(inv)
        if not acts:
            if inv["status"] == "REJECTED" and inv["decided_by"] == "system":
                st.markdown("<span class='z-muted'>No action available: the rules blocked this invoice (for example a duplicate or a blocked vendor), "
                            "so it can't be approved with a click.</span>", unsafe_allow_html=True)
            else:
                note = q.reviewer_note(conn, iid)
                who = f" by {note['actor']} on {datetime.fromtimestamp(note['ts']):%d %b %H:%M}" if note else ""
                st.markdown(f"<span class='z-muted'>Already decided{who}. See the Audit Trail for the reason.</span>", unsafe_allow_html=True)
        else:
            labels = {"approve": "✅ Approve", "reject": "⛔ Reject"}
            act = st.segmented_control("Action", [a for a in ("approve", "reject") if a in acts], format_func=lambda a: labels[a],
                                       key=f"act_{iid}", label_visibility="collapsed")
            if "approve" not in acts:
                st.markdown("<span class='z-muted'>Approve isn't offered because this invoice is already <b>Ready to Pay</b>. "
                            "You can still pull it back with Reject.</span>", unsafe_allow_html=True)
            reason = None
            if act:
                if act == "approve" and "BANK_CHANGED" in (inv["reason_codes"] or ""):
                    st.warning("The bank account differs from our records. Only approve after calling the vendor on the number **on file**.", icon="📞")
                OTHER = "Other (type below)"
                pick = st.selectbox("Reason", decision.REVIEW_REASONS[act] + [OTHER], index=None, placeholder="Choose a reason…", key=f"why_{iid}_{act}")
                note_txt = st.text_input("Reason (required)" if pick == OTHER else "Add a note (optional)", key=f"note_{iid}_{act}",
                                         placeholder="e.g. confirmed with Ravi in procurement")
                if pick == OTHER:
                    reason = note_txt.strip() or None
                elif pick:
                    reason = pick + (f" - {note_txt.strip()}" if note_txt.strip() else "")
                eff = "**Ready to Pay** (PO amount committed)" if act == "approve" else "**Blocked** (PO amount released)"
                st.caption(f"On submit, this invoice becomes {eff} and your reason is saved in the audit trail.")
            if st.button("Submit decision", type="primary", icon=":material/send:", disabled=not (act and reason), key=f"submit_{iid}"):
                try:
                    new = decision.reviewer_action(conn, iid, act, reason)
                    for k in list(st.session_state.keys()):
                        if k.startswith((f"act_{iid}", f"why_{iid}", f"note_{iid}")):
                            del st.session_state[k]
                    st.toast(f"Saved: {LABEL[new]}. Recorded in the audit trail.", icon="✅")
                    st.rerun()
                except (ValueError, PermissionError) as e:
                    st.error(str(e))

    fs = q.findings(conn, iid)
    tabs = st.tabs(["Checks", "Details & Matches", "Email Draft", "Audit Trail"])

    # ---- Checks: problems first; passed folded; not-applicable as a muted line
    with tabs[0]:
        bad = sorted([f for f in fs if f["result"] in ("WARN", "FAIL")], key=lambda f: f["result"] != "FAIL")
        if bad:
            st.markdown(f"**Needs your attention ({len(bad)})**")
            st.markdown("".join(check_html(f) for f in bad), unsafe_allow_html=True)
        else:
            st.markdown("✅ **Nothing needs attention.** Every check passed.")
        passed = [f for f in fs if f["result"] == "PASS"]
        with st.expander(f"Passed ({len(passed)})"):
            for g in ["Document", "Vendor & bank", "Order & goods", "Policy"]:
                items = [f for f in passed if GROUP.get(f["check_group"]) == g]
                if items:
                    st.markdown(f"<div class='z-muted' style='margin-top:6px;text-transform:uppercase;letter-spacing:.06em;font-size:.75rem'>{g}</div>"
                                + "".join(check_html(f, with_cmp=False) for f in items), unsafe_allow_html=True)
        na = [f for f in fs if f["result"] == "NA"]
        if na:
            st.markdown("".join(f"<div class='z-na'>➖ <b>{html.escape(f['details'].get('label', f['check_id']))}</b> - not applicable: "
                                f"{html.escape(f['message'])}</div>" for f in na), unsafe_allow_html=True)
        st.caption("✅ passed · ⚠️ needs attention · ⛔ blocks payment · ➖ not applicable")
        with st.expander("Technical details"):
            st.dataframe([{"check": f["check_id"], "result": f["result"], "code": f["reason_code"], "message": f["message"],
                           "expected": f["expected"], "found": f["actual"], "policy": f["policy_version"]} for f in fs],
                         hide_index=True, use_container_width=True)

    # ---- Details & Matches: what was read (with its source), vendor, PO money, lines, receipts
    with tabs[1]:
        st.markdown("##### What we read from the invoice")
        how = {"TEXT": "✅ found in the PDF text", "OCR": "✅ found in the OCR text", "NONE": "⚠️ not verified - check the PDF"}
        ev = q.evidence(conn, iid)
        st.dataframe([{"Field": e["field"].replace("_", " ").capitalize(),
                       "Value": mask_account(e["value"]) if e["field"] == "bank_account" else e["value"],
                       "Where it came from": ((e["snippet"] or NOT_SHOWN).replace(e["value"], mask_account(e["value"])) if e["field"] == "bank_account" else (e["snippet"] or NOT_SHOWN)),
                       "Check": how[e["verification"]]} for e in ev], hide_index=True, use_container_width=True)
        st.dataframe([{"Item": l["description"], "Qty": l["quantity"], "Rate (₹)": l["unit_price"], "Amount (₹)": l["amount"]}
                      for l in q.lines(conn, iid)], hide_index=True, use_container_width=True)
        st.markdown(f"<span class='z-muted'>Subtotal {inr(inv['subtotal'])} · Tax {inr(inv['tax'])} · Total {inr(inv['total'])}</span>", unsafe_allow_html=True)
        meta = json.loads(inv["extraction_meta"] or "{}")
        reads = meta.get("reads", [])
        if reads:
            st.markdown("<span class='z-muted'>Read by " + ", then ".join(f"{r.get('model')}{' (saved answer)' if r.get('cached') else ''}" for r in reads)
                        + (f" · re-read because: {meta['retry_reason'].lower()}" if meta.get("retry_reason") else "") + "</span>", unsafe_allow_html=True)
        if meta.get("disagreements"):
            st.warning("The two reads disagreed on these values:")
            st.dataframe(meta["disagreements"], hide_index=True)

        st.markdown("##### Vendor record")
        v = q.vendor(conn, inv["vendor_id"])
        if v:
            st.markdown(f"**{v['name']}** · status **{v['status'].lower()}**  \nGSTIN {v['gstin']} · bank {mask_account(v['bank_account'])} · IFSC {v['ifsc']}  \n"
                        f"<span class='z-muted'>{v['email']} · {v['address']}</span>", unsafe_allow_html=True)
        else:
            st.markdown("<span class='z-muted'>Not matched to an approved vendor.</span>", unsafe_allow_html=True)

        st.markdown("##### Purchase order")
        po = q.po_detail(conn, inv["po_number"])
        if po:
            st.markdown(f"**{po['po_number']}** · {po['po_type'].lower()} · {po['status'].lower()} · valid until {po['valid_until']} · "
                        + ("PO number taken from the invoice" if inv["po_match_type"] == "EXPLICIT" else "⚠️ **suggested match - a person must confirm it**"))
            m = st.columns(4)
            m[0].metric("PO value", inr(po["total_amount"], decimals=0))
            m[1].metric("Approved", inr(po["committed"], decimals=0))
            m[2].metric("On hold", inr(po["reserved"], decimals=0))
            m[3].metric("Left", inr(po["remaining"], decimals=0))
            rows3 = []
            for l in q.lines(conn, iid):
                pl = next((x for x in po["lines"] if x["line_no"] == l["po_line_no"]), None)
                rows3.append({"Invoice item": l["description"], "PO item": pl["description"] if pl else "not on the PO",
                              "Ordered": pl["quantity"] if pl else None,
                              "Received": (pl["received"] if po["po_type"] == "GOODS" else None) if pl else None,
                              "Billed": l["quantity"], "PO rate": pl["unit_price"] if pl else None, "Invoice rate": l["unit_price"]})
            st.markdown("**Line by line** <span class='z-muted'>" + ("(ordered · received · billed)" if po["po_type"] == "GOODS" else "(service: no goods receipt, invoice vs PO)") + "</span>",
                        unsafe_allow_html=True)
            st.dataframe(rows3, hide_index=True, use_container_width=True)
            st.markdown("**Every invoice on this PO**")
            st.dataframe([{"Invoice": x["invoice_number"], "Date": x["invoice_date"], "Amount before tax": x["amount"],
                           "PO money": {"COMMITTED": "approved", "RESERVED": "on hold", "RELEASED": "released"}[x["state"]],
                           "Status": LABEL.get(x["status"], "")} for x in po["invoices"]], hide_index=True, use_container_width=True)
            if po["receipts"]:
                st.markdown("**Goods received**")
                st.dataframe([{"Receipt": r["grn_number"], "PO line": r["line_no"], "Received on": r["received_date"], "Qty": r["quantity_received"]}
                              for r in po["receipts"]], hide_index=True, use_container_width=True)
        else:
            st.markdown("<span class='z-muted'>No purchase order matched.</span>", unsafe_allow_html=True)
        cands = next((f["details"].get("candidates") for f in fs if f["check_id"] == "PO_MATCH" and f["details"].get("candidates")), None)
        if cands:
            st.markdown("**Purchase orders considered** <span class='z-muted'>(score = 0.5 × items + 0.35 × amount + 0.15 × dates)</span>", unsafe_allow_html=True)
            st.dataframe(cands, hide_index=True)

    # ---- Email draft
    with tabs[2]:
        if inv["email_draft"]:
            e = json.loads(inv["email_draft"])
            st.markdown(f"**To:** {e['to']}  \n**Subject:** {e['subject']}")
            st.code(e["body"], language=None, wrap_lines=True)
            st.caption("Draft only - copy it with the icon. Nothing is sent automatically, and it always goes to the address on file, never one from the invoice.")
        else:
            st.info("No vendor email needed for this invoice.")
        if inv["explanation"]:
            st.markdown("**Summary for the AP team**")
            st.markdown(f"<div class='z-card'>{html.escape(inv['explanation'])}</div>", unsafe_allow_html=True)

    # ---- Audit trail, in words
    with tabs[3]:
        WORDS = {"UPLOADED": "Invoice uploaded", "DECIDED": "Rules decided", "EXPLANATION_WRITTEN": "Explanation written",
                 "REVIEWER_APPROVE": "Approved by a person", "REVIEWER_REJECT": "Rejected by a person", "PO_RESERVED": "PO amount put on hold",
                 "PO_COMMITTED": "PO amount committed", "PO_RELEASED": "PO amount released", "RUN_FAILED": "Processing failed",
                 "RETRY_REQUESTED": "Retry requested", "SAME_FILE_UPLOADED_AGAIN": "Same file uploaded again"}
        rows_ = []
        for a in q.audit(conn, iid):
            d = a["details"]
            extra = d.get("reason") or (f"{d.get('label')} · policy v{d.get('policy_version')}" if a["action"] == "DECIDED" else "") \
                or (f"{d.get('po')} · {inr(d.get('amount'), decimals=0)}" if a["action"].startswith("PO_") else "") or d.get("error") or d.get("filename") or ""
            rows_.append(f"<div class='z-check'><div class='ic'>•</div><div><div class='nm'>{html.escape(WORDS.get(a['action'], a['action'].replace('_', ' ').title()))}"
                         f" <span class='z-muted' style='font-weight:400'>· {html.escape(a['actor'])} · {datetime.fromtimestamp(a['ts']):%d %b %Y, %H:%M:%S}</span></div>"
                         f"<div class='ms'>{html.escape(str(extra))}</div></div></div>")
        st.markdown("".join(rows_), unsafe_allow_html=True)
        st.caption("Append-only: the database refuses edits and deletions of these entries.")
