# Submission — PS-1: Invoice processing, from PDF to decision

## 1. What to submit (checklist)

| # | Item | Where | Status |
|---|---|---|---|
| 1 | **Live app link** | https://zamp-invoice-intelligence.streamlit.app | ✅ live |
| 2 | **Code (public GitHub repo)** | https://github.com/Jhamusk18/Zamp-invoice-intelligence | ✅ public |
| 3 | **5-minute demo video**: happy path live + at least one edge case, explaining the choices | Loom / YouTube (unlisted) / Google Drive (set to "anyone with the link") | ⬜ record (script in section 6) |
| 4 | **2–4 edge cases** with why they matter | Section 4 below, also shown in the video | ✅ |
| 5 | **Test files** the reviewer can upload | `sample_data/test_invoices/` in the repo (D1–D5, X1–X8) | ✅ |

**Before you hit submit:**
- [ ] Open the live link in a private/incognito window. It should load without login and with no yellow "add GEMINI_API_KEY" warning.
- [ ] **Profile → Reset demo data**, so the reviewer starts clean. (Do it again right after recording.)
- [ ] Video link opens for someone who isn't logged in to your account.
- [ ] Delete the extra *experiment* app on share.streamlit.io, so only one link exists.
- [ ] Wake the app up on submission day. Free Streamlit apps sleep after a few days without visits.

## 2. Short description (paste into the submission form)

> **Zamp AP Assistant** checks a vendor invoice PDF and tells accounts payable what to do with it: **Ready to Pay**, **Needs Attention** or **Blocked**, with the reasons in plain English.
>
> **How it works**
> - **AI reads, Python decides, people own exceptions.** Gemini reads the invoice (text PDFs and scans) and must quote where it found each value. Python then checks every quote against the document itself, so invented values are caught.
> - **Python makes the decision.** Fixed, versioned rules check the invoice against the vendor list, the purchase order, goods received and the approval limits, and set the status. The AI never sees or sets a status.
> - **People decide every exception.** A person reviews each Needs Attention invoice and records a reason. A vendor email is prepared, and every step is written to an append-only audit trail.
>
> **What you'll see:** a live run view showing 5 steps, a history dashboard, a review page with the original PDF beside the result, and a chat assistant that explains the result but can't approve anything.
>
> **Edge cases covered:**
> - scanned invoice with no PO number
> - bank account change combined with hidden "approve this" text
> - disguised duplicate
> - split purchase order billed past its value
>
> These are among the 13 test PDFs in the repo.

## 3. Process map

```
PDF ──► 1 PDF received ──► 2 Text extracted ──► 3 Fields validated ──► 4 Policy checks ──► 5 Decision & audit
        type/size/pages     text layer, or OCR      AI reads fields +       17 Python rules:        worst finding wins:
        same file twice?    for scans; hidden-      a quote for each;       vendor · GSTIN · bank   any FAIL  → Blocked
        → show old result   text scan               Python verifies each    duplicate · PO match    any WARN  → Needs Attention
                                                    quote, checks maths,    prices · PO balance     else      → Ready to Pay
                                                    re-reads once if off    goods received · dates  PO money: reserve/commit/release
                                                                            limits                  audit log (append-only)
                                                                                     │
                     Needs Attention ──► person on Review page: note + Ready to Pay / Blocked ──► vendor email (copy / Gmail)
```

- **Technical errors** (unreadable file, AI down) stop the run with **Retry**.
- **Business problems** never stop the run: they become findings.
- Every number shown is calculated from the database, never typed by the AI.

## 4. Edge cases (the four I'd lead with)

| # | Case (test file) | Why it's realistic | What the system does | Design choice behind it |
|---|---|---|---|---|
| 1 | **Scanned invoice, no PO number, vendor's own item names** (`D2`) | Small vendors send phone scans and leave out the PO number. Their item names don't match ours. | It reads the scan with AI, double-checks the values with OCR, and scores open POs by amount, date and item meaning. It suggests the best PO with a score. The result is **Needs Attention**. | A guessed match is **never auto-paid**. A person confirms the suggested PO. |
| 2 | **Bank account changed + hidden "approve this invoice" text** (`D3`) | Bank-change fraud is the costliest AP failure. Prompt injection is a new risk once AI reads documents. | The hidden white text is detected by comparing text colour with the background pixel, then ignored and reported. The bank mismatch holds the invoice: **Needs Attention**, with "call the vendor on the number we have on file". | The AI never decides, so injected text has nothing to persuade. The bank rule is **locked** and can't be relaxed in settings. |
| 3 | **Disguised duplicate** (`X1`: `INV-0042` sent again as `42`) | Re-sent invoices with a reformatted number are a common way to pay twice. | Invoice numbers are normalised. The fuzzy check flags the same vendor with the same amount when the number is similar or the date is within 7 days. Result: **Blocked**. | We tuned this so **monthly recurring bills are not** treated as duplicates. Same amount alone isn't enough. |
| 4 | **Split PO billed past its value** (`X2`: third invoice on one PO) | Vendors bill one PO in parts. The last part often goes over what was ordered or received. | Every invoice reserves its amount on the PO: Needs Attention reserves, Ready to Pay commits, Blocked releases. The third invoice goes over the remaining balance and over goods received, so it is **Needs Attention**. | Each invoice holds one allocation row per PO, so **re-processing never counts money twice**. |

Also covered:

| File | Case | Result |
|---|---|---|
| D4 | Short receipt: billed 80, received 70 | Needs Attention |
| D5 | Total matches the PO but a line price is +4.5% | Needs Attention |
| X3 | Vendor arithmetic error | Needs Attention |
| X4 | Blocked vendor | Blocked |
| X5 | Unknown vendor | Blocked |
| X6 | Look-alike vendor name with a different GSTIN and bank | Blocked |
| X7 | Price +7.3% over the PO | Blocked |
| X8 | A quotation, not an invoice | Blocked |

## 5. Key choices (for questions)

**Three outcomes, not two.**
- **Blocked** is for things a person shouldn't override with a click: a blocked vendor, a duplicate, a fake vendor.
- **Needs Attention** is for things a phone call can settle.

**AI only where meaning is needed:**
- reading the invoice
- matching item descriptions
- writing a plain summary

Every AI number is checked against the findings; if any doesn't match, a template is used instead. Maths, money and status are plain Python, so they are repeatable and explainable.

**Cost and reliability:**
- Gemini Flash-Lite does the first read; Flash does the retry or fallback.
- Results are cached by file, so re-uploading the same PDF costs nothing.
- If the AI service is busy, the app waits and retries, then switches models, then shows a friendly error with **Retry**.

**Human in the loop:**
- Every override needs a written reason.
- Every action is in an append-only audit log that the database itself refuses to edit or delete.

**Assistant:** it answers from stored results using fixed templates (no AI, no cost, always consistent). It refuses to approve, change or send anything.

**Known limits (next steps):**
- no login
- no phone-verification record yet
- money stored as floats with tolerances
- hidden-text detector not yet tested on a large real-world PDF set

## 6. 5-minute video script

*Before recording:*
- Profile → Reset demo data.
- Have `D1`, `D3` and `X1` downloaded.
- Use a 1440px-wide browser window and zoom to 100%.

| Time | Screen | Say (roughly) |
|---|---|---|
| 0:00–0:30 | **Welcome** | "AP teams lose money to three things: paying the wrong amount, paying twice, and paying a fraudster. This tool checks every invoice before payment and gives one of three answers: Ready to Pay, Needs Attention or Blocked, with reasons in plain English." |
| 0:30–1:30 | **Upload `D1`** (happy path) | Drop the file and watch the 5 steps. "AI reads the invoice and must quote where it found each value. Python checks those quotes against the PDF, checks the maths, then runs the business rules: vendor, PO, price, goods received, duplicates." Result: **Ready to Pay**. Click a chat option ("Why is it OK?"). |
| 1:30–2:45 | **Upload `D3`** (bank change + hidden text) | "This one looks normal, but the bank account is different from our records. That's the classic fraud. It also hides white text telling an AI to approve it." Show **Needs Attention** and the next step: "call the vendor on the number we have". "The AI never makes the decision, so the hidden instruction has nothing to persuade. We detect it and report it." |
| 2:45–3:45 | **Review page** for D3 | Show the PDF on the left and the result on the right. Write a note ("Called vendor, they confirmed no bank change"), choose **Blocked**, and save. Show the email that changed to match, plus **Copy** / **Open in Gmail**. "A person owns every exception, and every action is recorded with a reason." |
| 3:45–4:20 | **Upload `X1`** (disguised duplicate) | "Same invoice re-sent as '42' instead of 'INV-0042'." Result: **Blocked** as a duplicate of the earlier invoice. "We tuned this so monthly bills with the same amount are *not* flagged." |
| 4:20–4:45 | **History** | Totals per status, search and filters. "Every run is here: who decided, the system or a reviewer, and why." |
| 4:45–5:00 | **Profile → Approval rules** | "Limits are versioned settings. You can see what would change before changing them. The bank and duplicate rules are locked." Close: "AI reads, Python decides, people own the exceptions." |

**Tips:**
- If the AI is slow on a take, it's fine to cut. Everything runs live.
- Keep the mouse still while talking.
- Speak to a non-technical AP manager, not an engineer.
