import streamlit as st

st.markdown("""<style>
.hero { border-radius: 24px; padding: 56px 52px 50px; margin: 8px 0 22px; color: #fff;
        background: radial-gradient(700px 360px at 85% 20%, rgba(96,165,250,.45), transparent 60%),
                    linear-gradient(135deg, #0B1B3A 0%, #12306E 60%, #1D4ED8 100%); position: relative; overflow: hidden; }
.hero .pill { display:inline-block; border:1px solid rgba(191,211,255,.6); color:#DCE7FF; border-radius:999px; padding:4px 12px; font-size:.8rem; }
.hero h1 { font-size: 3rem !important; line-height: 1.08; margin: 18px 0 14px; color: #fff !important; max-width: 640px; }
.hero h1, .hero h1 * { color: #fff !important; } .hero h1 .hl, .hero h1 .hl * { color: #93C5FD !important; }
.hero p { color: #C9D7F5; font-size: 1.08rem; max-width: 560px; }
.mock { position:absolute; right: 56px; top: 54px; width: 300px; background:#fff; border-radius:16px; padding:20px; color:#0F1B33;
        box-shadow: 0 30px 60px rgba(2,8,30,.45); transform: rotate(-3deg); }
.mock .bar { height:8px; background:#E3EBFA; border-radius:6px; margin:9px 0; }
.mock .ok { margin-top:12px; background:#E8F7EE; color:#15803D; border-radius:10px; padding:8px 10px; font-weight:700; font-size:.92rem; }
.mock .c { font-size:.86rem; margin:5px 0; }
@media (max-width: 1100px) { .mock { display:none; } }
.step { background:#fff; border:1px solid #DCE4F2; border-radius:16px; padding:20px; height:100%; }
.step .n { width:42px;height:42px;border-radius:12px;background:#EAF1FF;color:#2563EB;display:flex;align-items:center;justify-content:center;font-weight:800;margin-bottom:12px }
.step b { display:block; margin-bottom:6px; color:#0F1B33 } .step span { color:#5B6B86; font-size:.92rem; }
.ben { background:#0B1B3A; color:#fff; border-radius:16px; padding:20px; height:100%; }
.ben b { display:block; margin:6px 0 4px } .ben span { color:#B8C8EA; font-size:.9rem }
</style>""", unsafe_allow_html=True)

st.markdown("""<div class='hero'>
<span class='pill'>AI + rules for Accounts Payable</span>
<h1>Verify invoices, prevent errors, and <span class='hl'>pay with confidence.</span></h1>
<p>Zamp reads each vendor invoice, checks it against your vendors, purchase orders, goods received and approval rules,
and tells you clearly what can be paid, what needs a look, and what must be stopped.</p>
<div class='mock'><b style='font-size:1.15rem'>INVOICE</b><div class='bar' style='width:70%'></div><div class='bar'></div><div class='bar' style='width:55%'></div>
<div class='c'>✅ Vendor verified</div><div class='c'>✅ PO matched</div><div class='c'>✅ Amount within tolerance</div><div class='ok'>Ready to Pay</div>
<div style='font-size:.72rem;color:#8193B2;margin-top:8px'>Illustration, not a processed invoice</div></div>
</div>""", unsafe_allow_html=True)
b = st.columns([1.2, 1.2, 4])
if b[0].button("Verify an invoice", type="primary", icon=":material/upload_file:", use_container_width=True):
    st.switch_page(st.session_state.pages["upload"])
if b[1].button("See past results", icon=":material/history:", use_container_width=True):
    st.switch_page(st.session_state.pages["history"])

st.markdown("<h2 style='text-align:center;margin-top:44px'>How it works</h2><p style='text-align:center' class='z-muted'>From PDF to a clear decision in seconds.</p>",
            unsafe_allow_html=True)
cols = st.columns(4)
for c, (n, t, d) in zip(cols, [("1", "Upload", "Drop a PDF or a scanned invoice."),
                               ("2", "Read", "AI reads the invoice and quotes where each value came from, whatever the layout."),
                               ("3", "Check", "Python rules check vendor, bank, PO, prices, quantities received, duplicates and policy."),
                               ("4", "Decide", "Ready to Pay, Needs Attention or Blocked - with reasons, evidence and a vendor email draft.")]):
    c.markdown(f"<div class='step'><div class='n'>{n}</div><b>{t}</b><span>{d}</span></div>", unsafe_allow_html=True)

st.write("")
bc = st.columns(3)
for c, (i, t, d) in zip(bc, [("⚡", "Faster processing", "Routine invoices that pass every check need no one's time."),
                             ("🛡️", "Lower financial risk", "Catches overbilling, duplicates, bank-account changes and hidden instructions."),
                             ("🧱", "Built for your business", "Uses your vendor master, POs, goods receipts and approval rules.")]):
    c.markdown(f"<div class='ben'><span style='font-size:1.5rem'>{i}</span><b>{t}</b><span>{d}</span></div>", unsafe_allow_html=True)

st.markdown("<h2 style='margin-top:44px'>FAQs</h2>", unsafe_allow_html=True)
with st.expander("Is this built for a specific company?", expanded=True):
    st.write("Yes. This prototype is set up for one sample company (Acme Retail India). It checks invoices against that company's "
             "vendor master, purchase orders, goods receipts and approval rules. All of that data is invented sample data.")
with st.expander("Can it handle different invoice formats and scanned PDFs?"):
    st.write("Yes. Text PDFs are read from their text layer; scanned PDFs are read by a vision model, and the values are cross-checked "
             "against a separate OCR read (Tesseract). Single invoices up to 10 pages and 10 MB. Handwriting and very poor scans may fail - "
             "those go to a person, never guessed.")
with st.expander("What rules does it check?"):
    st.write("Document type, required fields, whether each value really appears in the document, hidden text, arithmetic and GST; vendor "
             "approved/blocked, GSTIN and bank account against the vendor record; exact and near duplicates; PO match (or a suggested PO "
             "when none is printed), line prices against tolerance, PO balance across split invoices, quantity billed vs received; dates, "
             "currency and the auto-approve limit.")
with st.expander("Can I change the business rules (e.g., tolerance, approval limit)?"):
    st.write("Yes, under Profile → Approval rules. You can preview the impact on past invoices before saving. Each save creates a new "
             "policy version; past decisions keep the version they were made under. The bank-account and duplicate checks can't be turned off.")
with st.expander("Does the AI decide whether to pay?"):
    st.write("No. AI reads and explains. Python rules make the decision, and a person handles every exception. Nothing is paid or emailed automatically.")
st.markdown("<div class='z-muted' style='margin-top:30px'>Zamp AP Assistant · prototype for the AI Solutions Analyst case study · sample data only</div>",
            unsafe_allow_html=True)
