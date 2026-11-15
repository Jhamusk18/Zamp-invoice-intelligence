import streamlit as st

st.markdown("""<style>
.w-eyebrow { display:inline-flex; align-items:center; gap:8px; background:#EEF3FF; color:#2F5BEA; border:1px solid #D6E1FD; border-radius:999px;
             padding:5px 14px; font-size:.82rem; font-weight:700; }
.w-h1 { font-size: 3.3rem; line-height: 1.06; font-weight: 800; letter-spacing: -.03em; color:#0F172A; margin: 18px 0 16px; }
.w-h1 span { color:#2F5BEA; }
.w-lead { font-size: 1.15rem; line-height: 1.6; color:#334155; max-width: 620px; }
.w-h2 { font-size: 2.5rem; line-height: 1.12; font-weight: 800; letter-spacing: -.025em; color:#0F172A; margin: 0 0 16px; }
.w-p { font-size: 1.08rem; line-height: 1.65; color:#334155; max-width: 640px; }
.w-list { list-style:none; padding:0; margin: 22px 0 8px; }
.w-list li { display:flex; gap:14px; align-items:flex-start; font-size:1.06rem; color:#0F172A; margin: 0 0 14px; line-height:1.45; }
.w-list li::before { content:"✓"; color:#2F5BEA; font-weight:800; font-size:1.05rem; margin-top:1px; }
.w-list li span { color:#64748B; display:block; font-size:.92rem; }
.w-section { padding: 56px 0 8px; }
.w-band { background:#0B1534; border-radius: 22px; padding: 30px 34px; color:#fff; }
.w-band h3 { color:#fff !important; margin:0 0 6px; font-size:1.4rem; }
.w-band p { color:#B9C6E6; margin:0; }
.w-tile { background:#fff; border:1px solid #E2E8F2; border-radius:16px; padding:18px; height:100%; box-shadow: 0 6px 18px rgba(15,23,42,.04); }
.w-tile .ic { width:40px; height:40px; border-radius:12px; background:#EEF3FF; color:#2F5BEA; display:flex; align-items:center; justify-content:center; font-weight:800; margin-bottom:10px; }
.w-tile b { display:block; color:#0F172A; margin-bottom:4px; } .w-tile span { color:#64748B; font-size:.92rem; line-height:1.45; }
.w-step { display:flex; gap:12px; align-items:flex-start; }
.w-step .n { width:34px; height:34px; border-radius:50%; background:#2F5BEA; color:#fff; font-weight:800; display:flex; align-items:center; justify-content:center; flex:none; }
.w-step b { color:#0F172A; display:block; } .w-step span { color:#64748B; font-size:.92rem; }
.w-mock { background:#fff; border:1px solid #E2E8F2; border-radius:20px; padding:20px; box-shadow: 0 24px 60px rgba(15,23,42,.10); }
.w-row { display:flex; align-items:center; gap:12px; padding:12px 4px; border-bottom:1px solid #EEF2F8; }
.w-row:last-child { border-bottom:0; }
.w-doc { width:34px; height:40px; border-radius:8px; background:#FCEBEE; color:#D63A52; font-size:.62rem; font-weight:800; display:flex; align-items:flex-end; justify-content:center; padding-bottom:6px; flex:none; }
.w-pill { margin-left:auto; padding:3px 11px; border-radius:999px; font-size:.78rem; font-weight:700; white-space:nowrap; }
</style>""", unsafe_allow_html=True)

FLOW = """<svg viewBox='0 0 600 400' xmlns='http://www.w3.org/2000/svg' style='width:100%;height:auto'>
 <defs><filter id='s' x='-20%' y='-20%' width='140%' height='140%'><feDropShadow dx='0' dy='6' stdDeviation='8' flood-color='#0F172A' flood-opacity='.10'/></filter></defs>
 <g fill='none' stroke='#2F5BEA' stroke-width='2'>
   <path d='M112 78 H170 Q190 78 190 98 V302 Q190 322 170 322 H112'/><path d='M112 200 H246'/>
 </g>
 <g filter='url(#s)'>
  <g transform='translate(30,30)'><path d='M8 0h50l20 20v76a8 8 0 0 1-8 8H8a8 8 0 0 1-8-8V8a8 8 0 0 1 8-8z' fill='#fff'/><path d='M58 0v20h20' fill='#EEF2F8'/>
    <rect x='14' y='70' width='34' height='16' rx='4' fill='#D63A52'/><text x='31' y='82' font-family='Arial' font-size='10' font-weight='700' fill='#fff' text-anchor='middle'>PDF</text></g>
  <g transform='translate(30,152)'><path d='M8 0h50l20 20v76a8 8 0 0 1-8 8H8a8 8 0 0 1-8-8V8a8 8 0 0 1 8-8z' fill='#fff'/><path d='M58 0v20h20' fill='#EEF2F8'/>
    <rect x='14' y='70' width='40' height='16' rx='4' fill='#64748B'/><text x='34' y='82' font-family='Arial' font-size='10' font-weight='700' fill='#fff' text-anchor='middle'>SCAN</text></g>
  <g transform='translate(30,274)'><path d='M8 0h50l20 20v76a8 8 0 0 1-8 8H8a8 8 0 0 1-8-8V8a8 8 0 0 1 8-8z' fill='#fff'/><path d='M58 0v20h20' fill='#EEF2F8'/>
    <rect x='14' y='70' width='40' height='16' rx='4' fill='#2F5BEA'/><text x='34' y='82' font-family='Arial' font-size='9' font-weight='700' fill='#fff' text-anchor='middle'>BILL</text></g>
 </g>
 <circle cx='300' cy='200' r='70' fill='none' stroke='#2F5BEA' stroke-width='2.5' stroke-dasharray='2 9' stroke-linecap='round'/>
 <g filter='url(#s)'><circle cx='300' cy='200' r='52' fill='#fff'/></g>
 <rect x='278' y='178' width='44' height='44' rx='12' fill='#2F5BEA'/><path d='M288 190h24l-24 20h24' stroke='#fff' stroke-width='4' fill='none' stroke-linecap='round' stroke-linejoin='round'/>
 <path d='M372 200 H418' stroke='#2F5BEA' stroke-width='2.5' stroke-dasharray='2 9' stroke-linecap='round'/>
 <g filter='url(#s)'><rect x='420' y='70' width='160' height='260' rx='16' fill='#fff'/></g>
 <rect x='440' y='92' width='70' height='8' rx='4' fill='#E2E8F2'/><rect x='440' y='108' width='110' height='6' rx='3' fill='#EEF2F8'/>
 <g font-family='Arial' font-size='12' font-weight='700'>
  <rect x='440' y='136' width='120' height='44' rx='10' fill='#E7F6EF'/><circle cx='458' cy='158' r='9' fill='#0F9F6E'/><path d='M453 158l4 4 7-8' stroke='#fff' stroke-width='2.4' fill='none'/><text x='474' y='162' fill='#0B7A55'>Ready to Pay</text>
  <rect x='440' y='190' width='120' height='44' rx='10' fill='#FDF1E3'/><circle cx='458' cy='212' r='9' fill='#E8963A'/><text x='458' y='216.5' fill='#fff' text-anchor='middle'>!</text><text x='474' y='216' fill='#A65B10'>Needs review</text>
  <rect x='440' y='244' width='120' height='44' rx='10' fill='#FCEBEE'/><circle cx='458' cy='266' r='9' fill='#D63A52'/><path d='M454 262l8 8M462 262l-8 8' stroke='#fff' stroke-width='2.2'/><text x='474' y='270' fill='#B8263E'>Blocked</text>
 </g>
 <rect x='550' y='48' width='46' height='46' rx='12' fill='#2F5BEA'/><path d='M573 58l13 5v9c0 8-5.5 13.5-13 15.5-7.5-2-13-7.5-13-15.5v-9z' fill='none' stroke='#fff' stroke-width='2.4'/><path d='M567 72l4.5 4.5 8-8.5' stroke='#fff' stroke-width='2.4' fill='none'/>
</svg>"""

# ---------------------------------------------------------------- intro
l, r = st.columns([1.1, 1], gap="large", vertical_alignment="center")
with l:
    st.markdown("""<span class='w-eyebrow'>● AI reads · Rules decide · You approve</span>
    <div class='w-h1'>Check every invoice <span>before you pay it.</span></div>
    <div class='w-lead'>Zamp AP Assistant reads each vendor invoice - PDF or scan - and checks it against your vendors, purchase orders,
    goods received and approval rules. Clean invoices are ready to pay; anything risky is held or blocked, with the reason in plain words.</div>""",
                unsafe_allow_html=True)
    st.write("")
    b = st.columns([1, 1, 1.2])
    if b[0].button("Verify an invoice", type="primary", icon=":material/upload_file:", use_container_width=True):
        st.switch_page(st.session_state.pages["upload"])
    if b[1].button("See past results", icon=":material/history:", use_container_width=True):
        st.switch_page(st.session_state.pages["history"])
with r:
    st.markdown("""<div class='w-mock'>
    <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:6px'><b style='color:#0F172A'>Today's invoices</b>
      <span style='font-size:.78rem;color:#64748B'>example</span></div>
    <div class='w-row'><div class='w-doc'>PDF</div><div><b style='color:#0F172A'>INV-NS-1001</b><br><span style='color:#64748B;font-size:.85rem'>Northstar Office Supplies · ₹49,560</span></div>
      <span class='w-pill' style='background:#E7F6EF;color:#0B7A55'>● Ready to Pay</span></div>
    <div class='w-row'><div class='w-doc'>PDF</div><div><b style='color:#0F172A'>GF/2026/5214</b><br><span style='color:#64748B;font-size:.85rem'>Bank account differs from our records</span></div>
      <span class='w-pill' style='background:#FDF1E3;color:#A65B10'>● Needs Attention</span></div>
    <div class='w-row'><div class='w-doc'>PDF</div><div><b style='color:#0F172A'>GF/2026/5302</b><br><span style='color:#64748B;font-size:.85rem'>Lookalike vendor - different GSTIN</span></div>
      <span class='w-pill' style='background:#FCEBEE;color:#B8263E'>● Blocked</span></div>
    <div class='w-row'><div class='w-doc'>PDF</div><div><b style='color:#0F172A'>42</b><br><span style='color:#64748B;font-size:.85rem'>Same invoice as INV-0042, already paid</span></div>
      <span class='w-pill' style='background:#FCEBEE;color:#B8263E'>● Blocked</span></div>
    </div>""", unsafe_allow_html=True)

# ---------------------------------------------------------------- why verify
st.markdown("<div class='w-section'></div>", unsafe_allow_html=True)
l, r = st.columns([1, 1.05], gap="large", vertical_alignment="center")
with l:
    st.markdown("""<div class='w-h2'>Why verify your invoices?</div>
    <div class='w-p'>Hundreds of vendor invoices arrive every month, all in different formats. Matching each one by hand to the right purchase order is slow -
    and it's exactly where a duplicate, an overcharge or a changed bank account slips through on a busy afternoon.</div>
    <ul class='w-list'>
      <li><div>Catch duplicates, overbilling and short deliveries<span>before money leaves the account, not after an audit</span></div></li>
      <li><div>Stop payments to changed or lookalike bank accounts<span>the most common invoice-fraud pattern</span></div></li>
      <li><div>See where every number came from<span>each value is traced back to the PDF, and every decision is explained</span></div></li>
      <li><div>Let your team handle only the exceptions<span>clean invoices go straight through; a person decides the rest</span></div></li>
    </ul>""", unsafe_allow_html=True)
    if st.button("Verify my invoice", type="primary", icon=":material/arrow_forward:", key="why_cta"):
        st.switch_page(st.session_state.pages["upload"])
with r:
    st.markdown(FLOW, unsafe_allow_html=True)

# ---------------------------------------------------------------- what it checks
st.markdown("<div class='w-section'></div><div class='w-h2' style='font-size:2rem'>What every invoice is checked for</div>", unsafe_allow_html=True)
tiles = [("V", "Vendor & GSTIN", "Approved, not blocked, and not a lookalike name with someone else's tax ID."),
         ("₹", "Bank account", "Must match the account on file. A change is held until it's confirmed by phone."),
         ("2×", "Duplicates", "Same invoice resent with a new format (INV-0042 vs 42) or the same amount days apart."),
         ("PO", "Order & prices", "Matched to the purchase order line by line, within your tolerance, without exceeding the PO."),
         ("📦", "Goods received", "You only pay for what actually arrived (three-way match)."),
         ("👁", "Document integrity", "Every value found in the PDF again; hidden text and arithmetic errors flagged.")]
for row in (tiles[:3], tiles[3:]):
    cols = st.columns(3)
    for c, (i, t, d) in zip(cols, row):
        c.markdown(f"<div class='w-tile'><div class='ic'>{i}</div><b>{t}</b><span>{d}</span></div>", unsafe_allow_html=True)
    st.write("")

# ---------------------------------------------------------------- how it works (dark band for contrast)
st.markdown("<div class='w-section'></div>", unsafe_allow_html=True)
st.markdown("""<div class='w-band'><h3>From PDF to a clear decision in seconds</h3><p>AI reads. Python rules decide. A person approves the exceptions - and nothing is ever paid or emailed automatically.</p></div>""",
            unsafe_allow_html=True)
st.write("")
cols = st.columns(4)
for c, (n, t, d) in zip(cols, [("1", "Upload", "Drop a PDF or a scanned invoice."), ("2", "Read", "AI extracts each field and quotes where it found it."),
                               ("3", "Check", "Rules check vendor, bank, PO, receipt, duplicates and policy."),
                               ("4", "Decide", "Ready to Pay, Needs Attention or Blocked - with a ready email for the vendor.")]):
    c.markdown(f"<div class='w-step'><div class='n'>{n}</div><div><b>{t}</b><span>{d}</span></div></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- FAQ
st.markdown("<div class='w-section'></div><div class='w-h2' style='font-size:2rem'>FAQs</div>", unsafe_allow_html=True)
with st.expander("Is this built for a specific company?", expanded=True):
    st.write("Yes. This prototype is set up for one sample company (Acme Retail India). It checks invoices against that company's "
             "vendor master, purchase orders, goods receipts and approval rules. All of that data is invented sample data.")
with st.expander("Can it handle different invoice formats and scanned PDFs?"):
    st.write("Yes. Text PDFs are read from their text layer; scanned PDFs are read by a vision model, and the values are cross-checked "
             "against a separate OCR read (Tesseract). Single invoices up to 10 pages and 10 MB. Handwriting and very poor scans may fail - "
             "those go to a person, never guessed.")
with st.expander("Can I change the business rules (e.g., tolerance, approval limit)?"):
    st.write("Yes, under Profile → Approval rules. You can preview the impact on past invoices before saving. Each save creates a new "
             "policy version; past decisions keep the version they were made under. The bank-account and duplicate checks can't be turned off.")
with st.expander("Does the AI decide whether to pay?"):
    st.write("No. AI reads and explains. Python rules make the decision, and a person handles every exception. Nothing is paid or emailed automatically.")
st.markdown("<div class='z-muted' style='margin-top:30px'>Zamp AP Assistant · prototype for the AI Solutions Analyst case study · sample data only</div>",
            unsafe_allow_html=True)
