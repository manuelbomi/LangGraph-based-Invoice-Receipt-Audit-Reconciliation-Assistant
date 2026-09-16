"""End-to-end graph flow tests using LangGraph's in-memory checkpointer.

This proves the interrupt/resume *mechanics* (the same API the FastAPI app
uses against Postgres in `app/db/checkpointer.py`) without needing a real
database or LLM. The equivalent test against a *real* Postgres checkpointer
and a *real* OpenAI key lives in `tests/live/test_live_smoke.py`.
"""
from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.graph.extraction_schema import ExtractedDocument
from app.graph.graph import build_graph


async def test_invoice_pauses_at_human_review_and_resumes_to_completion(
    fake_chat_model, fake_prompts, no_ledger_io, monkeypatch
):
    monkeypatch.setattr("app.graph.nodes.detect_doc_type", lambda p: "invoice")
    monkeypatch.setattr("app.graph.nodes.extract_pdf_text", lambda p: "invoice text")
    no_ledger_io.match_result = None
    no_ledger_io.duplicate_results = []

    fake_chat_model(
        [
            ExtractedDocument(
                vendor="Acme Corp",
                document_number="INV-1",
                document_date="2026-08-05",
                line_items=[],
                subtotal=100.0,
                tax=8.0,
                total=108.0,
                currency="USD",
            )
        ]
    )

    graph = build_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "test-thread-1"}}

    result = None
    async for event in graph.astream(
        {"file_path": "invoice.pdf", "original_filename": "invoice.pdf"},
        config=config,
        stream_mode="updates",
    ):
        result = event

    assert result is not None
    assert "__interrupt__" in result, "graph should pause at human_review"
    interrupt_payload = result["__interrupt__"][0].value
    assert interrupt_payload["extracted_fields"]["vendor"] == "Acme Corp"

    state_before_resume = await graph.aget_state(config)
    assert state_before_resume.next == ("human_review",)

    final_event = None
    async for event in graph.astream(
        Command(resume={"decision": "approve", "feedback": "Looks correct."}),
        config=config,
        stream_mode="updates",
    ):
        final_event = event

    assert "finalize" in final_event
    final_state = await graph.aget_state(config)
    assert final_state.next == ()  # graph reached END
    assert final_state.values["status"] == "completed"
    assert final_state.values["final_status"] == "posted"


async def test_correct_and_approve_applies_corrected_fields(
    fake_chat_model, fake_prompts, no_ledger_io, monkeypatch
):
    monkeypatch.setattr("app.graph.nodes.detect_doc_type", lambda p: "invoice")
    monkeypatch.setattr("app.graph.nodes.extract_pdf_text", lambda p: "invoice text")
    no_ledger_io.match_result = None
    no_ledger_io.duplicate_results = []

    fake_chat_model(
        [
            ExtractedDocument(
                vendor="Acme Corp",
                document_number="INV-1",
                document_date="2026-08-05",
                line_items=[],
                subtotal=100.0,
                tax=8.0,
                total=108.0,
                currency="USD",
            )
        ]
    )

    graph = build_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "test-thread-correct"}}

    async for _ in graph.astream(
        {"file_path": "invoice.pdf", "original_filename": "invoice.pdf"},
        config=config,
        stream_mode="updates",
    ):
        pass

    async for _ in graph.astream(
        Command(
            resume={
                "decision": "correct",
                "feedback": "Fixed vendor name typo.",
                "corrected_fields": {"vendor": "Acme Corporation"},
            }
        ),
        config=config,
        stream_mode="updates",
    ):
        pass

    final_state = await graph.aget_state(config)
    assert final_state.values["vendor"] == "Acme Corporation"
    assert final_state.values["final_status"] == "corrected_posted"


async def test_ledger_upload_skips_human_review(no_ledger_io, monkeypatch):
    monkeypatch.setattr("app.graph.nodes.detect_doc_type", lambda p: "ledger")
    no_ledger_io.rows_loaded = 6

    graph = build_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "test-thread-ledger"}}

    saw_interrupt = False
    async for event in graph.astream(
        {"file_path": "ledger.xlsx", "original_filename": "ledger.xlsx"},
        config=config,
        stream_mode="updates",
    ):
        if "__interrupt__" in event:
            saw_interrupt = True

    assert saw_interrupt is False
    final_state = await graph.aget_state(config)
    assert final_state.next == ()
    assert final_state.values["final_status"] == "ledger_loaded"
    assert final_state.values["status"] == "completed"
