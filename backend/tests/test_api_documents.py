"""API contract tests for the /documents and /runs endpoints.

Uses a lightweight in-memory fake in place of the Postgres-backed
`SessionLocal`, and an `InMemorySaver` in place of the Postgres checkpointer,
so these run without any real database. LLM + ledger calls are mocked
exactly as in `test_graph_nodes.py` / `test_graph_flow.py`. PDF text
extraction is mocked too (`extract_pdf_text`) since the uploaded test file
isn't a real PDF -- `detect_doc_type` is left real since it's pure,
deterministic extension-sniffing with no I/O.
"""
from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from langgraph.checkpoint.memory import InMemorySaver

from app.api.routers.documents import router as documents_router
from app.api.routers.runs import router as runs_router
from app.config import Settings
from app.db.models import Run
from app.graph.extraction_schema import ExtractedDocument
from app.graph.graph import build_graph


class _FakeResultSet:
    def __init__(self, rows: list[Run]):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, store: dict[str, Run]):
        self._store = store

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def add(self, obj: Run) -> None:
        self._store[obj.id] = obj

    def commit(self) -> None:
        pass

    def get(self, _model, run_id: str):
        return self._store.get(run_id)

    def execute(self, _stmt):
        rows = sorted(self._store.values(), key=lambda r: r.created_at, reverse=True)
        return _FakeResultSet(rows)


@pytest.fixture
def api_app(monkeypatch, fake_chat_model, fake_prompts, no_ledger_io, tmp_path):
    store: dict[str, Run] = {}
    monkeypatch.setattr("app.api.routers.runs.SessionLocal", lambda: _FakeSession(store))
    monkeypatch.setattr("app.api.routers.documents.SessionLocal", lambda: _FakeSession(store))

    fake_settings = Settings(
        upload_dir=str(tmp_path / "uploads"), sample_data_dir=str(tmp_path / "sample-data")
    )
    monkeypatch.setattr("app.api.routers.documents.get_settings", lambda: fake_settings)

    monkeypatch.setattr("app.graph.nodes.extract_pdf_text", lambda p: "invoice text")
    monkeypatch.setattr("app.graph.nodes.encode_image_base64", lambda p: "abc123")

    app = FastAPI()
    app.state.run_queues = {}
    app.state.run_tasks = {}
    app.state.graph = build_graph(checkpointer=InMemorySaver())
    app.include_router(documents_router)
    app.include_router(runs_router)
    return app, store


async def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _extracted_doc(**overrides) -> ExtractedDocument:
    defaults = dict(
        vendor="Acme Corp",
        document_number="INV-1",
        document_date="2026-08-05",
        line_items=[],
        subtotal=100.0,
        tax=8.0,
        total=108.0,
        currency="USD",
    )
    defaults.update(overrides)
    return ExtractedDocument(**defaults)


async def test_list_samples_returns_catalog(api_app):
    app, _ = api_app
    async with await _client(app) as client:
        resp = await client.get("/documents/samples")
        assert resp.status_code == 200
        samples = resp.json()["samples"]
        ids = {s["id"] for s in samples}
        assert "inv-1001" in ids
        assert "general-ledger" in ids


async def test_upload_invoice_reaches_human_review(api_app, fake_chat_model):
    app, _ = api_app
    fake_chat_model([_extracted_doc()])

    async with await _client(app) as client:
        resp = await client.post(
            "/documents/upload",
            files={"file": ("test_invoice.pdf", b"%PDF-1.4 fake content", "application/pdf")},
        )
        assert resp.status_code == 200
        body = resp.json()
        run_id = body["id"]
        assert body["doc_type"] == "invoice"

        await app.state.run_tasks[run_id]

        detail = await client.get(f"/runs/{run_id}")
        assert detail.status_code == 200
        detail_body = detail.json()
        assert detail_body["status"] == "awaiting_human"
        assert detail_body["extracted_fields"]["vendor"] == "Acme Corp"
        assert len(detail_body["trace"]) >= 3  # ingest, extract_fields, validate, reconcile


async def test_upload_rejects_unsupported_extension(api_app):
    app, _ = api_app
    async with await _client(app) as client:
        resp = await client.post(
            "/documents/upload", files={"file": ("notes.txt", b"hello", "text/plain")}
        )
        assert resp.status_code == 400


async def test_run_sample_document(api_app, fake_chat_model, tmp_path):
    app, _ = api_app
    fake_chat_model([_extracted_doc(vendor="Bright Office Supplies Inc.")])

    sample_dir = tmp_path / "sample-data" / "invoices"
    sample_dir.mkdir(parents=True)
    (sample_dir / "INV-1001_bright_office_supplies.pdf").write_bytes(b"%PDF-1.4 fake content")

    async with await _client(app) as client:
        resp = await client.post("/documents/samples/inv-1001/run")
        assert resp.status_code == 200
        run_id = resp.json()["id"]

        await app.state.run_tasks[run_id]

        detail = await client.get(f"/runs/{run_id}")
        assert detail.json()["extracted_fields"]["vendor"] == "Bright Office Supplies Inc."


async def test_run_unknown_sample_404(api_app):
    app, _ = api_app
    async with await _client(app) as client:
        resp = await client.post("/documents/samples/does-not-exist/run")
        assert resp.status_code == 404


async def test_resume_run_completes(api_app, fake_chat_model):
    app, _ = api_app
    fake_chat_model([_extracted_doc()])

    async with await _client(app) as client:
        resp = await client.post(
            "/documents/upload",
            files={"file": ("test_invoice.pdf", b"%PDF-1.4 fake content", "application/pdf")},
        )
        run_id = resp.json()["id"]
        await app.state.run_tasks[run_id]

        resume_resp = await client.post(
            f"/runs/{run_id}/resume", json={"decision": "approve", "feedback": "Looks good."}
        )
        assert resume_resp.status_code == 200
        await app.state.run_tasks[run_id]

        detail = await client.get(f"/runs/{run_id}")
        detail_body = detail.json()
        assert detail_body["status"] == "completed"
        assert detail_body["final_status"] == "posted"


async def test_resume_rejects_when_not_awaiting_human(api_app):
    app, _ = api_app
    async with await _client(app) as client:
        resp = await client.post(
            "/runs/does-not-exist/resume", json={"decision": "approve", "feedback": ""}
        )
        assert resp.status_code == 404


async def test_list_runs_returns_summaries(api_app):
    app, store = api_app
    from datetime import datetime, timezone

    store["r1"] = Run(
        id="r1", original_filename="a.pdf", doc_type="invoice", status="completed",
        extracted_fields={}, validation_issues=[], reconciliation_findings=[], trace=[],
        state_snapshot={}, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    store["r2"] = Run(
        id="r2", original_filename="b.png", doc_type="receipt", status="awaiting_human",
        extracted_fields={}, validation_issues=[], reconciliation_findings=[], trace=[],
        state_snapshot={}, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )

    async with await _client(app) as client:
        resp = await client.get("/runs")
        assert resp.status_code == 200
        ids = {r["id"] for r in resp.json()["runs"]}
        assert ids == {"r1", "r2"}


async def test_get_unknown_run_404(api_app):
    app, _ = api_app
    async with await _client(app) as client:
        resp = await client.get("/runs/nope")
        assert resp.status_code == 404
