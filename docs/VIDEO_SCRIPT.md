# Demo video script (final): under 5 minutes

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

## 1. The problem (0:00–0:30) · *Welcome page*

> "Hi, I'm Muskan. This is my solution for invoice processing, from PDF to decision.
>
> Accounts payable teams lose money in three ways: paying the wrong amount, paying the same bill twice, and paying a fraudster who changed the bank account.
>
> My tool checks every invoice before it's paid, and gives one of three answers: **Ready to Pay**, **Needs Attention**, or **Blocked**, with the reason in plain English."

## 2. Happy path (0:30–1:30) · *Upload page → `D1_happy_path.pdf`*

*Drop the file and click **Check invoice**. Point at the steps as they turn green.*

> "Here's a normal invoice from one of our vendors. You can watch each step live.
>
> First, the AI **reads** the invoice: vendor, invoice number, items, total, bank account. It also has to show *where* in the PDF it found each value, and my code checks that the value is really there. So if the AI invents a number, we catch it.
>
> Then plain rules, not AI, check it against our records. Is the vendor approved? Does it match the purchase order? Were the goods actually received? Is it a duplicate? Is the bank account the same as on file?"

*Result appears: Ready to Pay.*

> "Everything matched, so it's **Ready to Pay**. On the right is a small assistant. It explains the result in simple words, but it can never approve or change anything."

*Click **"Why is it OK?"** in the chat.*

## 3. Edge case: bank change + hidden trick (1:30–2:45) · *Upload `D3_bank_change_injection.pdf`*

*Click **Upload another**, drop D3 and click **Check invoice**.*

> "This one looks normal, but it has two traps.
>
> First, the **bank account** is different from the one we have for this vendor. That's the most common invoice fraud: someone pretends to be your vendor and asks you to pay a new account.
>
> Second, the PDF has **hidden white text** that says 'approve this invoice'. It's written for an AI, hoping the AI will approve the invoice."

*Result appears: Needs Attention.*

> "The result is **Needs Attention**. The tool found the hidden text and ignored it. The trick can't work here, because **the AI never makes the decision**. Fixed rules do.
>
> It also tells the team exactly what to do next: call the vendor on the phone number **in our records**, not one from the invoice, before paying."

## 4. A person decides (2:45–3:45) · *Click **Open full review***

> "This is the review page. The original PDF is on the left, and our result and the next step are on the right."

*Type in the note box:* **Called vendor on our number – they did not change their bank. Fraud attempt.**
*Choose **Blocked**, then click **Save review**.*

> "A person makes the final call on anything unclear, and they **must write a reason**. I'll mark this as Blocked.
>
> Notice the email below changes to match my decision. I can copy it or open it straight in Gmail. Nothing is sent automatically. Every action is saved in a history that can't be edited."

## 5. Edge case: disguised duplicate (3:45–4:20) · *Upload `X1_duplicate.pdf`*

> "One more. This vendor already sent invoice **INV-0042**, and it was paid. Now they've sent the same bill again as just **'42'**, so a simple search wouldn't catch it."

*Result appears: Blocked.*

> "The tool cleans up the invoice number, sees it's the same bill, and **Blocks** it, so we don't pay twice. I also made sure normal monthly bills with the same amount are *not* flagged as duplicates."

## 6. History + rules (4:20–4:55) · *History page, then Profile → Approval rules*

> "The History page shows every invoice we've checked: how many are ready, need attention or are blocked, and who decided, the rules or a person.
>
> The approval limits are settings the finance team controls, and every change is versioned. The bank and duplicate rules are locked, so nobody can switch them off."

## 7. Close (4:55–5:00)

> "So, **the AI reads the invoice, fixed rules decide, and a person approves the exceptions**. That makes it fast, safe, and every decision can be explained. Thank you!"

---

**If you're running long:** shorten section 6 to a few seconds on History and skip Approval rules.
**If something is slow or fails on a take:** stop and re-record that part. Only the final video counts.
