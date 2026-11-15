# Zamp AP Assistant — PS-1: Invoice processing, from PDF to decision

**Live app:** https://zamp-invoice-intelligence.streamlit.app

Upload a vendor invoice PDF (text or scanned). AI reads it, Python checks it against the company's vendors,
purchase orders, goods receipts and approval rules, and the result is **Ready to Pay**, **Needs Attention** or **Rejected**,
with every reason, the evidence, a vendor email draft and an audit trail. A person decides every exception.

Submission notes (edge cases, process map, demo script): [`docs/SUBMISSION.md`](docs/SUBMISSION.md)

## Run it locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
sudo apt-get install -y tesseract-ocr        # OCR for scanned invoices (macOS: brew install tesseract)
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then paste your Gemini key into it
streamlit run app/streamlit_app.py
```

AI order: Gemini (primary, then its second model). If Google is down, Groq is the backup, used only when `GROQ_API_KEY` is set.

The sample database builds itself on first start. **Profile → Reset demo data** rebuilds it.
Regenerate the sample PDFs with `python scripts/make_sample_invoices.py` (writes both folders). Run tests with `pytest -q`.

## Who does what

| | Does | Never does |
|---|---|---|
| **AI** (Gemini via LangChain, `core/llm.py`) | Reads fields + quotes a snippet for each; judges whether two item descriptions mean the same thing; writes the plain-English summary from the findings (numbers checked against the findings, else a template is used) | Sees or sets a status |
| **Python** (`core/rules.py`, `core/decision.py`) | Checks every snippet against the document, arithmetic, hidden text, vendor, GSTIN, bank, duplicates, PO, prices, PO balance, goods received, dates, limits; sets the status; moves PO money | Guesses |
| **Person** (Review page) | Marks a Needs Attention invoice Ready to Pay or Rejected with a note (or pulls back a Ready to Pay one); sends the prepared vendor email | - |

## Screens

- **Welcome** - what it does, how it works, FAQs
- **Upload** - drop a PDF, watch 5 live steps, get the decision, chat with the Zamp Assistant, open **Review**
- **History** - every invoice with totals per status, search, filters (status, vendor, date) and sorting; click a row for **Review**
- **Profile** - your approvals/rejections, the approval rules (with "see what would change"), and the prototype's assumptions
- **Review** (opens from Upload or History) - the original PDF beside the result and next step, a review note with a Needs Attention / Ready to Pay / Rejected choice, a vendor email that follows the choice (copy or open in Gmail), and the Zamp Assistant

## Demo cases — `sample_data/test_invoices/` (upload these)

The 8 past invoices that pre-fill History are in `sample_data/history_invoices/` (don't upload those).

| File | Case | Expected |
|---|---|---|
| D1 | Happy path | Ready to Pay |
| D2 | Scanned, no PO number, vendor's own item names | Needs Attention (suggested PO) |
| D3 | Bank account changed + hidden "approve this" text | Needs Attention |
| D4 | Billed 80, received 70 | Needs Attention |
| D5 | Total matches the PO, line prices don't | Needs Attention |
| X1-X3 | Disguised duplicate · split PO over-billed · vendor arithmetic error | Rejected · Needs Attention · Needs Attention |
| X4-X8 | Blocked vendor · unknown vendor · lookalike vendor · price +7.3% over PO · quotation, not an invoice | Rejected (all five) |
| X9 | One bundled line ("desk + chair" set) for two PO items | Needs Attention |
| X10 | No PO number and two open orders fit almost equally - neither is picked | Needs Attention |

## Next steps (known limits, not built)

- Money as integer paise instead of rounded floats (comparisons already use small tolerances)
- Unit price in the missing-PO score
- Test that processing two related invoices in either order gives consistent results
- Hidden-text detector tested on a large set of real-world PDFs
- Login / shared password for a public link; recording phone verification of bank changes in the app
- AI answers for free-typed assistant questions (today: keyword routing to the fixed menu)

## Layout

```
app/            Streamlit screens (display only: they call core/, never SQL)
core/           pipeline, rules, decision, policy, document checks, AI layer, helper, what-if, eval
sample_data/    company/*.csv (vendors, POs, receipts) · invoices.json (ground truth + expected outcomes)
                test_invoices/ (upload these) · history_invoices/ (pre-loaded into History)
tests/          hand-checked cases and safety rules
docs/           decisions made along the way
```
