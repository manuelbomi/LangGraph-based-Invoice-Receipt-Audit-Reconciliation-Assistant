"""Unit tests for individual graph nodes and routing functions.

Everything here is mocked: LLM calls go through `FakeChatModel` (see
conftest.py), and ledger I/O is monkeypatched via the `no_ledger_io`
fixture. No network, no Postgres, no API key spend.
"""
from __future__ import annotations

from app.graph import nodes
from app.graph.extraction_schema import ExtractedDocument, ExtractedLineItem
from app.tools.ledger import LedgerMatch
from datetime import date


def _match(id_=1, vendor="Acme Corp", amount=100.0, day=5) -> LedgerMatch:
    return LedgerMatch(
        id=id_,
        date=date(2026, 8, day),
        vendor=vendor,
        description="desc",
        gl_account="6100-Test",
        amount=amount,
        currency="USD",
    )


# ---------------------------------------------------------------------
# ingest_node / route_after_ingest
# ---------------------------------------------------------------------
async def test_ingest_node_pdf(monkeypatch):
    monkeypatch.setattr(nodes, "detect_doc_type", lambda p: "invoice")
    monkeypatch.setattr(nodes, "extract_pdf_text", lambda p: "INVOICE TEXT HERE")

    result = await nodes.ingest_node({"file_path": "some.pdf"})

    assert result["doc_type"] == "invoice"
    assert result["raw_text"] == "INVOICE TEXT HERE"
    assert len(result["trace"]) == 1


async def test_ingest_node_receipt(monkeypatch):
    monkeypatch.setattr(nodes, "detect_doc_type", lambda p: "receipt")
    monkeypatch.setattr(nodes, "encode_image_base64", lambda p: "YmFzZTY0Zm9v")

    result = await nodes.ingest_node({"file_path": "some.png"})

    assert result["doc_type"] == "receipt"
    assert result["image_base64"] == "YmFzZTY0Zm9v"


async def test_ingest_node_ledger(monkeypatch, no_ledger_io):
    monkeypatch.setattr(nodes, "detect_doc_type", lambda p: "ledger")
    no_ledger_io.rows_loaded = 6

    result = await nodes.ingest_node({"file_path": "ledger.xlsx"})

    assert result["doc_type"] == "ledger"
    assert result["ledger_rows_loaded"] == 6


def test_route_after_ingest():
    assert nodes.route_after_ingest({"doc_type": "ledger"}) == "finalize"
    assert nodes.route_after_ingest({"doc_type": "invoice"}) == "extract_fields"
    assert nodes.route_after_ingest({"doc_type": "receipt"}) == "extract_fields"


# ---------------------------------------------------------------------
# extract_fields_node
# ---------------------------------------------------------------------
async def test_extract_fields_node_text_path(fake_chat_model, fake_prompts):
    doc = ExtractedDocument(
        vendor="Acme Corp",
        document_number="INV-1",
        document_date="2026-08-05",
        line_items=[ExtractedLineItem(description="Widget", quantity=2, unit_price=5.0, amount=10.0)],
        subtotal=10.0,
        tax=1.0,
        total=11.0,
        currency="USD",
    )
    fake_chat_model([doc])

    result = await nodes.extract_fields_node({"doc_type": "invoice", "raw_text": "some text"})

    assert result["vendor"] == "Acme Corp"
    assert result["total"] == 11.0
    assert len(result["line_items"]) == 1
    assert result["trace"][0]["node"] == "extract_fields"


async def test_extract_fields_node_vision_path(fake_chat_model, fake_prompts):
    doc = ExtractedDocument(
        vendor="Downtown Cafe",
        document_number="",
        document_date="2026-08-06",
        line_items=[],
        subtotal=16.50,
        tax=1.36,
        total=17.86,
        currency="USD",
    )
    fake_chat_model([doc])

    result = await nodes.extract_fields_node(
        {"doc_type": "receipt", "image_base64": "abc123", "file_path": "receipt.png"}
    )

    assert result["vendor"] == "Downtown Cafe"
    assert result["total"] == 17.86


async def test_extract_fields_node_handles_extraction_failure(fake_chat_model, fake_prompts):
    fake_chat_model([RuntimeError("model refused to comply")])

    result = await nodes.extract_fields_node({"doc_type": "invoice", "raw_text": "garbled text"})

    assert result["vendor"] == ""
    assert result["total"] == 0.0
    assert "failed" in result["trace"][0]["summary"].lower()


# ---------------------------------------------------------------------
# validate_node (deterministic)
# ---------------------------------------------------------------------
def _valid_state(**overrides):
    state = {
        "vendor": "Acme Corp",
        "document_date": "2026-08-05",
        "line_items": [{"description": "Widget", "quantity": 2, "unit_price": 5.0, "amount": 10.0}],
        "subtotal": 10.0,
        "tax": 1.0,
        "total": 11.0,
        "currency": "USD",
    }
    state.update(overrides)
    return state


async def test_validate_node_clean_document():
    result = await nodes.validate_node(_valid_state())
    assert result["validation_issues"] == []


async def test_validate_node_catches_subtotal_mismatch():
    state = _valid_state(subtotal=999.0)
    result = await nodes.validate_node(state)
    codes = [i["code"] for i in result["validation_issues"]]
    assert "line_items_subtotal_mismatch" in codes


async def test_validate_node_catches_total_mismatch():
    state = _valid_state(total=500.0)
    result = await nodes.validate_node(state)
    codes = [i["code"] for i in result["validation_issues"]]
    assert "total_mismatch" in codes


async def test_validate_node_catches_missing_required_fields():
    state = _valid_state(vendor="", total=None)
    result = await nodes.validate_node(state)
    codes = [i["code"] for i in result["validation_issues"]]
    assert "missing_vendor" in codes
    assert "missing_total" in codes


async def test_validate_node_catches_future_date():
    state = _valid_state(document_date="2099-01-01")
    result = await nodes.validate_node(state)
    codes = [i["code"] for i in result["validation_issues"]]
    assert "future_date" in codes


async def test_validate_node_catches_unparseable_date():
    state = _valid_state(document_date="not-a-date")
    result = await nodes.validate_node(state)
    codes = [i["code"] for i in result["validation_issues"]]
    assert "unparseable_date" in codes


async def test_validate_node_warns_on_no_line_items():
    state = _valid_state(line_items=[])
    result = await nodes.validate_node(state)
    codes = [i["code"] for i in result["validation_issues"]]
    assert "no_line_items" in codes


async def test_validate_node_warns_on_unusual_currency():
    state = _valid_state(currency="ZZZ")
    result = await nodes.validate_node(state)
    codes = [i["code"] for i in result["validation_issues"]]
    assert "unusual_currency" in codes


# ---------------------------------------------------------------------
# reconcile_node (deterministic + ledger tools, mocked here)
# ---------------------------------------------------------------------
async def test_reconcile_node_match_found_no_duplicate(no_ledger_io):
    no_ledger_io.match_result = _match(id_=1, vendor="Acme Corp", amount=11.0)
    no_ledger_io.duplicate_results = []

    result = await nodes.reconcile_node({"vendor": "Acme Corp", "total": 11.0, "document_date": "2026-08-05"})

    codes = [f["code"] for f in result["reconciliation_findings"]]
    assert "ledger_match_found" in codes
    assert result["ledger_match_id"] == 1
    assert result["is_duplicate"] is False
    assert result["requires_approval"] is False


async def test_reconcile_node_no_match_found(no_ledger_io):
    no_ledger_io.match_result = None
    no_ledger_io.duplicate_results = []

    result = await nodes.reconcile_node({"vendor": "Unknown Vendor", "total": 42.0, "document_date": "2026-08-05"})

    codes = [f["code"] for f in result["reconciliation_findings"]]
    assert "no_ledger_match" in codes
    assert result["ledger_match_id"] is None


async def test_reconcile_node_flags_duplicate(no_ledger_io):
    no_ledger_io.match_result = _match(id_=2, vendor="Bright Office Supplies Inc.", amount=1266.53, day=7)
    no_ledger_io.duplicate_results = [_match(id_=1, vendor="Bright Office Supplies Inc.", amount=1266.53, day=5)]

    result = await nodes.reconcile_node(
        {"vendor": "Bright Office Supplies Inc.", "total": 1266.53, "document_date": "2026-08-07"}
    )

    codes = [f["code"] for f in result["reconciliation_findings"]]
    assert "duplicate_payment_suspected" in codes
    assert result["is_duplicate"] is True


async def test_reconcile_node_flags_policy_threshold(no_ledger_io):
    no_ledger_io.match_result = _match(id_=3, vendor="Summit Cloud Hosting LLC", amount=3518.13)
    no_ledger_io.duplicate_results = []

    result = await nodes.reconcile_node(
        {"vendor": "Summit Cloud Hosting LLC", "total": 3518.13, "document_date": "2026-08-10"}
    )

    codes = [f["code"] for f in result["reconciliation_findings"]]
    assert "exceeds_policy_threshold" in codes
    assert result["requires_approval"] is True


# ---------------------------------------------------------------------
# finalize_node
# ---------------------------------------------------------------------
async def test_finalize_node_ledger_upload():
    result = await nodes.finalize_node({"doc_type": "ledger", "ledger_rows_loaded": 6})
    assert result["final_status"] == "ledger_loaded"
    assert result["status"] == "completed"


async def test_finalize_node_posted():
    result = await nodes.finalize_node({"doc_type": "invoice", "human_decision": "approve"})
    assert result["final_status"] == "posted"
    assert result["status"] == "completed"


async def test_finalize_node_corrected_posted():
    result = await nodes.finalize_node({"doc_type": "invoice", "human_decision": "correct"})
    assert result["final_status"] == "corrected_posted"
    assert result["status"] == "completed"


async def test_finalize_node_rejected():
    result = await nodes.finalize_node({"doc_type": "invoice", "human_decision": "reject"})
    assert result["final_status"] == "rejected"
    assert result["status"] == "rejected"
