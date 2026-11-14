# History invoices — already in the app, don't upload these

These 8 past invoices are loaded into **History** automatically (at first start and on **Reset Demo Data**), so the
dashboard isn't empty and some test cases have something to compare against (e.g. `H2` is the original that
`X1_duplicate` repeats; `H3`/`H4` are the earlier invoices on the PO that `X2` over-bills).

They go through the same rules engine as uploads; the only difference is their values come from the known ground truth
in `sample_data/invoices.json` instead of an AI read. Nothing is "trained" on them.
