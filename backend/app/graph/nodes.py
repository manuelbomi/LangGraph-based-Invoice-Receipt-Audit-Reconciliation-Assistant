"""LangGraph node implementations for the Invoice & Receipt Audit /
Reconciliation Assistant.

Six real (non-stub) nodes:
  ingest          - detects document type, extracts raw text/structure
                     (pdfplumber for PDFs, base64 for images so a vision LLM
                     can read them, pandas/openpyxl for the ledger)
  extract_fields  - LLM structured-output extraction (text or vision)
  validate        - deterministic arithmetic/required-field/date checks
  reconcile       - deterministic cross-check against the Postgres ledger:
                     match, duplicate-payment detection, policy threshold
  human_review    - interrupt() pauses the graph for an accountant's decision
  finalize        - records the audited outcome
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage
from langgraph.types import interrupt

from app.config import get_settings
from app.graph.extraction_schema import ExtractedDocument
from app.graph.state import AuditState, TraceEvent
from app.llm import get_chat_model
from app.prompts import render_prompt
from app.tools.document_ingest import (
    detect_doc_type,
    encode_image_base64,
    extract_pdf_text,
    image_mime_type,
)
from app.tools.ledger import find_ledger_match, find_near_duplicate_ledger_entries, load_ledger_from_excel

logger = logging.getLogger(__name__)

# Public so the API layer (app/api/routers/runs.py) can project the same
# set of fields out of a run's state snapshot into `Run.extracted_fields`.
EXTRACTED_FIELD_KEYS = (
    "vendor",
    "document_number",
    "document_date",
    "line_items",
    "subtotal",
    "tax",
    "total",
    "currency",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trace(node: str, summary: str) -> list[TraceEvent]:
    return [{"node": node, "timestamp": _now(), "summary": summary}]


# --------------------------------------------------------------------------
# 1. ingest
# --------------------------------------------------------------------------
async def ingest_node(state: AuditState) -> dict:
    file_path = state["file_path"]
    doc_type = detect_doc_type(file_path)

    if doc_type == "invoice":
        raw_text = extract_pdf_text(file_path)
        return {
            "doc_type": doc_type,
            "raw_text": raw_text,
            "trace": _trace("ingest", f"Detected invoice PDF; extracted {len(raw_text)} chars of text."),
        }

    if doc_type == "receipt":
        image_b64 = encode_image_base64(file_path)
        return {
            "doc_type": doc_type,
            "image_base64": image_b64,
            "trace": _trace("ingest", "Detected receipt image; encoded for vision extraction."),
        }

    # doc_type == "ledger": deterministic parse + load, no LLM involved.
    rows_loaded = load_ledger_from_excel(file_path, replace=True)
    return {
        "doc_type": doc_type,
        "ledger_rows_loaded": rows_loaded,
        "trace": _trace("ingest", f"Loaded general ledger: {rows_loaded} row(s) into Postgres."),
    }


def route_after_ingest(state: AuditState) -> str:
    """A ledger upload has nothing to extract/validate/reconcile/review --
    it deterministically replaces the ledger table in `ingest_node` itself,
    so it routes straight to `finalize`. Invoices and receipts go through
    the full extraction/audit pipeline."""
    if state.get("doc_type") == "ledger":
        return "finalize"
    return "extract_fields"


# --------------------------------------------------------------------------
# 2. extract_fields
# --------------------------------------------------------------------------
def _empty_fields() -> dict:
    return {
        "vendor": "",
        "document_number": "",
        "document_date": "",
        "line_items": [],
        "subtotal": 0.0,
        "tax": 0.0,
        "total": 0.0,
        "currency": "USD",
    }


async def extract_fields_node(state: AuditState) -> dict:
    llm = get_chat_model()
    structured_llm = llm.with_structured_output(ExtractedDocument)

    try:
        if state.get("doc_type") == "receipt":
            prompt_text = render_prompt("extract_fields_vision")
            mime = image_mime_type(state["file_path"])
            message = HumanMessage(
                content=[
                    {"type": "text", "text": prompt_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{state['image_base64']}"},
                    },
                ]
            )
            result = await structured_llm.ainvoke([message])
        else:
            prompt_text = render_prompt("extract_fields_text", raw_text=state.get("raw_text", ""))
            result = await structured_llm.ainvoke(prompt_text)
        fields = result.model_dump()
    except Exception as exc:  # noqa: BLE001
        logger.exception("extract_fields_node: extraction failed")
        fields = _empty_fields()
        return {
            **fields,
            "trace": _trace("extract_fields", f"Extraction failed ({exc.__class__.__name__}); left fields empty."),
        }

    summary = (
        f"Extracted vendor={fields['vendor']!r}, total={fields['total']}, "
        f"{len(fields['line_items'])} line item(s)."
    )
    return {**fields, "trace": _trace("extract_fields", summary)}


# --------------------------------------------------------------------------
# 3. validate (deterministic)
# --------------------------------------------------------------------------
_ALLOWED_CURRENCIES = {"USD", "EUR", "GBP", "CAD", "AUD"}
_AMOUNT_TOLERANCE = 0.01
_MIN_PLAUSIBLE_YEAR = 2000


async def validate_node(state: AuditState) -> dict:
    issues: list[dict] = []

    line_items = state.get("line_items") or []
    subtotal = state.get("subtotal")
    tax = state.get("tax") or 0.0
    total = state.get("total")
    vendor = state.get("vendor")
    document_date = state.get("document_date")
    currency = state.get("currency")

    if line_items:
        computed_subtotal = round(sum(li.get("amount", 0.0) for li in line_items), 2)
        if subtotal is not None and abs(computed_subtotal - subtotal) > _AMOUNT_TOLERANCE:
            issues.append(
                {
                    "code": "line_items_subtotal_mismatch",
                    "severity": "error",
                    "message": (
                        f"Line items sum to {computed_subtotal:.2f} but the stated "
                        f"subtotal is {subtotal:.2f}."
                    ),
                }
            )
    else:
        issues.append(
            {"code": "no_line_items", "severity": "warning", "message": "No line items were extracted."}
        )

    if subtotal is not None and total is not None:
        expected_total = round(subtotal + tax, 2)
        if abs(expected_total - total) > _AMOUNT_TOLERANCE:
            issues.append(
                {
                    "code": "total_mismatch",
                    "severity": "error",
                    "message": (
                        f"Subtotal + tax = {expected_total:.2f} but the stated total is {total:.2f}."
                    ),
                }
            )

    for field_name, value in (("vendor", vendor), ("document_date", document_date), ("total", total)):
        if value in (None, ""):
            issues.append(
                {
                    "code": f"missing_{field_name}",
                    "severity": "error",
                    "message": f"Required field '{field_name}' is missing.",
                }
            )

    if document_date:
        try:
            parsed = datetime.strptime(document_date, "%Y-%m-%d").date()
            today = datetime.now(timezone.utc).date()
            if parsed > today:
                issues.append(
                    {
                        "code": "future_date",
                        "severity": "error",
                        "message": f"Document date {document_date} is in the future.",
                    }
                )
            elif parsed.year < _MIN_PLAUSIBLE_YEAR:
                issues.append(
                    {
                        "code": "implausible_date",
                        "severity": "warning",
                        "message": f"Document date {document_date} seems implausible.",
                    }
                )
        except ValueError:
            issues.append(
                {
                    "code": "unparseable_date",
                    "severity": "error",
                    "message": f"Could not parse document date {document_date!r} as YYYY-MM-DD.",
                }
            )

    if currency and currency.upper() not in _ALLOWED_CURRENCIES:
        issues.append(
            {
                "code": "unusual_currency",
                "severity": "warning",
                "message": f"Currency {currency!r} is unusual for this ledger; please verify.",
            }
        )

    severities = ", ".join(sorted({i["severity"] for i in issues})) or "none"
    return {
        "validation_issues": issues,
        "trace": _trace("validate", f"{len(issues)} validation issue(s) found (severities: {severities})."),
    }


# --------------------------------------------------------------------------
# 4. reconcile (deterministic, cross-checked against Postgres)
# --------------------------------------------------------------------------
async def reconcile_node(state: AuditState) -> dict:
    settings = get_settings()
    vendor = state.get("vendor")
    total = state.get("total")
    document_date = state.get("document_date")

    findings: list[dict] = []

    match = find_ledger_match(vendor, total, document_date)
    ledger_match_id = match.id if match else None
    if match is None:
        findings.append(
            {
                "code": "no_ledger_match",
                "severity": "warning",
                "message": (
                    f"No ledger entry found matching vendor={vendor!r}, amount={total}, "
                    f"date near {document_date}. This document may need to be coded to the "
                    "GL manually."
                ),
                "details": {},
            }
        )
    else:
        findings.append(
            {
                "code": "ledger_match_found",
                "severity": "info",
                "message": (
                    f"Matched ledger entry #{match.id}: {match.vendor}, {match.amount:.2f} "
                    f"{match.currency} on {match.date.isoformat()} ({match.gl_account})."
                ),
                "details": {"ledger_entry_id": match.id, "gl_account": match.gl_account},
            }
        )

    duplicates = find_near_duplicate_ledger_entries(
        vendor, total, document_date, exclude_id=ledger_match_id
    )
    is_duplicate = bool(duplicates)
    if duplicates:
        dup_desc = "; ".join(f"#{d.id} on {d.date.isoformat()}" for d in duplicates)
        findings.append(
            {
                "code": "duplicate_payment_suspected",
                "severity": "error",
                "message": (
                    f"Possible duplicate payment: {len(duplicates)} other ledger entr"
                    f"{'y' if len(duplicates) == 1 else 'ies'} for the same vendor and amount "
                    f"within {settings.duplicate_date_window_days} days ({dup_desc})."
                ),
                "details": {"duplicate_ledger_ids": [d.id for d in duplicates]},
            }
        )

    requires_approval = total is not None and total > settings.policy_approval_threshold
    if requires_approval:
        findings.append(
            {
                "code": "exceeds_policy_threshold",
                "severity": "warning",
                "message": (
                    f"Total {total:.2f} exceeds the ${settings.policy_approval_threshold:,.2f} "
                    "policy threshold and requires additional approval before posting."
                ),
                "details": {"threshold": settings.policy_approval_threshold},
            }
        )

    return {
        "reconciliation_findings": findings,
        "ledger_match_id": ledger_match_id,
        "is_duplicate": is_duplicate,
        "requires_approval": bool(requires_approval),
        "trace": _trace(
            "reconcile",
            f"{len(findings)} finding(s); matched={'yes' if match else 'no'}; "
            f"duplicate={is_duplicate}; requires_approval={bool(requires_approval)}.",
        ),
    }


# --------------------------------------------------------------------------
# 5. human_review
# --------------------------------------------------------------------------
def _extracted_fields_snapshot(state: AuditState) -> dict:
    return {key: state.get(key) for key in EXTRACTED_FIELD_KEYS}


async def human_review_node(state: AuditState) -> dict:
    """Pause the graph and wait for an accountant's decision.

    `interrupt()` raises a `GraphInterrupt` the first time this node runs
    for a given thread; LangGraph's Postgres checkpointer persists state up
    to (but not including) this node's completion, so the process can exit
    entirely and be resumed later via `Command(resume=...)` against the
    same `thread_id` -- see `app/api/routers/runs.py::resume_run`. This is
    the point of the whole design: a financial posting should never happen
    without a human explicitly approving it, and that human should be able
    to work through a queue of documents over hours or days without losing
    anything.
    """
    decision_payload = interrupt(
        {
            "original_filename": state.get("original_filename"),
            "doc_type": state.get("doc_type"),
            "extracted_fields": _extracted_fields_snapshot(state),
            "validation_issues": state.get("validation_issues", []),
            "reconciliation_findings": state.get("reconciliation_findings", []),
        }
    )
    decision = str(decision_payload.get("decision", "approve")).lower()
    feedback = str(decision_payload.get("feedback", ""))
    corrected_fields = decision_payload.get("corrected_fields") or {}
    if decision not in {"approve", "correct", "reject"}:
        decision = "approve"

    update: dict = {
        "human_decision": decision,
        "human_feedback": feedback,
        "trace": _trace("human_review", f"Human decision={decision} | {feedback[:200]}"),
    }

    if decision == "correct" and corrected_fields:
        for key in EXTRACTED_FIELD_KEYS:
            if key in corrected_fields and corrected_fields[key] not in (None, ""):
                update[key] = corrected_fields[key]
        update["corrected_fields"] = corrected_fields

    return update


# --------------------------------------------------------------------------
# 6. finalize
# --------------------------------------------------------------------------
async def finalize_node(state: AuditState) -> dict:
    if state.get("doc_type") == "ledger":
        rows = state.get("ledger_rows_loaded", 0)
        return {
            "final_status": "ledger_loaded",
            "status": "completed",
            "trace": _trace("finalize", f"General ledger reloaded: {rows} row(s)."),
        }

    decision = state.get("human_decision", "approve")
    if decision == "reject":
        final_status, status = "rejected", "rejected"
    elif decision == "correct":
        final_status, status = "corrected_posted", "completed"
    else:
        final_status, status = "posted", "completed"

    return {
        "final_status": final_status,
        "status": status,
        "trace": _trace("finalize", f"Document finalized with status={final_status}."),
    }
