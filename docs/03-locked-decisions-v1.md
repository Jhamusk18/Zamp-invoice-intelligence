# PS-1 Zamp AP Assistant — Locked Decisions (v1)

## How it works, in plain words
1. User drops a PDF. Backend checks it is really a PDF (file contents, not extension), computes a SHA-256 fingerprint. **Same file seen before → show the old result, no reprocessing.**
2. Backend saves the file and returns an invoice ID immediately. The screen polls for progress (~every 0.5 s).
3. Backend reads the text layer (or OCRs a scan). AI turns it into fields, each with a source snippet.
4. Python checks every snippet against the document text (or OCR text), checks the numbers add up, and asks the AI to re-read **once** if they don't.
5. Python runs **all** business checks against vendor, PO and goods-receipt records and collects **every** finding.
6. Python sets the status and updates the PO money state: APPROVED deducts, FLAGGED reserves, REJECTED releases. Idempotent: never twice.
7. AI writes the explanation and vendor email from the findings ledger only.
8. Screen shows the verdict. Reviewer opens the Review page, reads the checks, and approves or rejects **with a required reason**. Saved in the append-only audit trail.

## Status names (one set, everywhere)
| Backend value | Screen label | Colour |
|---|---|---|
| `APPROVED` | Ready to Pay | green |
| `FLAGGED` | Needs Attention | amber |
| `REJECTED` | Blocked | red |

- Severity order: `REJECTED > FLAGGED > APPROVED`. The most severe finding wins; all reasons are listed.
- The red status is labelled "Blocked" everywhere (landing, dashboard cards, filters, badges). Updated per user decision.
- `decided_by` = `system` or `reviewer`, so the screen can show "Ready to Pay · auto" vs "Ready to Pay · approved by reviewer".

## Two kinds of failure
| Type | Examples | Effect |
|---|---|---|
| **Technical failure** | Corrupt file, password-protected, unreadable, AI/OCR API down | **Stops the run.** Stage shows *failed* with a clear error. Run state = `ERROR` (not a decision). No PO money touched. User can retry. |
| **Business finding** | Bank differs, duplicate, over tolerance, math doesn't add up, unverified snippet, two reads disagree | **Never stops the run.** Every check still runs; all findings are collected; the decision is made at the end. |

## Bank number masking
Show the last 4 digits and mask the rest, plus an explicit word: `•••• 3210 vs •••• 7890 — differs`. Never hide completely.

## Removed / deferred
- **Confidence scores: removed.** Field trust is shown as verification status instead: `Verified (text)` / `Verified (OCR)` / `Not verified`. A critical field that is `Not verified` → FLAGGED.
- **"Verified by phone" confirmation UI: deferred (later addition).** First build: approving a bank-mismatch invoice requires a reason like any other override.

## Exact duplicate file vs duplicate invoice
- Same **file** (same fingerprint) → return the existing result. Not a new invoice.
- Same **invoice**, different file (re-scan, `INV-0042` vs `42`) → processed, the duplicate check fires → REJECTED.
