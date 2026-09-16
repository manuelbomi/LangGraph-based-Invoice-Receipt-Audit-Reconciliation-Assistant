"""Centralized application settings.

All configuration is read from environment variables (see `.env.example` at
the repo root). We use `pydantic-settings` so misconfiguration fails fast and
loudly at process startup instead of deep inside a graph node.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- LLM provider ---------------------------------------------------
    llm_provider: str = "openai"  # "openai" | "anthropic"
    llm_model: str = "gpt-4o-mini"
    anthropic_model: str = "claude-3-5-haiku-latest"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    embedding_model: str = "text-embedding-3-small"
    # Field extraction should be as deterministic as possible -- this is
    # bookkeeping data, not creative writing.
    llm_temperature: float = 0.0

    # --- Postgres (prompts, runs/audit history, LangGraph checkpoints) ---
    # SQLAlchemy (sync engine) uses the psycopg3 dialect: postgresql+psycopg://
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/invoice_audit"
    )
    # AsyncPostgresSaver needs a plain psycopg-style DSN (no "+psycopg" driver
    # suffix); we strip it in db/checkpointer.py.

    # --- Documents --------------------------------------------------------
    # Where uploaded documents are stored (git-ignored). Relative paths are
    # resolved from the backend/ working directory.
    upload_dir: str = "./data/uploads"
    # Where the bundled synthetic sample documents live, so the "run a
    # sample document" zero-setup demo path and `scripts/seed_ledger.py` can
    # find them. Defaults to the repo-root `sample-data/` folder one level
    # up from `backend/`; overridden to `/app/sample-data` in Docker (see
    # docker-compose.yml, which mounts it read-only).
    sample_data_dir: str = "../sample-data"

    # --- Reconciliation / audit policy ------------------------------------
    # Payments at or below this are auto-clearable; above it, the reconcile
    # node flags "requires additional approval" for the human reviewer.
    policy_approval_threshold: float = 3000.0
    # Fuzzy vendor-name match threshold (difflib SequenceMatcher ratio,
    # 0-1) used by app/tools/ledger.py when matching a document to a ledger
    # row and when screening for duplicate payments.
    vendor_match_threshold: float = 0.72
    # A ledger row within this many days of the document date (and matching
    # vendor + amount) is considered "the" matching entry.
    match_date_window_days: int = 5
    # A SECOND ledger row (besides the matched one) within this many days,
    # same vendor + amount, is flagged as a possible duplicate payment.
    duplicate_date_window_days: int = 14

    # --- API ---------------------------------------------------------------
    cors_allow_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
