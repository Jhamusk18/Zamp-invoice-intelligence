# Demo video script (final): under 5 minutes

**Structure:** for each outcome, say in one sentence which cases lead to it, then show one example live.
Ready to Pay → Needs Attention → Blocked (safe to dangerous).

**Before you press record**
- Open https://zamp-invoice-intelligence.streamlit.app and click through every page once, to wake it up.
- Go to **Profile → Reset demo data**.
- Have three files ready to drag in from `sample_data/test_invoices/`:
  - `D1_happy_path.pdf`
  - `D3_bank_change_injection.pdf`
  - `X1_duplicate.pdf`
- Use a full-screen browser at 100% zoom, and close other tabs and notifications.
- Speak slowly. If the AI takes a few seconds, keep talking about what the steps are doing.

---

## 1. The problem and the idea (0:00–0:35) · *Welcome page*

> "Hi, I'm Muskan. This is my solution for invoice processing, from PDF to decision.
>
> Accounts payable teams lose money in three ways: paying the wrong amount, paying the same bill twice, and paying a fraudster who changed the bank account.
>
> My tool checks every invoice before it's paid. The AI reads the invoice, fixed rules decide, and a person approves the exceptions. Every invoice gets one of three answers: **Ready to Pay**, **Needs Attention**, or **Blocked**. I'll show one example of each."

## 2. ✅ Ready to Pay (0:35–1:35) · *Upload page → `D1_happy_path.pdf`*

> "**Ready to Pay** means everything matches: an approved vendor, the right purchase order, the right price, goods received, and the same bank account as on file."

*Drop the file and click **Check invoice**. Point at the steps as they turn green.*

> "You can watch each step live. First, the AI **reads** the invoice: vendor, items, total, bank account. It also has to show *where* in the PDF it found each value, and my code checks that the value is really there. So if the AI invents a number, we catch it.
>
> Then plain rules, not AI, check it against our records: vendor list, purchase order, goods received, duplicates, bank account."

*Result appears: Ready to Pay. Click **"Why is it OK?"** in the chat.*

> "All checks passed, so it's **Ready to Pay**. The assistant on the right explains the result in simple words, but it can never approve or change anything."

## 3. ⚠️ Needs Attention (1:35–3:20) · *Upload `D3_bank_change_injection.pdf`*

> "**Needs Attention** is for problems a person can sort out with a quick check or a phone call. For example: the bank account changed, fewer goods arrived than were billed, a price is a little above the order, there's no PO number, or the vendor's maths is wrong."

*Click **Upload another**, drop D3 and click **Check invoice**.*

> "This invoice has two traps. The **bank account** is different from our records, which is the most common invoice fraud. And the PDF has **hidden white text** saying 'approve this invoice', written to trick an AI."

*Result appears: Needs Attention.*

> "The tool found the hidden text and ignored it. The trick can't work, because **the AI never makes the decision**. It also says what to do next: call the vendor on the phone number **in our records** before paying."

*Click **Open full review**.*

> "On the review page, the PDF is on the left and our result is on the right. A person makes the final call, and they **must write a reason**."

*Type in the note box:* **Called vendor on our number – they did not change their bank. Fraud attempt.**
*Choose **Blocked**, then click **Save review**.*

> "I called the vendor, and they never changed their bank, so I'll block it. The email below updates to match my decision. I can copy it or open it in Gmail. Nothing is sent automatically, and every action is saved in a history that can't be edited."

## 4. ⛔ Blocked (3:20–4:20) · *Upload `X1_duplicate.pdf`*

> "**Blocked** is for invoices that should never be paid with one click: a duplicate, a blocked or unknown vendor, a fake lookalike vendor, a price far above the order, or a document that isn't an invoice at all, like a quotation."

*Drop X1 and click **Check invoice**.*

> "This vendor already sent invoice **INV-0042**, and we paid it. Now the same bill has come back as just **'42'**, so a simple search wouldn't catch it."

*Result appears: Blocked.*

> "The tool cleans up the invoice number, sees it's the same bill, and **Blocks** it, so we don't pay twice. I also made sure normal monthly bills with the same amount are *not* flagged as duplicates."

## 5. History (4:20–4:50) · *History page*

> "The History page shows every invoice we've checked: how many are ready, need attention or are blocked, and who decided, the rules or a person. The approval limits are settings the finance team controls, and the bank and duplicate rules are locked."

## 6. Close (4:50–5:00)

> "So, **the AI reads, fixed rules decide, and a person approves the exceptions**. It's fast, it's safe, and every decision can be explained. Thank you!"

---

**If you're running long:** cut the History section to one sentence.
**If something is slow or fails on a take:** stop and re-record that part. Only the final video counts.
