"""Money helpers. All amounts are rupees as floats rounded to 2 decimals; comparisons use a small epsilon."""


def r2(x):
    return None if x is None else round(float(x) + 0.0, 2)


def inr(amount, symbol=True, decimals=2):
    """Indian digit grouping: 113200 -> '₹1,13,200.00'."""
    if amount is None:
        return "—"
    neg = amount < 0
    s = f"{abs(amount):.{decimals}f}"
    whole, _, frac = s.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    out = whole + (f".{frac}" if decimals else "")
    return ("-" if neg else "") + ("₹" if symbol else "") + out


def mask_account(acct):
    if not acct:
        return "—"
    digits = str(acct)
    return "•••• " + digits[-4:]
