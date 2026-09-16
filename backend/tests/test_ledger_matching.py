"""Unit tests for the deterministic ledger matching / duplicate-detection
logic in `app/tools/ledger.py`. Uses a fake SQLAlchemy session (no real
Postgres) returning canned `LedgerEntry`-shaped rows."""
from __future__ import annotations

from datetime import date

from app.tools import ledger


class _FakeEntry:
    def __init__(self, id, entry_date, vendor, amount, currency="USD", description="", gl_account=""):
        self.id = id
        self.date = entry_date
        self.vendor = vendor
        self.amount = amount
        self.currency = currency
        self.description = description
        self.gl_account = gl_account


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, _stmt):
        return _FakeResult(self._rows)


def _patch_rows(monkeypatch, rows):
    monkeypatch.setattr(ledger, "SessionLocal", lambda: _FakeSession(rows))


def test_vendor_similarity_ignores_case_and_punctuation():
    assert ledger.vendor_similarity("Bright Office Supplies Inc.", "bright office supplies inc") > 0.95


def test_vendor_similarity_low_for_unrelated_names():
    assert ledger.vendor_similarity("Bright Office Supplies Inc.", "Statewide Insurance Co") < 0.5


def test_find_ledger_match_returns_closest_date_on_tie(monkeypatch):
    rows = [
        _FakeEntry(1, date(2026, 8, 5), "Bright Office Supplies Inc.", 1266.53),
        _FakeEntry(2, date(2026, 8, 7), "Bright Office Supplies Inc.", 1266.53),
    ]
    _patch_rows(monkeypatch, rows)

    match = ledger.find_ledger_match("Bright Office Supplies Inc.", 1266.53, "2026-08-05")

    assert match is not None
    assert match.id == 1  # exact date match wins over the other candidate


def test_find_ledger_match_returns_none_when_no_candidate_qualifies(monkeypatch):
    rows = [_FakeEntry(1, date(2026, 8, 5), "Some Other Vendor", 99.99)]
    _patch_rows(monkeypatch, rows)

    match = ledger.find_ledger_match("Redwood Facilities Maintenance", 612.75, "2026-08-12")

    assert match is None


def test_find_near_duplicate_ledger_entries_excludes_the_matched_row(monkeypatch):
    rows = [
        _FakeEntry(1, date(2026, 8, 5), "Bright Office Supplies Inc.", 1266.53),
        _FakeEntry(2, date(2026, 8, 7), "Bright Office Supplies Inc.", 1266.53),
    ]
    _patch_rows(monkeypatch, rows)

    duplicates = ledger.find_near_duplicate_ledger_entries(
        "Bright Office Supplies Inc.", 1266.53, "2026-08-05", exclude_id=1
    )

    assert [d.id for d in duplicates] == [2]


def test_find_near_duplicate_ledger_entries_empty_when_unique(monkeypatch):
    rows = [_FakeEntry(3, date(2026, 8, 10), "Summit Cloud Hosting LLC", 3518.13)]
    _patch_rows(monkeypatch, rows)

    duplicates = ledger.find_near_duplicate_ledger_entries(
        "Summit Cloud Hosting LLC", 3518.13, "2026-08-10", exclude_id=3
    )

    assert duplicates == []


def test_find_ledger_match_respects_amount_tolerance(monkeypatch):
    rows = [_FakeEntry(1, date(2026, 8, 5), "Acme Corp", 100.00)]
    _patch_rows(monkeypatch, rows)

    assert ledger.find_ledger_match("Acme Corp", 150.00, "2026-08-05") is None
    assert ledger.find_ledger_match("Acme Corp", 100.00, "2026-08-05") is not None
