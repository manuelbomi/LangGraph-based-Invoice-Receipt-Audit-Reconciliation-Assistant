"""Assembles the LangGraph `StateGraph` for the Invoice & Receipt Audit /
Reconciliation Assistant.

    START -> ingest --ledger--> finalize -> END
                |
          invoice/receipt
                v
          extract_fields -> validate -> reconcile -> human_review -> finalize -> END

The only branch point is right after `ingest`: a general-ledger upload is
parsed and loaded straight into Postgres deterministically (nothing to
extract, validate, or have a human review), while an invoice or receipt
goes through the full extract -> validate -> reconcile -> human_review
pipeline. `human_review`'s `interrupt()` is the other load-bearing piece of
control flow here -- see `app/graph/nodes.py::human_review_node`.
"""
from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
    extract_fields_node,
    finalize_node,
    human_review_node,
    ingest_node,
    reconcile_node,
    route_after_ingest,
    validate_node,
)
from app.graph.state import AuditState


def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    """Build (and optionally compile-with-checkpointer) the audit graph.

    Pass `checkpointer=None` to get an uncompiled-but-still-runnable graph
    with LangGraph's default in-memory checkpointing (handy for unit tests
    that don't need durability/interrupts across processes). Pass a real
    `AsyncPostgresSaver` in the FastAPI app for durable, resumable runs.
    """
    builder = StateGraph(AuditState)

    builder.add_node("ingest", ingest_node)
    builder.add_node("extract_fields", extract_fields_node)
    builder.add_node("validate", validate_node)
    builder.add_node("reconcile", reconcile_node)
    builder.add_node("human_review", human_review_node)
    builder.add_node("finalize", finalize_node)

    builder.add_edge(START, "ingest")
    builder.add_conditional_edges(
        "ingest",
        route_after_ingest,
        {"extract_fields": "extract_fields", "finalize": "finalize"},
    )
    builder.add_edge("extract_fields", "validate")
    builder.add_edge("validate", "reconcile")
    builder.add_edge("reconcile", "human_review")
    builder.add_edge("human_review", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile(checkpointer=checkpointer)
