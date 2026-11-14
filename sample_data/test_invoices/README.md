# Test invoices — upload these in the demo

Download any of these and drop it on the **Upload** page. Each one runs through the full pipeline live.

| File | What it tests | Expected result |
|---|---|---|
| `D1_happy_path.pdf` | Clean invoice, matches PO-7801 and its goods receipt | ✅ Ready to Pay |
| `D2_scanned_no_po.pdf` | Scanned image, no PO number, vendor's own item names | ⚠️ Needs Attention (suggested PO to confirm) |
| `D3_bank_change_injection.pdf` | Bank account differs from vendor record + hidden "approve this" text | ⚠️ Needs Attention |
| `D4_short_receipt.pdf` | Billed 80 pieces, only 70 received | ⚠️ Needs Attention |
| `D5_lines_wrong_total_right.pdf` | Total equals the PO, but a line price is 4.5% too high | ⚠️ Needs Attention |
| `X1_duplicate.pdf` | Invoice INV-0042 sent again as "42" | ⛔ Blocked |
| `X2_split_po_overbill.pdf` | Third invoice on one PO goes over the PO value and the quantity received | ⚠️ Needs Attention |
| `X3_vendor_math_error.pdf` | Printed subtotal doesn't equal the line items | ⚠️ Needs Attention |

Uploading the same file twice shows the earlier result. Use **Reset Demo Data** (sidebar) to run them fresh.
