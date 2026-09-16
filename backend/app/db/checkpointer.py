"""Wiring for LangGraph's Postgres checkpointer.

This is what makes a document's audit run durable: `AsyncPostgresSaver`
persists the full graph state after every node executes, keyed by
`thread_id`. A run paused at `human_review` (via `interrupt()`) -- an
accountant's queue item waiting for their attention -- can be resumed hours
or days later, even from a brand new process, by opening a fresh
`AsyncPostgresSaver` against the same Postgres database and calling
`graph.astream(Command(resume=...), config={"configurable": {"thread_id": ...}})`.
That matters specifically for an audit workflow: nothing here should ever
post to the ledger without a human in the loop, and that human should be
able to work through a queue of pending documents over an arbitrarily long
stretch of time without losing state.

We open ONE saver for the lifetime of the FastAPI process (see
`app/main.py` lifespan) rather than one per request, since it owns a
connection pool.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import get_settings


def _psycopg_dsn(database_url: str) -> str:
    """Strip the SQLAlchemy "+psycopg" driver suffix -> a plain psycopg DSN."""
    return database_url.replace("postgresql+psycopg://", "postgresql://")


@asynccontextmanager
async def build_checkpointer():
    """Yield a ready-to-use (schema already set up) AsyncPostgresSaver."""
    settings = get_settings()
    dsn = _psycopg_dsn(settings.database_url)
    async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
        await saver.setup()
        yield saver
