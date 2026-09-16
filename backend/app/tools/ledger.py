"""Real (non-stub, deterministic) ledger matching + duplicate-payment
detection, plus the Excel -> Postgres loader for the general ledger.

Matching strategy (intentionally simple and inspectable, no LLM call):
  - Vendor names are compared with `difflib.SequenceMatcher` on a normalized
    (lowercased, punctuation-stripped) form -- good enough to survive minor
    formatting differences ("Bright Office Supplies Inc." vs "Bright Office
    Supplies Inc") without pulling in a fuzzy-matching dependency.
  - Amounts must match within a small absolute/relative tolerance.
  - The "correct" match is the ledger row with the same vendor+amount whose
    date is closest to the document's date (ties broken by whichever row is
    seen first), so a document exactly reproduces its own posting even when
    a near-duplicate exists nearby in time.
  - A near-duplicate is any OTHER ledger row (same vendor+amount, a
    different id) within a wider date window -- this is what catches a
    vendor invoice that was accidentally paid twice a few days apart.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd
from sqlalchemy import delete, select

from app.config import get_settings
from app.db.models import LedgerEntry
from app.db.session import SessionLocal

_VENDOR_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def _normalize_vendor(name: str) -> str:
    return _VENDOR_NORMALIZE_RE.sub(" ", name.lower()).strip()


def vendor_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _normalize_vendor(a), _normalize_vendor(b)).ratio()


def _amounts_match(a: float, b: float) -> bool:
    tolerance = max(0.01, abs(b) * 0.005)
    return abs(a - b) <= tolerance


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


@dataclass
class LedgerMatch:
    id: int
    date: date
    vendor: str
    description: str
    gl_account: str
    amount: float
    currency: str


def _to_match(entry: LedgerEntry) -> LedgerMatch:
    return LedgerMatch(
        id=entry.id,
        date=entry.date,
        vendor=entry.vendor,
        description=entry.description,
        gl_account=entry.gl_account,
        amount=entry.amount,
        currency=entry.currency,
    )


def find_ledger_match(
    vendor: str | None, amount: float | None, document_date: str | None
) -> LedgerMatch | None:
    """Return the single best-matching ledger row, or None."""
    if not vendor or amount is None:
        return None
    settings = get_settings()
    target_date = parse_iso_date(document_date)

    with SessionLocal() as db:
        candidates = db.execute(select(LedgerEntry)).scalars().all()

    best: LedgerEntry | None = None
    best_date_diff: int | None = None
    for candidate in candidates:
        if not _amounts_match(amount, candidate.amount):
            continue
        if vendor_similarity(vendor, candidate.vendor) < settings.vendor_match_threshold:
            continue
        date_diff = abs((candidate.date - target_date).days) if target_date else 0
        if date_diff > settings.match_date_window_days:
            continue
        if best is None or date_diff < best_date_diff:  # type: ignore[operator]
            best = candidate
            best_date_diff = date_diff

    return _to_match(best) if best is not None else None


def find_near_duplicate_ledger_entries(
    vendor: str | None,
    amount: float | None,
    document_date: str | None,
    *,
    exclude_id: int | None = None,
) -> list[LedgerMatch]:
    """Return OTHER ledger rows (besides `exclude_id`) that share the same
    vendor + amount within the wider duplicate-detection date window --
    i.e. "this vendor appears to have been paid this exact amount more than
    once in a short window."""
    if not vendor or amount is None:
        return []
    settings = get_settings()
    target_date = parse_iso_date(document_date)

    with SessionLocal() as db:
        candidates = db.execute(select(LedgerEntry)).scalars().all()

    duplicates: list[LedgerEntry] = []
    for candidate in candidates:
        if exclude_id is not None and candidate.id == exclude_id:
            continue
        if not _amounts_match(amount, candidate.amount):
            continue
        if vendor_similarity(vendor, candidate.vendor) < settings.vendor_match_threshold:
            continue
        if target_date and abs((candidate.date - target_date).days) > settings.duplicate_date_window_days:
            continue
        duplicates.append(candidate)

    return [_to_match(d) for d in duplicates]


def load_ledger_from_excel(file_path: str, *, replace: bool = True) -> int:
    """Load the general ledger `.xlsx` (columns: date, vendor, description,
    gl_account, amount, currency) into the `ledger_entries` table.

    `replace=True` (the default) clears the table first, so re-uploading a
    ledger export behaves like "here is the current ledger", not "append
    more rows on top of what's already there" -- important for this demo
    since re-running the seed script (or re-uploading the sample ledger
    through the app) must not double up the intentionally-duplicated pair
    and falsely inflate the duplicate-payment detector.
    """
    df = pd.read_excel(file_path)
    required = {"date", "vendor", "description", "gl_account", "amount", "currency"}
    missing = required - set(c.strip().lower() for c in df.columns)
    if missing:
        raise ValueError(f"Ledger file is missing required column(s): {sorted(missing)}")
    df.columns = [str(c).strip().lower() for c in df.columns]

    entries: list[LedgerEntry] = []
    for _, row in df.iterrows():
        raw_date = row["date"]
        if hasattr(raw_date, "date"):
            entry_date = raw_date.date()
        else:
            parsed = parse_iso_date(str(raw_date))
            if parsed is None:
                continue
            entry_date = parsed
        entries.append(
            LedgerEntry(
                date=entry_date,
                vendor=str(row["vendor"]).strip(),
                description=str(row.get("description", "") or ""),
                gl_account=str(row.get("gl_account", "") or ""),
                amount=float(row["amount"]),
                currency=str(row.get("currency", "USD") or "USD").strip().upper(),
            )
        )

    with SessionLocal() as db:
        if replace:
            db.execute(delete(LedgerEntry))
        db.add_all(entries)
        db.commit()

    return len(entries)
