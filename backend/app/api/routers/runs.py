"""REST + SSE API for starting, streaming, resuming, and listing document
audit runs.

Concurrency model (intentionally simple for a tutorial app): each active run
gets one `asyncio.Queue` in `request.app.state.run_queues`, fed by a
background `asyncio.Task` that drives `graph.astream(...)`. The SSE endpoint
just relays whatever lands on that queue. Every event is also persisted to
the `runs` table as it happens, so a client that reconnects (or a run that
finished while nobody was watching) can still be inspected via
`GET /runs/{id}` / replayed via `GET /runs/{id}/stream`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from sqlalchemy import select

from app.api.schemas import (
    HumanDecisionRequest,
    RunCreateResponse,
    RunDetail,
    RunListResponse,
    RunSummary,
)
from app.db.models import Run
from app.db.session import SessionLocal
from app.graph.nodes import EXTRACTED_FIELD_KEYS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/runs", tags=["runs"])


def _sse(event_type: str, data: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"


def _extracted_fields_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {k: snapshot.get(k) for k in EXTRACTED_FIELD_KEYS if k in snapshot}


def _is_flagged(run: Run) -> bool:
    return any(
        item.get("severity") in {"warning", "error"}
        for item in [*run.validation_issues, *run.reconciliation_findings]
    )


def _is_duplicate(run: Run) -> bool:
    return any(f.get("code") == "duplicate_payment_suspected" for f in run.reconciliation_findings)


async def _run_graph(request: Request, thread_id: str, graph_input: Any) -> None:
    """Background task: drive the graph, persist + broadcast each step."""
    graph = request.app.state.graph
    queue: asyncio.Queue = request.app.state.run_queues[thread_id]
    config = {"configurable": {"thread_id": thread_id}}

    def _set_status(status: str, **extra: Any) -> None:
        with SessionLocal() as db:
            run = db.get(Run, thread_id)
            if run is None:
                return
            run.status = status
            for k, v in extra.items():
                setattr(run, k, v)
            db.commit()

    def _record_event(node_output: dict[str, Any]) -> None:
        trace_items = node_output.get("trace", [])
        with SessionLocal() as db:
            run = db.get(Run, thread_id)
            if run is None:
                return
            run.trace = [*run.trace, *trace_items]
            merged_snapshot = {**run.state_snapshot, **{k: v for k, v in node_output.items() if k != "trace"}}
            run.state_snapshot = merged_snapshot
            run.doc_type = merged_snapshot.get("doc_type", run.doc_type)
            run.extracted_fields = _extracted_fields_from_snapshot(merged_snapshot)
            if "validation_issues" in node_output:
                run.validation_issues = node_output["validation_issues"]
            if "reconciliation_findings" in node_output:
                run.reconciliation_findings = node_output["reconciliation_findings"]
            db.commit()

    try:
        _set_status("running")
        async for event in graph.astream(graph_input, config=config, stream_mode="updates"):
            if "__interrupt__" in event:
                interrupt_obj = event["__interrupt__"][0]
                payload = dict(interrupt_obj.value)
                with SessionLocal() as db:
                    run = db.get(Run, thread_id)
                    if run is not None:
                        run.status = "awaiting_human"
                        run.state_snapshot = {**run.state_snapshot, "interrupt": payload}
                        db.commit()
                await queue.put(_sse("interrupt", payload))
                continue

            for node_name, node_output in event.items():
                if not isinstance(node_output, dict):
                    continue
                _record_event(node_output)
                await queue.put(
                    _sse(
                        "node",
                        {
                            "node": node_name,
                            "output": {k: v for k, v in node_output.items() if k != "trace"},
                            "trace": node_output.get("trace", []),
                        },
                    )
                )
                if node_name != "human_review":
                    _set_status("running")

        # Loop ended without an interrupt -> graph ran to completion (END).
        state = await graph.aget_state(config)
        if not state.next:  # no pending nodes => finished
            values = state.values
            status = values.get("status", "completed")
            final_status = values.get("final_status")
            with SessionLocal() as db:
                run = db.get(Run, thread_id)
                if run is not None:
                    run.status = status
                    run.final_status = final_status
                    merged_snapshot = {**run.state_snapshot, **values}
                    run.state_snapshot = merged_snapshot
                    run.extracted_fields = _extracted_fields_from_snapshot(merged_snapshot)
                    run.validation_issues = values.get("validation_issues", run.validation_issues)
                    run.reconciliation_findings = values.get(
                        "reconciliation_findings", run.reconciliation_findings
                    )
                    db.commit()
            await queue.put(_sse("done", {"status": status, "final_status": final_status}))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Run %s failed", thread_id)
        with SessionLocal() as db:
            run = db.get(Run, thread_id)
            if run is not None:
                run.status = "error"
                run.error = str(exc)
                db.commit()
        await queue.put(_sse("error", {"message": str(exc)}))
    finally:
        await queue.put(None)  # sentinel: close the SSE stream


def _start_background_run(request: Request, thread_id: str, graph_input: Any) -> None:
    queue: asyncio.Queue = asyncio.Queue()
    request.app.state.run_queues[thread_id] = queue
    task = asyncio.create_task(_run_graph(request, thread_id, graph_input))
    request.app.state.run_tasks[thread_id] = task


async def start_document_run(
    request: Request,
    *,
    file_path: str,
    original_filename: str,
    doc_type: str,
    run_id: str | None = None,
) -> RunCreateResponse:
    """Create a `Run` row and kick off the graph in the background. Shared
    by both the upload and run-a-sample-document endpoints in
    `app/api/routers/documents.py`."""
    run_id = run_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        run = Run(
            id=run_id,
            original_filename=original_filename,
            doc_type=doc_type,
            status="pending",
            extracted_fields={},
            validation_issues=[],
            reconciliation_findings=[],
            trace=[],
            state_snapshot={},
            created_at=now,
            updated_at=now,
        )
        db.add(run)
        db.commit()

    _start_background_run(
        request, run_id, {"file_path": file_path, "original_filename": original_filename}
    )
    return RunCreateResponse(id=run_id, status="pending", original_filename=original_filename, doc_type=doc_type)


@router.post("/{run_id}/resume", response_model=RunCreateResponse)
async def resume_run(run_id: str, body: HumanDecisionRequest, request: Request) -> RunCreateResponse:
    with SessionLocal() as db:
        run = db.get(Run, run_id)
        if run is None:
            raise HTTPException(404, "run not found")
        if run.status != "awaiting_human":
            raise HTTPException(409, f"run is not awaiting human review (status={run.status})")
        original_filename = run.original_filename
        doc_type = run.doc_type

    _start_background_run(
        request,
        run_id,
        Command(
            resume={
                "decision": body.decision,
                "feedback": body.feedback,
                "corrected_fields": body.corrected_fields or {},
            }
        ),
    )
    return RunCreateResponse(id=run_id, status="running", original_filename=original_filename, doc_type=doc_type)


@router.get("/{run_id}/stream")
async def stream_run(run_id: str, request: Request) -> StreamingResponse:
    async def event_source():
        queue: asyncio.Queue | None = request.app.state.run_queues.get(run_id)

        if queue is None:
            # No live background task (already finished, or the server was
            # restarted after this run reached a terminal/awaiting state).
            # Replay what's durably stored instead of streaming live.
            with SessionLocal() as db:
                run = db.get(Run, run_id)
            if run is None:
                yield _sse("error", {"message": "run not found"})
                return
            yield _sse(
                "replay",
                {
                    "status": run.status,
                    "trace": run.trace,
                    "state_snapshot": run.state_snapshot,
                    "final_status": run.final_status,
                },
            )
            if run.status == "awaiting_human":
                interrupt_payload = run.state_snapshot.get("interrupt", {})
                yield _sse("interrupt", interrupt_payload)
            yield _sse("done", {"status": run.status, "final_status": run.final_status})
            return

        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("", response_model=RunListResponse)
async def list_runs() -> RunListResponse:
    with SessionLocal() as db:
        rows = db.execute(select(Run).order_by(Run.created_at.desc())).scalars().all()
        return RunListResponse(
            runs=[
                RunSummary(
                    id=r.id,
                    original_filename=r.original_filename,
                    doc_type=r.doc_type,
                    status=r.status,
                    final_status=r.final_status,
                    flagged=_is_flagged(r),
                    is_duplicate=_is_duplicate(r),
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                )
                for r in rows
            ]
        )


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(run_id: str) -> RunDetail:
    with SessionLocal() as db:
        run = db.get(Run, run_id)
        if run is None:
            raise HTTPException(404, "run not found")
        return RunDetail(
            id=run.id,
            original_filename=run.original_filename,
            doc_type=run.doc_type,
            status=run.status,
            final_status=run.final_status,
            extracted_fields=run.extracted_fields,
            validation_issues=run.validation_issues,
            reconciliation_findings=run.reconciliation_findings,
            trace=run.trace,
            state_snapshot=run.state_snapshot,
            error=run.error,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )
