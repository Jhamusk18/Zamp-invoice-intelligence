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
| `X4_blocked_vendor.pdf` | New invoice from Orion Print House, a vendor blocked in the vendor master | ⛔ Blocked |
| `X5_unknown_vendor.pdf` | Invoice from "Quickfix Hardware Mart", not on the approved vendor list | ⛔ Blocked |
| `X6_lookalike_vendor.pdf` | "Globex **Frieght** Services LLP" - lookalike name, different GSTIN and bank, billing a real Globex PO | ⛔ Blocked |
| `X7_price_over_limit.pdf` | Ceiling fans at ₹2,950 vs PO ₹2,750 (+7.3%, above the 5% block limit) | ⛔ Blocked |
| `X8_quotation_not_invoice.pdf` | A QUOTATION, not an invoice - nothing is payable | ⛔ Blocked |
| `X9_bundled_line.pdf` | PO has 6 desks + 6 chairs; invoice bills one line "Workstation set (desk + chair)" at the combined price | ⚠️ Needs Attention (bundled line - check against the order items) |
| `X10_two_close_pos.pdf` | No PO number, and two open orders of this vendor fit almost equally | ⚠️ Needs Attention (person chooses the PO; nothing reserved) |

Uploading the same file twice shows the earlier result. Use **Profile → Reset demo data** to run them fresh.
