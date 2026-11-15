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

fs = q.findings(conn, iid)
bad = sorted([f for f in fs if f["result"] in ("WARN", "FAIL")], key=lambda f: f["result"] != "FAIL")
src = "Sample history" if inv["source"] == "seed" else "Uploaded"

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



# ================================================================ header: back · title · facts | Ask · ‹ n of N ›
h = st.columns([0.42, 5.2, 1.75, 0.38, 0.62, 0.38], vertical_alignment="center", gap="small")
if h[0].button("", icon=":material/arrow_back:", key="back", help="Back to History"):
    st.switch_page(st.session_state.pages["history"])
_d = inv["invoice_date"] or ""
nice_date = f"{int(_d[8:10])} {['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][int(_d[5:7]) - 1]} {_d[:4]}" if len(_d) == 10 else "—"
h[1].markdown(f"<div class='rv-title'>Review Invoice</div><div class='z-sub' style='margin:2px 0 0'><b style='color:#0F172A'>{html.escape(name)}</b> · "
              f"{html.escape(inv['vendor_name'] or 'Unknown vendor')} · {inr(inv['total'], decimals=0) if inv['total'] is not None else '—'} · "
              f"{nice_date} · {src}<span class='z-muted'>"
              f"{' · policy v' + str(inv['policy_version']) if inv['policy_version'] else ''}</span></div>", unsafe_allow_html=True)
with h[2].popover("Ask about this invoice", icon=":material/chat:", use_container_width=True):
    helper_panel.render(conn, iid, "rv", height=300)
if h[3].button("‹", disabled=pos == 0, help="Previous invoice", use_container_width=True):
    st.switch_page(st.session_state.pages["review"], query_params={"id": str(order[pos - 1])})
h[4].markdown(f"<div style='text-align:center;white-space:nowrap' class='z-muted'>{pos + 1} of {len(order)}</div>", unsafe_allow_html=True)
if h[5].button("›", disabled=pos >= len(order) - 1, help="Next invoice", use_container_width=True):
    st.switch_page(st.session_state.pages["review"], query_params={"id": str(order[pos + 1])})
st.write("")

left, right = st.columns([1, 1.05], gap="large")

# ================================================================ left: the document in one card
with left:
    with st.container(key="pdfpane"):
        data = (db.ROOT / inv["file_path"]).read_bytes()
        doc = pymupdf.open(stream=data, filetype="pdf")
        z = st.session_state.setdefault(f"zoom_{iid}", 1.0)
        pg = st.session_state.setdefault(f"page_{iid}", 0)
        bar = st.columns([4.2, 0.5, 0.5, 0.5, 0.5, 0.5], vertical_alignment="center", gap="small")
        bar[0].markdown(f"<div class='rv-file'><span class='doc'>{ui.PDF_SVG}</span><div style='min-width:0'><b>{html.escape(inv['filename'] or name)}</b>"
                        f"<div class='z-muted'>{'scan' if inv['is_scanned'] else 'PDF'} · page {pg + 1} of {doc.page_count} · {int(z * 100)}%</div></div></div>",
                        unsafe_allow_html=True)
        if bar[1].button("", icon=":material/chevron_left:", key="pp", disabled=pg == 0, help="Previous page"):
            st.session_state[f"page_{iid}"] -= 1
            st.rerun()
        if bar[2].button("", icon=":material/chevron_right:", key="np", disabled=pg >= doc.page_count - 1, help="Next page"):
            st.session_state[f"page_{iid}"] += 1
            st.rerun()
        if bar[3].button("", icon=":material/zoom_out:", key="zo", disabled=z <= 0.6, help="Zoom out"):
            st.session_state[f"zoom_{iid}"] = round(z - 0.25, 2)
            st.rerun()
        if bar[4].button("", icon=":material/zoom_in:", key="zi", disabled=z >= 2.5, help="Zoom in"):
            st.session_state[f"zoom_{iid}"] = round(z + 0.25, 2)
            st.rerun()
        bar[5].download_button("", data, file_name=inv["filename"] or "invoice.pdf", mime="application/pdf", icon=":material/download:",
                               key="dl", help="Download the original")
        png = doc[pg].get_pixmap(dpi=int(110 * z)).tobytes("png")
        with st.container(height=780, border=False, key="pdfview"):
            st.image(png, use_container_width=z <= 1.0)

# ================================================================ right: status · review · email · actions
STATUS_ICON = {"APPROVED": "✓", "FLAGGED": "!", "REJECTED": "✕"}


def copy_button(text, key):
    """Copies text to the clipboard (falls back to execCommand inside the component frame)."""
    import streamlit.components.v1 as components
    components.html(f"""<style>html,body{{margin:0;padding:0;overflow:hidden}}</style><button id='b' style="width:100%;height:44px;margin:0;border-radius:10px;border:1.5px solid #C9D7FB;background:#fff;color:#2449C9;
      font:600 15px 'Source Sans Pro',sans-serif;cursor:pointer">⧉  Copy Draft</button><script>
      const t = {json.dumps(text)}; const b = document.getElementById('b');
      b.onclick = async () => {{ try {{ await navigator.clipboard.writeText(t); }} catch (e) {{
        const a = document.createElement('textarea'); a.value = t; document.body.appendChild(a); a.select(); document.execCommand('copy'); a.remove(); }}
        b.innerText = '✓ Copied'; setTimeout(() => b.innerText = '⧉  Copy Draft', 1800); }};</script>""", height=46)


with right:
    if inv["run_state"] != "DONE":
        ui.verdict(inv)
        st.stop()
    note = q.reviewer_note(conn, iid)
    acts = decision.allowed_actions(inv)
    s_ = inv["status"]
    sub = (f"Decided by {note['actor']} on {datetime.fromtimestamp(note['ts']):%d %b %Y, %H:%M}." if note and inv["decided_by"] == "reviewer"
           else helper.next_step(conn, iid) or "")
    st.markdown(f"<div class='rv-banner {s_}'><div class='ic'>{STATUS_ICON[s_]}</div><div><div class='t'>{LABEL[s_]}</div>"
                f"<div class='s'>{html.escape(sub)}</div></div><div class='amt'>{inr(inv['total'], decimals=0)}</div></div>", unsafe_allow_html=True)

    # ---- Review
    found = [short_text(f) for f in bad]
    with st.container(key="card_review"):
        st.markdown("<div class='rv-h'><svg viewBox='0 0 24 24' width='24' height='24' fill='none' stroke='#2F5BEA' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><path d='M4 20h4L19 9l-4-4L4 16v4z'/><path d='M13.5 6.5l4 4'/></svg><span>Review</span></div>", unsafe_allow_html=True)
        choice, reason = None, None
        if not acts:
            st.markdown("<div class='rv-found'>" + ("".join(f"<div>{'⛔' if f['result'] == 'FAIL' else '⚠️'} {html.escape(short_text(f))}</div>" for f in bad)
                        if bad else "<div>✅ Every check passed.</div>") + "</div>", unsafe_allow_html=True)
            if note and inv["decided_by"] == "reviewer":
                st.markdown(f"<div class='rv-note'><b>{'Approved' if note['action'] == 'REVIEWER_APPROVE' else 'Rejected'} by {html.escape(note['actor'])}</b> - "
                            f"{html.escape(note['details'].get('reason', ''))}</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='rv-note'>Blocked by the rules, so it can't be approved with a click.</div>", unsafe_allow_html=True)
        else:
            label = ("What we found - edit it into your note (saved with your decision)" if found
                     else "Your note (saved with your decision)")
            st.markdown(f"<div class='z-muted' style='margin:6px 0 2px'>{label}</div>", unsafe_allow_html=True)
            reason = st.text_area("Your note", value=" ".join(found) if found else "", height=90, key=f"txt_{iid}", label_visibility="collapsed",
                                  placeholder=("Why are you pulling this invoice back?" if s_ == "APPROVED"
                                               else "Why are you approving or blocking this invoice?")).strip()
            # the three statuses, as in the design; the current status is pre-selected
            opts = ["FLAGGED", "APPROVED", "REJECTED"]
            choice = st.radio("Decision", opts, index=opts.index(s_) if s_ in opts else None,
                              format_func=lambda x: {"FLAGGED": "Needs Attention", "APPROVED": "Ready to Pay", "REJECTED": "Blocked"}[x],
                              horizontal=True, key=f"st_{iid}", label_visibility="collapsed")
            if s_ == "APPROVED":
                st.markdown("<span class='z-muted'>Every check passed, so this invoice is already <b>Ready to Pay</b>. "
                            "Choose <b>Blocked</b> only if you need to pull it back.</span>", unsafe_allow_html=True)
            elif choice == "FLAGGED":
                st.markdown("<span class='z-muted'><b>Needs Attention</b> keeps the invoice on hold. Saving stores your note; "
                            "use the email below to ask the vendor to fix the issue.</span>", unsafe_allow_html=True)
            for n_ in q.reviewer_notes(conn, iid):
                st.markdown(f"<div class='rv-note' style='margin-top:8px'>📝 <b>Note by {html.escape(n_['actor'])}</b> "
                            f"<span class='z-muted'>· {datetime.fromtimestamp(n_['ts']):%d %b, %H:%M}</span><br>{html.escape(n_['details'].get('reason', ''))}</div>",
                            unsafe_allow_html=True)
            if choice == "APPROVED" and "BANK_CHANGED" in (inv["reason_codes"] or ""):
                st.warning("The bank account differs from our records. Only mark Ready to Pay after calling the vendor on the number **on file**.", icon="📞")

    # ---- Email to vendor (template, follows the chosen status; nothing is sent)
    if note and inv["decided_by"] == "reviewer":
        e_action, e_reason = ("approve" if note["action"] == "REVIEWER_APPROVE" else "reject"), note["details"].get("reason", "")
    elif not acts:
        e_action, e_reason = "reject", inv["primary_reason"] or ""
    elif choice:
        e_action = {"APPROVED": "approve", "REJECTED": "reject", "FLAGGED": "hold"}[choice]
        e_reason = reason or inv["primary_reason"] or ""
    else:
        e_action = None
    if e_action is None:
        with st.container(key="card_email"):
            st.markdown("<div class='rv-h'><svg viewBox='0 0 24 24' width='26' height='26' fill='none' stroke='#2F5BEA' stroke-width='1.9' stroke-linejoin='round'><rect x='3' y='5' width='18' height='14' rx='2.5'/><path d='M3.5 6.5l8.5 6.5 8.5-6.5'/></svg><span>Email to Vendor</span></div><div class='z-muted' style='margin-top:6px'>Pick <b>Ready to Pay</b> or <b>Blocked</b> above "
                        "and a ready-to-send email for the vendor appears here.</div>", unsafe_allow_html=True)
    else:
        e = explain.reviewer_email(conn, iid, e_action, e_reason)
    if e_action:
        with st.container(key="card_email"):
            hh = st.columns([3, 1.2], vertical_alignment="center")
            hh[0].markdown("<div class='rv-h'><svg viewBox='0 0 24 24' width='26' height='26' fill='none' stroke='#2F5BEA' stroke-width='1.9' stroke-linejoin='round'><rect x='3' y='5' width='18' height='14' rx='2.5'/><path d='M3.5 6.5l8.5 6.5 8.5-6.5'/></svg><span>Email to Vendor</span><span class='z-draft2'>Draft · not sent</span></div>", unsafe_allow_html=True)
            ek = f"edit_{iid}"
            if hh[1].button("Done" if st.session_state.get(ek) else "Edit Draft", icon=":material/edit:", key=f"ebtn_{iid}", use_container_width=True):
                st.session_state[ek] = not st.session_state.get(ek)
                st.rerun()
            st.markdown(f"<div class='rv-mail'><div class='f'><span>To</span>{html.escape(e['to'])}</div>"
                        f"<div class='f'><span>Subject</span><b>{html.escape(e['subject'])}</b></div></div>", unsafe_allow_html=True)
            if st.session_state.get(ek):
                body = st.text_area("Email text", value=e["body"], height=260, key=f"body_{iid}_{e_action}", label_visibility="collapsed")
            else:
                body = st.session_state.get(f"body_{iid}_{e_action}", e["body"])
                st.markdown("<div class='rv-body'>" + html.escape(body).replace("\n", "<br>") + "</div>", unsafe_allow_html=True)
            from urllib.parse import quote
            bb = st.columns([1, 1.25], gap="small")
            with bb[0]:
                copy_button(f"To: {e['to']}\nSubject: {e['subject']}\n\n{body}", f"cp_{iid}")
            if "@" in e["to"]:
                gmail = (f"https://mail.google.com/mail/?view=cm&fs=1&to={quote(e['to'])}&su={quote(e['subject'])}&body={quote(body)}")
                bb[1].link_button("Open in Gmail", gmail, type="primary", icon=":material/send:", use_container_width=True)
                st.markdown(f"<div class='z-muted' style='text-align:right;margin-top:-4px'>or <a href='mailto:{e['to']}?subject={quote(e['subject'])}"
                            f"&body={quote(body)}'>open in your default mail app</a></div>", unsafe_allow_html=True)

    # ---- Actions
    if acts:
        with st.container(key="card_actions"):
            changed = choice is not None and choice != s_
            allowed = (not changed) or {"APPROVED": "approve", "REJECTED": "reject"}.get(choice) in acts
            if not allowed:
                hint = "A Ready to Pay invoice can't go back to Needs Attention - choose <b>Blocked</b> to pull it back."
            elif changed:
                hint = f"Saving marks it <b>{ {'APPROVED': 'Ready to Pay', 'REJECTED': 'Blocked'}[choice] }</b> and stores your note in the audit trail."
            else:
                hint = "Status stays the same - saving stores your note in the audit trail."
            a = st.columns([2.2, 1, 1.3], vertical_alignment="center")
            a[0].markdown(f"<span class='z-muted'>{hint}</span>", unsafe_allow_html=True)
            if a[1].button("Cancel", use_container_width=True):
                st.switch_page(st.session_state.pages["history"])
            if a[2].button("Save review", type="primary", icon=":material/check:", use_container_width=True,
                           disabled=not (choice and allowed and reason and len(reason) >= 5)):
                try:
                    if changed:
                        new = decision.reviewer_action(conn, iid, "approve" if choice == "APPROVED" else "reject", reason)
                        msg = f"Saved: {LABEL[new]}. Recorded in the audit trail."
                    else:
                        decision.reviewer_note_only(conn, iid, reason)
                        msg = "Note saved. Status unchanged."
                    for k in list(st.session_state.keys()):
                        if isinstance(k, str) and k.startswith((f"txt_{iid}", f"st_{iid}", f"edit_{iid}", f"body_{iid}")):
                            del st.session_state[k]
                    st.toast(msg, icon="✅")
                    st.rerun()
                except (ValueError, PermissionError) as err:
                    st.error(str(err))
