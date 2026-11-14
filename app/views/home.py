import streamlit as st

st.markdown("""<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display:none; }
.hero { border-radius: 28px; padding: 48px 44px 44px; margin: 12px 0 16px;
        background: radial-gradient(900px 400px at 80% 30%, rgba(124,92,255,.45), transparent 60%),
                    linear-gradient(180deg, #17123A 0%, #2A1670 100%); }
.pill { display:inline-block; border:1px solid rgba(167,139,250,.6); color:#D9CCFF; border-radius:999px; padding:4px 12px; font-size:.8rem; }
.hero h1 { font-size: 3.1rem; line-height: 1.08; margin: 18px 0 14px; color: #fff !important; }
.hero h1 span { color:#A78BFA !important; }
.hero p { color:#CFCBEA; font-size:1.08rem; max-width: 560px; }
.mock { background:#F4F2FF; border-radius:18px; padding:26px; color:#2A2366; width: 300px; transform: rotate(-4deg); box-shadow: 0 30px 60px rgba(0,0,0,.4); }
.mock .bar { height:9px; background:#D9D4F7; border-radius:6px; margin:10px 0; }
.chk { background:#16133A; border:1px solid #3B3480; border-radius:16px; padding:16px 20px; margin:-120px 0 0 150px; width:230px; position:relative; }
.chk div { margin:8px 0; font-size:.92rem; }
.step { background:#14122C; border:1px solid #2B2852; border-radius:16px; padding:20px; height:100%; }
.step .n { width:44px;height:44px;border-radius:50%;background:#6D4AFF;display:flex;align-items:center;justify-content:center;font-size:1.3rem;margin-bottom:12px }
.step b { display:block; margin-bottom:6px; } .step span { color:#9C99BD; font-size:.9rem; }
.ben b { display:block } .ben span { color:#9C99BD; font-size:.9rem }
</style>""", unsafe_allow_html=True)

nav = st.columns([3, 1, 1, 1, 1.3, 1.3])
nav[0].markdown("### 🟪 Zamp AP Assistant")
nav[1].markdown("<div style='padding-top:14px'><a href='#how' style='color:#ddd;text-decoration:none'>How it works</a></div>", unsafe_allow_html=True)
nav[2].markdown("<div style='padding-top:14px'><a href='#benefits' style='color:#ddd;text-decoration:none'>Benefits</a></div>", unsafe_allow_html=True)
nav[3].markdown("<div style='padding-top:14px'><a href='#faqs' style='color:#ddd;text-decoration:none'>FAQs</a></div>", unsafe_allow_html=True)
if nav[4].button("Explore Demo", use_container_width=True, key="n_demo"):
    st.switch_page(st.session_state.pages["upload"])
if nav[5].button("Verify Invoice →", type="primary", use_container_width=True, key="n_up"):
    st.switch_page(st.session_state.pages["upload"])

h1, h2 = st.columns([1.35, 1])
with h1:
    st.markdown("""<div class='hero'><span class='pill'>AI + Rules for Accounts Payable</span>
    <h1>Verify invoices, prevent errors, and <span>pay with confidence.</span></h1>
    <p>An intelligent Accounts Payable assistant that reads vendor invoices, validates them against your business rules,
    and flags issues for quick resolution.</p></div>""", unsafe_allow_html=True)
    b = st.columns([1, 1, 2])
    if b[0].button("⬆ Verify an Invoice", type="primary", use_container_width=True):
        st.switch_page(st.session_state.pages["upload"])
    if b[1].button("Explore Demo", use_container_width=True):
        st.switch_page(st.session_state.pages["upload"])
with h2:
    st.markdown("""<div style='padding:60px 0 0 40px'><div class='mock'><b style='font-size:1.4rem;font-style:italic'>INVOICE</b>
    <div class='bar' style='width:70%'></div><div class='bar' style='width:50%'></div><div class='bar'></div><div class='bar' style='width:80%'></div>
    <div class='bar'></div><div class='bar' style='width:60%'></div><div class='bar' style='width:40%'></div></div>
    <div class='chk'><div>✅ Vendor verified</div><div>✅ PO matched</div><div>✅ Amount validated</div>
    <div style='background:rgba(34,197,94,.15);border-radius:10px;padding:8px 10px;color:#4ADE80;font-weight:700'>🛡️ Ready to Pay</div></div>
    <div class='z-muted' style='margin:14px 0 0 150px'>Illustration, not a processed invoice</div></div>""", unsafe_allow_html=True)

st.markdown("<a name='how'></a>", unsafe_allow_html=True)
st.markdown("<h2 style='text-align:center;margin-top:40px'>How Zamp AP Assistant works</h2><p style='text-align:center' class='z-muted'>From invoice upload to a clear decision in seconds.</p>", unsafe_allow_html=True)
steps = [("☁️", "1. Upload Invoice", "Upload a PDF or scanned invoice from your vendor."),
         ("🔎", "2. Extract & Understand", "AI reads the invoice and quotes where each value came from, even from different layouts."),
         ("🧮", "3. Validate with Your Rules", "Python checks vendor, bank, PO, prices, quantities received, duplicates and policy."),
         ("🛡️", "4. Get a Decision", "Ready to Pay, Needs Attention or Blocked - with reasons, evidence and a vendor email draft.")]
cols = st.columns(4)
for c, (i, t, d) in zip(cols, steps):
    c.markdown(f"<div class='step'><div class='n'>{i}</div><b>{t}</b><span>{d}</span></div>", unsafe_allow_html=True)

st.markdown("<a name='benefits'></a>", unsafe_allow_html=True)
st.write("")
st.divider()
bc = st.columns(3)
for c, (i, t, d) in zip(bc, [("⚡", "Faster Processing", "Routine invoices that pass every check need no one's time."),
                             ("🛡️", "Lower Financial Risk", "Catches overbilling, duplicates, bank-account changes and hidden instructions."),
                             ("🧱", "Built for Your Business", "Uses your vendor master, POs, goods receipts and approval rules.")]):
    c.markdown(f"<div class='ben'><span style='font-size:1.6rem'>{i}</span><b>{t}</b><span>{d}</span></div>", unsafe_allow_html=True)
st.divider()

st.markdown("<a name='faqs'></a>", unsafe_allow_html=True)
f1, f2 = st.columns([1, 2.4])
f1.markdown("## FAQs\n<span class='z-muted'>Common questions about Zamp AP Assistant.</span>", unsafe_allow_html=True)
with f2:
    with st.expander("Is this built for a specific company?", expanded=True):
        st.write("Yes. This prototype is set up for one sample company (Acme Retail India). It checks invoices against that "
                 "company's vendor master, purchase orders, goods receipts and approval rules. All of that data is invented sample data.")
    with st.expander("Can it handle different invoice formats and scanned PDFs?"):
        st.write("Yes. Text PDFs are read from their text layer; scanned PDFs are read by a vision model, and the values are "
                 "cross-checked against a separate OCR read (Tesseract). Single invoices up to 10 pages and 10 MB. "
                 "Handwriting and very poor scans may fail - those are sent to a person, never guessed.")
    with st.expander("What rules does it check?"):
        st.write("Document type, required fields, whether each value really appears in the document, hidden text, arithmetic "
                 "and GST; vendor approved/blocked, GSTIN and bank account against the vendor record; exact and near "
                 "duplicates; PO match (or a suggested PO when none is printed), line prices against tolerance, PO balance "
                 "across split invoices, quantity billed vs received (3-way match for goods); dates, currency and the auto-approve limit.")
    with st.expander("Can I change the business rules (e.g., tolerance, approval limit)?"):
        st.write("Yes, on the Approval Rules page. You can preview the impact on past invoices before saving. Each save "
                 "creates a new policy version; past decisions keep the version they were made under. The bank-account "
                 "and duplicate checks can't be turned off.")
    with st.expander("Does the AI decide whether to pay?"):
        st.write("No. AI reads and explains. Python rules make the decision, and a person handles every exception. "
                 "Nothing is paid or emailed automatically.")
st.divider()
st.markdown("<div class='z-muted'>Zamp AP Assistant · prototype for the AI Solutions Analyst case study · sample data only</div>", unsafe_allow_html=True)
