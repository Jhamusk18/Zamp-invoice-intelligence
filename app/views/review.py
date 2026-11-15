import html
import json
from datetime import datetime

import pymupdf
import streamlit as st

from app import helper_panel, ui
from core import db, decision, explain, helper, queries as q
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

if st.button(f"History  /  {name}", type="tertiary", icon=":material/arrow_back:"):
    st.switch_page(st.session_state.pages["history"])
src = "sample history (values known, no AI)" if inv["source"] == "seed" else "uploaded"
h = st.columns([4.6, 1.75, 0.38, 0.62, 0.38], vertical_alignment="center", gap="small")
h[0].markdown(f"<h1 style='margin:0'>{html.escape(name)}</h1>"
              f"<div class='z-sub' style='margin:4px 0 0'><b style='color:#0F172A'>{html.escape(inv['vendor_name'] or 'Unknown vendor')}</b> · "
              f"{inr(inv['total'], decimals=0) if inv['total'] is not None else '—'} · invoice date {inv['invoice_date'] or '—'}"
              f"<span class='z-muted'> &nbsp;·&nbsp; {src}{' · policy v' + str(inv['policy_version']) if inv['policy_version'] else ''}</span></div>",
              unsafe_allow_html=True)
with h[1].popover("Ask about this invoice", icon=":material/chat:", use_container_width=True):
    helper_panel.render(conn, iid, "rv", height=300)
if h[2].button("‹", disabled=pos == 0, help="Previous invoice", use_container_width=True):
    st.switch_page(st.session_state.pages["review"], query_params={"id": str(order[pos - 1])})
h[3].markdown(f"<div style='text-align:center;white-space:nowrap' class='z-muted'>{pos + 1} of {len(order)}</div>", unsafe_allow_html=True)
if h[4].button("›", disabled=pos >= len(order) - 1, help="Next invoice", use_container_width=True):
    st.switch_page(st.session_state.pages["review"], query_params={"id": str(order[pos + 1])})
st.write("")

left, right = st.columns([1, 1.15], gap="large")

# ---------------- left (sticky): the original document
with left:
    with st.container(key="pdfpane"):
        data = (db.ROOT / inv["file_path"]).read_bytes()
        doc = pymupdf.open(stream=data, filetype="pdf")
        z = st.session_state.setdefault(f"zoom_{iid}", 1.0)
        pg = st.session_state.setdefault(f"page_{iid}", 0)
        png = doc[pg].get_pixmap(dpi=int(110 * z)).tobytes("png")
        with st.container(height=800, border=True):
            st.image(png, use_container_width=z <= 1.0)
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
        if f["reason_code"] == "PO_INFERRED":
            best = (f["details"].get("candidates") or [{}])[0].get("po_number", "a suggested PO")
            return f"No PO number printed on the invoice; best match is {best}."
        if f["reason_code"] == "NO_PO":
            return "No PO number printed on the invoice, and no open PO of this vendor fits."
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

TITLES = {"DOC_TYPE": "Document type", "REQUIRED_FIELDS": "Required details", "EVIDENCE": "Values found in the PDF", "HIDDEN_TEXT": "Hidden text",
          "READS_AGREE": "Second read", "ARITHMETIC": "Amounts add up", "VENDOR": "Vendor", "TAX_ID": "GSTIN", "BANK": "Bank account",
          "DUPLICATE": "Duplicate", "PO_MATCH": "Purchase order", "PO_LINES": "Items vs order", "PO_BALANCE": "Order budget",
          "RECEIPT": "Goods received", "DATES": "Dates", "CURRENCY": "Currency", "AUTO_LIMIT": "Approval limit"}


def plain_title(f):
    return TITLES.get(f["check_id"], f["details"].get("label", f["check_id"]))


def _first(msg):
    import re
    t = msg.split(". ")[0].rstrip(".")
    return re.sub(r"\s*\((score|similarity|allowed|PO value|approved|paid)[^)]*\)", "", t) + "."


def short_text(f):
    """One plain sentence a non-technical reviewer can act on."""
    code, d = f["reason_code"], f["details"]
    if code == "BANK_CHANGED":
        return f"The invoice asks us to pay {f['actual']}, but our records have {f['expected']}. Call the vendor before paying."
    if code == "HIDDEN_TEXT":
        return "The PDF hides text that tries to get it approved. It was ignored, but treat this invoice as suspicious."
    if code == "PO_INFERRED":
        best = (d.get("candidates") or [{}])[0].get("po_number", "a likely order")
        return f"No PO number on the invoice. Best guess: {best} - please confirm."
    if code == "NO_PO":
        return "No PO number on the invoice, and no matching order was found."
    if code in ("LINE_NOT_ON_PO", "PRICE_VARIANCE", "LINE_MISMATCH", "PRICE_OVER_LIMIT", "QTY_OVER_PO"):
        bad = [x for x in d.get("lines", []) if x.get("result") != "PASS"]
        if bad:
            x = bad[0]
            note = x["note"].split(" (")[0].replace("vs PO", "vs the order").replace("not on the PO", "isn't on the order").replace("on the PO", "on the order")
            more = f" (+{len(bad) - 1} more)" if len(bad) > 1 else ""
            return f"{x['invoice_line']}: {note}{more}."
    if code == "QTY_EXCEEDS_RECEIPT":
        rows = [r for r in d.get("rows", []) if r["invoiced"] > r["received"] - r.get("billed_before", 0)]
        if rows:
            r = rows[0]
            return f"Billed {r['invoiced']:g}, but only {max(r['received'] - r.get('billed_before', 0), 0):g} received and not yet billed."
    if code == "DUPLICATE_EXACT":
        return f"We already have this invoice ({f['actual']} is the same as an earlier one). Don't pay it twice."
    if code == "OVER_AUTO_LIMIT":
        return f"{f['actual']} is above the {f['expected'].replace('≤ ', '')} limit, so a person must approve it."
    if code == "UNVERIFIED_FIELD":
        return "Some values couldn't be found in the PDF. Compare them with the document yourself."
    if code == "VENDOR_MATH_ERROR":
        return "The invoice's own numbers don't add up - ask the vendor for a corrected invoice."
    if code == "VENDOR_LOOKALIKE":
        return "The name looks like one of our vendors, but it's a different company. Possible impersonation."
    if code == "UNKNOWN_VENDOR":
        return "This vendor isn't on our approved list."
    if code == "VENDOR_BLOCKED":
        return "This vendor is blocked in our records - don't pay."
    if code == "NOT_AN_INVOICE":
        return "This is not an invoice (for example a quotation), so there's nothing to pay."
    return _first(f["message"])


def check_html(f, with_cmp=True):
    cmp = plain(f) if with_cmp else ""
    return (f"<div class='z-check'><div class='ic'>{ui.ICON[f['result']]}</div><div><div class='nm'>{html.escape(f['details'].get('label', f['check_id']))}</div>"
            f"<div class='ms'>{html.escape(f['message'])}</div>" + (f"<div class='cmp'>{html.escape(cmp)}</div>" if cmp else "") + "</div></div>")


def show_email(action, reason, folded=False):
    """Ready-to-copy vendor email for this decision (fixed template, no AI). Nothing is sent.
    folded=True (decision already made): a compact bar you click open."""
    from contextlib import nullcontext
    from urllib.parse import quote
    e = explain.reviewer_email(conn, iid, action, reason)
    outer = st.expander(f"✉️  Email to the vendor  ·  {e['subject']}  ·  ready to copy", expanded=False) if folded else nullcontext()
    with outer, st.container(key=f"mail_{action}"):
        st.markdown(f"<div class='z-mailhead'><span>✉️</span><b>Email to the vendor</b><span class='z-draft'>Draft · not sent</span></div>"
                    f"<div class='z-mailfield'><span>To</span><div>{html.escape(e['to'])} <i class='z-muted'>(address on file)</i></div></div>"
                    f"<div class='z-mailfield'><span>Subject</span><div><b>{html.escape(e['subject'])}</b></div></div>", unsafe_allow_html=True)
        st.code(e["body"], language=None, wrap_lines=True)
        c = st.columns([1.7, 3], vertical_alignment="center")
        if "@" in e["to"]:
            c[0].link_button("Open in email app", f"mailto:{e['to']}?subject={quote(e['subject'])}&body={quote(e['body'])}",
                             icon=":material/forward_to_inbox:", use_container_width=True)
        c[1].markdown("<span class='z-muted'>Copy with the icon on the text, or open it in your email app. Nothing is sent from here.</span>",
                      unsafe_allow_html=True)

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
                if note:
                    ok = note["action"] == "REVIEWER_APPROVE"
                    st.markdown(f"<div class='z-decided {'APPROVED' if ok else 'REJECTED'}'>"
                                f"<div class='top'><span class='z-pill {'APPROVED' if ok else 'REJECTED'}'><span class='dot'></span>{'Approved' if ok else 'Rejected'} by reviewer</span>"
                                f"<span class='z-muted'>{html.escape(note['actor'])} · {datetime.fromtimestamp(note['ts']):%d %b %Y, %H:%M}</span></div>"
                                f"<div class='why'>Reason: <b>{html.escape(note['details'].get('reason', ''))}</b></div></div>", unsafe_allow_html=True)
                else:
                    st.markdown("<span class='z-muted'>Already decided. See the Audit Trail.</span>", unsafe_allow_html=True)
                if note:
                    show_email("approve" if note["action"] == "REVIEWER_APPROVE" else "reject", note["details"].get("reason", ""), folded=True)
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
                if reason:
                    show_email(act, reason)
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
    tabs = st.tabs(["Checks", "Details & Matches", "Audit Trail"])

    # ---- Checks, for a non-technical reader: one short sentence per problem; everything else folded away
    with tabs[0]:
        bad = sorted([f for f in fs if f["result"] in ("WARN", "FAIL")], key=lambda f: f["result"] != "FAIL")
        if bad:
            st.markdown(f"<div class='z-sectitle'>{len(bad)} thing{'s' if len(bad) != 1 else ''} to look at</div>", unsafe_allow_html=True)
            st.markdown("".join(
                f"<div class='z-prob {'FAIL' if f['result'] == 'FAIL' else 'WARN'}'><div class='ic'>{'⛔' if f['result'] == 'FAIL' else '⚠️'}</div>"
                f"<div><div class='tt'>{html.escape(plain_title(f))}</div><div class='tx'>{html.escape(short_text(f))}</div></div></div>" for f in bad),
                unsafe_allow_html=True)
        else:
            st.markdown("<div class='z-prob OK'><div class='ic'>✅</div><div><div class='tt'>Nothing to look at</div>"
                        "<div class='tx'>Every check passed.</div></div></div>", unsafe_allow_html=True)
        passed = [f for f in fs if f["result"] == "PASS"]
        na = [f for f in fs if f["result"] == "NA"]
        with st.expander(f"✅ {len(passed)} checks passed" + (f" · {len(na)} not needed" if na else "")):
            st.markdown("<div class='z-chips'>" + "".join(f"<span class='z-chip ok' title='{html.escape(f['message'])}'>✓ {html.escape(plain_title(f))}</span>" for f in passed)
                        + "".join(f"<span class='z-chip na' title='{html.escape(f['message'])}'>– {html.escape(plain_title(f))}</span>" for f in na)
                        + "</div><div class='z-muted' style='margin-top:8px'>Hover a label to see what was checked. Grey = not needed for this invoice.</div>",
                        unsafe_allow_html=True)
        with st.expander("Technical details"):
            if inv["explanation"]:
                st.markdown(f"**{'Rules summary (written before the reviewer decided)' if inv['decided_by'] == 'reviewer' else 'Summary'}**  \n{inv['explanation']}")
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

    # ---- Audit trail, in words
    with tabs[2]:
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
