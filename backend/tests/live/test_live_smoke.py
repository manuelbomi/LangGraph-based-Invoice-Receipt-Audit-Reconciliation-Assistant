"""REAL end-to-end smoke test: actual OpenAI API calls + a real Postgres.

This is deliberately excluded from the default `pytest` run (see the `live`
marker + `addopts` in `pyproject.toml`). Run it explicitly with:

    export OPENAI_API_KEY=sk-...
    export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/invoice_audit
    cd backend
    pytest -m live tests/live/test_live_smoke.py -v -s

What it proves, with no mocks anywhere in the graph/LLM/DB/ledger path:
  1. A real invoice PDF (`sample-data/invoices/INV-1001_bright_office_supplies.pdf`)
     is ingested, its fields extracted by a real `gpt-4o-mini` call, validated,
     and reconciled against the REAL general ledger (seeded from
     `sample-data/ledger/general_ledger.xlsx`) -- reaching `human_review` and
     genuinely pausing there (`interrupt()`).
  2. The checkpointer can be torn down and a BRAND NEW `AsyncPostgresSaver`
     + freshly-compiled graph (standing in for "a new process", e.g. the
     accountant coming back to their review queue the next day) can resume
     that exact thread and finish the run (`finalize`), posting it.

Cost note: this makes exactly ONE small `gpt-4o-mini` structured-output call
(the invoice's field extraction) and zero embedding calls.
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

if sys.platform == "win32":
    # psycopg's async mode cannot run on Windows' default ProactorEventLoop;
    # it needs a selector-based loop. This only matters for local dev on
    # Windows -- the backend Docker image (and CI) run on Linux, where this
    # is a no-op. See: https://www.psycopg.org/psycopg3/docs/advanced/async.html
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from alembic import command
from alembic.config import Config
from langgraph.types import Command

from app.config import get_settings
from app.db.checkpointer import build_checkpointer
from app.graph.graph import build_graph
from app.prompts.seed_prompts import seed as seed_prompts
from app.tools.ledger import load_ledger_from_excel

pytestmark = pytest.mark.live

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _run_migrations() -> None:
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "app", "db", "migrations"))
    command.upgrade(cfg, "head")


@pytest.fixture(scope="module", autouse=True)
def _prepare_schema():
    assert os.environ.get("OPENAI_API_KEY"), "OPENAI_API_KEY must be set for the live smoke test"
    assert os.environ.get("DATABASE_URL"), "DATABASE_URL must point at a real reachable Postgres"
    _run_migrations()
    seed_prompts()
    settings = get_settings()
    ledger_path = os.path.join(settings.sample_data_dir, "ledger", "general_ledger.xlsx")
    assert os.path.exists(ledger_path), f"sample ledger not found at {ledger_path}"
    load_ledger_from_excel(ledger_path, replace=True)
    yield


async def test_live_invoice_survives_checkpointer_restart_and_posts():
    settings = get_settings()
    invoice_path = os.path.join(
        settings.sample_data_dir, "invoices", "INV-1001_bright_office_supplies.pdf"
    )
    assert os.path.exists(invoice_path), f"sample invoice not found at {invoice_path}"

    thread_id = "live-smoke-thread"
    config = {"configurable": {"thread_id": thread_id}}
    graph_input = {"file_path": invoice_path, "original_filename": "INV-1001_bright_office_supplies.pdf"}

    # --- Phase 1: run until it pauses at human_review ------------------
    async with build_checkpointer() as checkpointer_1:
        graph_1 = build_graph(checkpointer=checkpointer_1)

        saw_interrupt = False
        async for event in graph_1.astream(graph_input, config=config, stream_mode="updates"):
            print("EVENT:", list(event.keys()))
            if "__interrupt__" in event:
                saw_interrupt = True
                payload = event["__interrupt__"][0].value
                print("\n--- EXTRACTED FIELDS AT HUMAN_REVIEW ---\n", payload["extracted_fields"])
                print("--- RECONCILIATION FINDINGS ---\n", payload["reconciliation_findings"])
                assert payload["extracted_fields"]["vendor"], "expected a non-empty extracted vendor"
                assert payload["extracted_fields"]["total"] > 0
        assert saw_interrupt, "graph should have paused at human_review"

        state = await graph_1.aget_state(config)
        assert state.next == ("human_review",)
    # `async with` exits here -> checkpointer_1's connection pool is fully
    # closed, simulating the backend process shutting down.

    # --- Phase 2: brand new checkpointer + graph, standing in for a ----
    # --- freshly-started process, resumes the SAME thread_id -----------
    async with build_checkpointer() as checkpointer_2:
        graph_2 = build_graph(checkpointer=checkpointer_2)

        # Prove the state genuinely persisted in Postgres, not in memory.
        resumed_state = await graph_2.aget_state(config)
        assert resumed_state.next == ("human_review",)
        assert resumed_state.values["vendor"]

        finished = False
        async for event in graph_2.astream(
            Command(resume={"decision": "approve", "feedback": "Approved by live smoke test."}),
            config=config,
            stream_mode="updates",
        ):
            print("RESUME EVENT:", list(event.keys()))
            if "finalize" in event:
                finished = True

        assert finished, "graph should have reached finalize after resume"
        final_state = await graph_2.aget_state(config)
        assert final_state.next == ()
        assert final_state.values["status"] == "completed"
        assert final_state.values["final_status"] == "posted"
        print("\n--- FINAL STATE ---\n", {k: final_state.values[k] for k in ("vendor", "total", "final_status")})
