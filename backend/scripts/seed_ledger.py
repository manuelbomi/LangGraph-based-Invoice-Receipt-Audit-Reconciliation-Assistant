"""Load the bundled sample general ledger (`sample-data/ledger/general_ledger.xlsx`)
into Postgres.

Run with:
    python -m scripts.seed_ledger

Safe to re-run: `load_ledger_from_excel` replaces the table contents rather
than appending, so re-running this never duplicates rows (which would
otherwise corrupt the demo's duplicate-payment detection).
"""
from __future__ import annotations

import os

from app.config import get_settings
from app.tools.ledger import load_ledger_from_excel


def seed() -> None:
    settings = get_settings()
    path = os.path.join(settings.sample_data_dir, "ledger", "general_ledger.xlsx")
    if not os.path.exists(path):
        raise SystemExit(
            f"Sample ledger not found at {path!r}. Did you set SAMPLE_DATA_DIR correctly, "
            "or run sample-data/scripts/generate_samples.py?"
        )
    count = load_ledger_from_excel(path, replace=True)
    print(f"[seeded] Loaded {count} ledger row(s) from {path}")


if __name__ == "__main__":
    seed()
