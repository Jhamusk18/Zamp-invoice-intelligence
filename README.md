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

## Layout

```
app/            Streamlit screens (display only: they call core/, never SQL)
core/           pipeline, rules, decision, policy, document checks, AI layer, helper, what-if, eval
sample_data/    company/*.csv (vendors, POs, receipts) + invoices.json (ground truth + expected outcomes) + PDFs
tests/          hand-checked cases and safety rules
docs/           decisions made along the way
```
