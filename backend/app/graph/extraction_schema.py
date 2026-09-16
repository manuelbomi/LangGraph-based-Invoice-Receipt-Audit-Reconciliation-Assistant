"""Pydantic schema used for LLM structured-output field extraction.

Passed to `chat_model.with_structured_output(ExtractedDocument)` in
`extract_fields_node` -- this is what lets one schema generalize across
invoices with meaningfully different layouts (see `sample-data/README.md`)
and across the text (PDF) vs. vision (receipt image) extraction paths.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractedLineItem(BaseModel):
    description: str = Field(description="What this line item is for.")
    quantity: float = Field(description="Quantity / count for this line item.")
    unit_price: float = Field(description="Price per unit, in the document's currency.")
    amount: float = Field(description="quantity * unit_price for this line item.")


class ExtractedDocument(BaseModel):
    vendor: str = Field(description="The vendor/merchant name issuing this document.")
    document_number: str = Field(
        default="", description="Invoice or receipt number, if present. Empty string if absent."
    )
    document_date: str = Field(
        description="The document's date, normalized to ISO 8601 'YYYY-MM-DD'."
    )
    line_items: list[ExtractedLineItem] = Field(
        default_factory=list, description="Every line item / purchased item on the document."
    )
    subtotal: float = Field(description="Subtotal before tax.")
    tax: float = Field(default=0.0, description="Total tax amount. 0 if none/tax-exempt.")
    total: float = Field(description="Grand total, including tax.")
    currency: str = Field(default="USD", description="ISO currency code, e.g. USD, EUR.")
