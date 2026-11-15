import streamlit as st

from app import ui
from core import llm, policy



def render():
    conn = ui.conn()
    ver, pol = policy.active(conn)
    st.caption("Key assumptions and scope for this prototype.")
    st.caption("Last updated: 14 Nov 2026")

    m = llm.models()
    cards = {
        "🗄️ Data": [
            "This is a prototype using **invented sample data** for one company (Acme Retail India): 9 vendors, 15 POs, goods receipts.",
            "Vendor, PO and receipt records are company-specific; in production they come from the ERP.",
            "Invoice history is pre-processed from known values (no AI). Uploaded invoices are read by AI.",
            "PDFs up to 10 MB and 10 pages, text or scanned. One invoice per file.",
            "Currency: INR. GST rates 0/5/12/18/28%. **PO and price checks compare amounts before tax**; the auto-approve limit uses the **invoice total including tax** (the amount actually paid).",
            "Dates are read as **day/month/year** (Indian format). An ambiguous date like 04/01 is taken as 4 January.",
            "GSTINs are invented, so only their **format** is checked (15 characters, state code, PAN pattern), not the official checksum.",
        ],
        "⚖️ Decisions": [
            "Outcomes: **Ready to Pay**, **Needs Attention**, **Rejected**. The most severe finding wins; all reasons are listed.",
            "AI reads the invoice and writes explanations. **Python rules make every decision**; the AI never sees or sets a status.",
            f"Current policy v{ver}: price tolerance {pol['tolerance_pct']:g}% (max ₹{pol['tolerance_cap']:,.0f}/line), rejected above "
            f"{pol['reject_variance_pct']:g}%, auto-approve limit ₹{pol['auto_approve_limit']:,.0f}.",
            "An inferred PO, an unverified key value or a bank change is never auto-approved.",
            "A person can approve or reject a Needs Attention invoice (reason required). A system-Rejected invoice can't be approved by a click.",
            "PO money: Needs Attention **reserves** the amount, approval **commits** it, rejection **releases** it. The next invoice on the PO sees "
            "what's left after both. Changing the policy does not touch existing reservations; only newly processed invoices use the new rules.",
            "A possible duplicate needs the same vendor and amount **plus** a similar invoice number or a date within "
            f"{pol['fuzzy_dup_days']} days, so normal recurring bills (rent, monthly freight) aren't flagged.",
            "No login in the prototype: every action is recorded as \"Demo Reviewer\".",
        ],
        "🚧 Limits": [
            "The system never pays or sends email. Vendor emails are drafts to copy.",
            "No model confidence scores: each value is shown as verified in the text, verified in OCR, or not verified.",
            "Hidden-text detection works on text PDFs only (a scan has no text layer to hide text in). It flags text the same colour as its background, under 3 pt, or off the page; tested on this project's PDFs, not on a large set of real ones.",
            "If the server has no OCR engine, scans are still read by the AI but every value is marked 'not verified', so they always go to a person.",
            "Money is handled as rupees rounded to 2 decimals, with small tolerances in comparisons; integer paise would be the production choice.",
            f"AI: Google Gemini free tier ({m['primary']}, second read {m['retry']}). Free-tier rate limits apply, and Google may use "
            "free-tier inputs to improve its products - fine for sample data, not for real invoices.",
            "Phone verification of bank changes is a manual step; recording it in the app is planned, not built.",
            "What-if analysis re-checks each invoice against invoices processed before it, using today's PO money state.",
        ],
    }
    cols = st.columns(3)
    for c, (title, items) in zip(cols, cards.items()):
        with c.container(border=True, height=560):
            st.markdown(f"### {title}")
            for i in items:
                st.markdown(f"- {i}")
    st.write("")
    with st.container(border=True):
        c = st.columns([4, 1])
        c[0].markdown("ℹ️ **Need more details?** The FAQs on the home page explain what is checked and how.")
        if c[1].button("View FAQs →", use_container_width=True):
            st.switch_page(st.session_state.pages["home"])

