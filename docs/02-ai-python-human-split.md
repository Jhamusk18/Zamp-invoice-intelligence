# PS-1 Invoice Processing — Who does what: AI vs Python vs Human

Status: **Final (v1)**. Decision states: **Approved / Flagged / Rejected**.

| Job | Who | Why |
|---|---|---|
| Read the PDF or scan into fields (vendor, number, date, PO reference, line items, total, bank account) | **AI** (multimodal model, text layer first, vision for scans) | Layouts vary too much for fixed rules |
| Give a source text snippet for each field | **AI** | The snippet is then verified by Python |
| Check the snippet exists in the PDF text | **Python** | Catches invented values |
| Scan for hidden text (tiny or white font) | **Python** | Deterministic, and doesn't depend on the model |
| Check items add up to subtotal and subtotal plus tax equals total | **Python** | Math must never come from the model |
| Retry extraction once if the math doesn't add up | **Python decides to retry, AI re-reads** | Retry is triggered by a failed check |
| Judge whether a description matches a PO item (missing PO case) | **AI** | Language meaning |
| Score amount, date and unit price for PO candidates | **Python** | Arithmetic |
| Duplicate and fuzzy duplicate checks | **Python** | Exact and string-similarity rules |
| Vendor approved, blocked or lookalike | **Python** | Lookup against the vendor table |
| PO open or closed, balance, tolerance bands | **Python** | Money rules |
| Billed quantity vs received (three-way match) | **Python** | Exact comparison |
| Bank or remit-to differs from vendor record | **Python** | Fraud rule, must be exact |
| Currency, date, expiry, tax ID checks | **Python** | Deterministic |
| Collect all findings into the evidence ledger | **Python** | Audit trail |
| **Final status** (Approved, Flagged, Rejected) | **Python** | Repeatable, never the model |
| Reserve or deduct PO balance | **Python** | Money state change |
| Write the plain-language explanation | **AI**, from the ledger only | Language task, numbers verified against the ledger |
| Draft the vendor email | **AI**, from the ledger only | Same |
| Answer Invoice Helper menu questions | **Python templates** (no model) | Stored data, zero cost |
| Answer free-typed helper questions | **AI**, restricted to stored records | Only when no menu item matches |
| Review a flagged invoice | **Human** | Judgment and accountability |
| **Approve anyway or Reject, with a reason** | **Human** | The model never decides |
| Confirm a proposed PO match | **Human** | An inferred match is never auto-approved |
| Verify a bank change by phone | **Human** | Out-of-band verification |
| Send the vendor email | **Human** (one click, or copy-paste) | Nothing is sent automatically |
| Correct a wrong extraction (memory feature) | **Human** | Only confirmed corrections are stored |
| Change tolerance and other policy values | **Human** | Business decision |

**Rule of thumb:** AI handles language and ambiguity, Python handles exactness and every money decision, and a human handles judgment and anything that moves money or goes outside.

## Guardrails
1. The AI never sees the decision it could influence. It reads and explains, while Python decides.
2. Memory and chat can add hints or stricter flags, but never skip a check or approve.

## Clarifications to close (proposed)
1. **Snippet check on scans:** scans have no text layer. Run local OCR (Tesseract) as an independent reference and fuzzy-match snippets against it. If a critical field (total, invoice no., bank, PO) can't be verified, the invoice is Flagged as `UNVERIFIED_FIELD`.
2. **After a failed retry:** if the second read gives the same numbers and the snippets verify, the vendor's invoice is wrong (not the extraction). Flag it as `VENDOR_MATH_ERROR` and draft a vendor email. If the two reads disagree, flag it as `EXTRACTION_UNSTABLE`.
3. **AI PO-description match:** it returns a score plus a reason, and Python treats it as one input to the candidate score. Any inferred PO is always Flagged, never Approved.
4. **Three-way match:** needs a goods-receipt (GRN) table in the dataset. Service lines have no receipt, so they use a two-way match.
5. **PO balance lifecycle:** Approved = deduct. Flagged = soft-reserve (counts against the balance for later invoices, so concurrent split invoices can't overbill). Rejected (by the system or a human) = release. Human "approve anyway" = deduct. Reprocessing the same invoice must never deduct twice (idempotent).
6. **Approve anyway on high-risk flags:** for bank mismatches, the phone verification must be recorded (who, number called, time) before the Approve button is enabled.
7. **Numbers in AI text:** Python checks that every number in the explanation or email appears in the ledger. If any doesn't, fall back to a template.
8. **Memory corrections:** stored as per-vendor extraction hints. A corrected value still has to pass the snippet check.
