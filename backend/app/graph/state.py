"""Graph state schema.

A `TypedDict` (LangGraph's preferred state shape) rather than a Pydantic
model, so partial node returns (`{"vendor": "..."}`) merge cleanly via
LangGraph's default "last write wins per key" reducer. Only `trace`
accumulates (via an `operator.add` reducer) since every other field is
written exactly once per run (this graph has no revision loops -- a human
correction is applied inline in `human_review_node`, not by looping back).
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class LineItem(TypedDict):
    description: str
    quantity: float
    unit_price: float
    amount: float


class ValidationIssue(TypedDict):
    code: str
    severity: str  # "error" | "warning"
    message: str


class ReconciliationFinding(TypedDict):
    code: str
    severity: str  # "info" | "warning" | "error"
    message: str
    details: dict[str, Any]


class TraceEvent(TypedDict):
    node: str
    timestamp: str
    summary: str


class AuditState(TypedDict, total=False):
    # --- input ---
    file_path: str
    original_filename: str

    # --- ingest ---
    doc_type: str  # "invoice" | "receipt" | "ledger"
    raw_text: str  # PDF-extracted text (invoices)
    image_base64: str  # receipt image, base64-encoded (receipts)
    ledger_rows_loaded: int  # ledger uploads only

    # --- extract_fields ---
    vendor: str
    document_number: str
    document_date: str  # ISO "YYYY-MM-DD"
    line_items: list[LineItem]
    subtotal: float
    tax: float
    total: float
    currency: str

    # --- validate (deterministic) ---
    validation_issues: list[ValidationIssue]

    # --- reconcile (deterministic, cross-checked against Postgres ledger) ---
    reconciliation_findings: list[ReconciliationFinding]
    ledger_match_id: int | None
    is_duplicate: bool
    requires_approval: bool

    # --- human review ---
    human_decision: str  # "approve" | "correct" | "reject" | ""
    human_feedback: str
    corrected_fields: dict[str, Any]

    # --- finalize ---
    final_status: str  # "posted" | "corrected_posted" | "rejected" | "ledger_loaded"
    status: str  # mirrors app.db.models.Run.status

    # --- observability (appended to, not replaced) ---
    trace: Annotated[list[TraceEvent], operator.add]
