"""Pydantic request/response schemas for the REST + SSE API.

Keep these in sync with `frontend/src/api/types.ts` -- that file is a
hand-written TypeScript mirror of this one.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

RunStatus = Literal["pending", "running", "awaiting_human", "completed", "rejected", "error"]
DocType = Literal["invoice", "receipt", "ledger", "unknown"]


class SampleDocument(BaseModel):
    id: str
    label: str
    doc_type: DocType


class SamplesResponse(BaseModel):
    samples: list[SampleDocument]


class RunCreateResponse(BaseModel):
    id: str
    status: RunStatus
    original_filename: str
    doc_type: DocType


class HumanDecisionRequest(BaseModel):
    decision: Literal["approve", "correct", "reject"]
    feedback: str = ""
    corrected_fields: dict[str, Any] | None = None


class TraceEventOut(BaseModel):
    node: str
    timestamp: datetime
    summary: str


class RunSummary(BaseModel):
    id: str
    original_filename: str
    doc_type: DocType
    status: RunStatus
    final_status: str | None
    # Derived for the Run History status badges ("clean" / "flagged" /
    # "duplicate"): `flagged` is true if any validation issue or
    # reconciliation finding is severity warning/error; `is_duplicate` is
    # true specifically when reconcile raised `duplicate_payment_suspected`.
    flagged: bool
    is_duplicate: bool
    created_at: datetime
    updated_at: datetime


class RunDetail(BaseModel):
    id: str
    original_filename: str
    doc_type: DocType
    status: RunStatus
    final_status: str | None
    extracted_fields: dict[str, Any]
    validation_issues: list[dict[str, Any]]
    reconciliation_findings: list[dict[str, Any]]
    trace: list[TraceEventOut]
    state_snapshot: dict[str, Any]
    error: str | None
    created_at: datetime
    updated_at: datetime


class RunListResponse(BaseModel):
    runs: list[RunSummary]
