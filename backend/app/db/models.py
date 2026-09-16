"""SQLAlchemy models: the `prompts` registry, `runs` audit history, and
`ledger_entries` (the general ledger loaded from the sample `.xlsx`).

Note: LangGraph's `AsyncPostgresSaver` manages its own checkpoint tables
(`checkpoints`, `checkpoint_writes`, ...) via `checkpointer.setup()` -- those
are NOT modeled here and are intentionally left out of Alembic's autogenerate
scope (see `db/migrations/env.py`).
"""
from __future__ import annotations

import datetime as dt
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Prompt(Base):
    """A versioned prompt template.

    Only one version per `name` is `is_active` at a time; `get_prompt(name)`
    (see `app/prompts/registry.py`) resolves to that active version.
    """

    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Prompt name={self.name!r} v{self.version} active={self.is_active}>"


class LedgerEntry(Base):
    """One row of the general ledger / expense register, loaded from the
    bundled sample `.xlsx` (see `backend/scripts/seed_ledger.py`) or from a
    ledger file uploaded through the app itself (`ingest_node` with
    `doc_type == "ledger"`).

    `amount` is a plain `Float` for tutorial simplicity; a real ledger
    should use `Numeric`/`Decimal` to avoid floating-point rounding on
    monetary values.
    """

    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    vendor: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    gl_account: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LedgerEntry vendor={self.vendor!r} amount={self.amount} date={self.date}>"


class Run(Base):
    """One end-to-end document audit run, keyed by the LangGraph `thread_id`.

    Doubles as both "run history" (every document ever processed, including
    the seeded example analyses) and the durable "audited record" the
    `finalize` node writes to -- there's no separate audit-log table because
    a `Run` row already *is* the full audit trail for one document: what was
    extracted, what validation/reconciliation found, what a human decided,
    and the final posting status.
    """

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    # invoice | receipt | ledger | unknown
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    # pending | running | awaiting_human | completed | rejected | error
    final_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # posted | corrected_posted | rejected | ledger_loaded

    extracted_fields: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    validation_issues: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    reconciliation_findings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    trace: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    state_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Run id={self.id} status={self.status!r} doc_type={self.doc_type!r}>"
