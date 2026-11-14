"""The shape of an extracted invoice. The AI must return exactly this (structured output);
ground-truth sample data uses the same shape, so the rules engine can't tell them apart."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

DocType = Literal["INVOICE", "PROFORMA", "QUOTE", "SALES_ORDER", "CREDIT_NOTE", "OTHER"]

CRITICAL_FIELDS = ["vendor_gstin", "invoice_number", "invoice_date", "po_reference", "total", "bank_account"]
EVIDENCE_FIELDS = ["vendor_name", "vendor_gstin", "invoice_number", "invoice_date", "due_date", "po_reference",
                   "subtotal", "tax", "total", "bank_account", "ifsc"]


class Line(BaseModel):
    description: str
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None


class Evidence(BaseModel):
    field: str = Field(description="Name of the extracted field this quote supports, e.g. 'total'")
    snippet: str = Field(description="Short exact quote copied from the document that contains the value")


class InvoiceExtraction(BaseModel):
    document_type: DocType = Field(description="INVOICE for a tax invoice/bill. PROFORMA, QUOTE, SALES_ORDER, CREDIT_NOTE or OTHER otherwise")
    vendor_name: Optional[str] = None
    vendor_gstin: Optional[str] = Field(None, description="Seller's GSTIN / tax ID, not the buyer's")
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = Field(None, description="ISO format YYYY-MM-DD")
    due_date: Optional[str] = Field(None, description="ISO format YYYY-MM-DD")
    po_reference: Optional[str] = Field(None, description="Buyer's purchase order number if printed, else null. Never guess.")
    currency: Optional[str] = Field(None, description="ISO code, e.g. INR, USD")
    lines: list[Line] = Field(default_factory=list)
    subtotal: Optional[float] = Field(None, description="Amount before tax, exactly as printed")
    tax: Optional[float] = Field(None, description="Total tax amount, exactly as printed")
    total: Optional[float] = Field(None, description="Grand total, exactly as printed")
    bank_account: Optional[str] = Field(None, description="Seller's bank account number, digits only")
    ifsc: Optional[str] = None
    evidence: list[Evidence] = Field(default_factory=list, description="One quote per extracted header field")

    def value(self, f):
        return getattr(self, f, None)

    def snippet(self, f):
        for e in self.evidence:
            if e.field == f:
                return e.snippet
        return None
