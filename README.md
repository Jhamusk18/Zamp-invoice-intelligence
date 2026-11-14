# Zamp AP Assistant — PS-1: Invoice processing, from PDF to decision

Upload a vendor invoice PDF (text or scanned). AI reads it, Python checks it against the company's vendors,
purchase orders, goods receipts and approval rules, and the result is **Ready to Pay**, **Needs Attention** or **Blocked**,
with every reason, the evidence, a vendor email draft and an audit trail. A person decides every exception.

## Run it locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
sudo apt-get install -y tesseract-ocr        # OCR for scanned invoices (macOS: brew install tesseract)
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then paste your Gemini key into it
streamlit run app/streamlit_app.py
```

The sample database builds itself on first start. **Reset Demo Data** (sidebar) rebuilds it.
Regenerate the sample PDFs with `python scripts/make_sample_invoices.py`. Run tests with `pytest -q`.

## Who does what

| | Does | Never does |
|---|---|---|
| **AI** (Gemini via LangChain, `core/llm.py`) | Reads fields + quotes a snippet for each; judges whether two item descriptions mean the same thing; writes the explanation and email from the findings | Sees or sets a status |
| **Python** (`core/rules.py`, `core/decision.py`) | Checks every snippet against the document, arithmetic, hidden text, vendor, GSTIN, bank, duplicates, PO, prices, PO balance, goods received, dates, limits; sets the status; moves PO money | Guesses |
| **Person** (Review page) | Approves or rejects Needs Attention invoices, with a reason | - |

## Screens

- **Welcome** - what it does, how it works, FAQs
- **Upload** - drop a PDF, watch 5 live steps, get the decision, ask the Invoice Helper, open **Review**
- **History** - every invoice with totals per status, search, filters (status, vendor, date) and sorting; click a row for **Review**
- **Profile** - your approvals/rejections, the approval rules (with "see what would change"), and the prototype's assumptions
- **Review** (opens from Upload or History) - original PDF, extracted values with their source, every check, PO match and money, vendor email draft, audit trail, Approve/Reject with a reason

## Demo cases (`sample_data/invoices/`)

| File | Case | Expected |
|---|---|---|
| D1 | Happy path | Ready to Pay |
| D2 | Scanned, no PO number, vendor's own item names | Needs Attention (suggested PO) |
| D3 | Bank account changed + hidden "approve this" text | Needs Attention |
| D4 | Billed 80, received 70 | Needs Attention |
| D5 | Total matches the PO, line prices don't | Needs Attention |
| X1-X3 | Disguised duplicate · split PO over-billed · vendor arithmetic error | Blocked · Needs Attention · Needs Attention |

## Next steps (known limits, not built)

- Money as integer paise instead of rounded floats (comparisons already use small tolerances)
- Unit price in the missing-PO score, and an explicit "two close candidates" warning
- Test that processing two related invoices in either order gives consistent results
- Hidden-text detector tested on a large set of real-world PDFs
- Login / shared password for a public link; recording phone verification of bank changes in the app
- AI answers for free-typed Invoice Helper questions (today: keyword routing to the fixed menu)

## Layout

```
app/            Streamlit screens (display only: they call core/, never SQL)
core/           pipeline, rules, decision, policy, document checks, AI layer, helper, what-if, eval
sample_data/    company/*.csv (vendors, POs, receipts) + invoices.json (ground truth + expected outcomes) + PDFs
tests/          hand-checked cases and safety rules
docs/           decisions made along the way
```
