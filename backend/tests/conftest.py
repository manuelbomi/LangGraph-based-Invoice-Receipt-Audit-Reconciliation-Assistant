"""Shared test fixtures.

All tests in `tests/` (excluding `tests/live/`) are fully mocked: no real
LLM calls, no real Postgres, no real network. This keeps `pytest` free and
fast to run in CI. The real end-to-end path is exercised separately by
`tests/live/test_live_smoke.py`, which is excluded by default (see the
`live` marker in `pyproject.toml`) and requires a real `OPENAI_API_KEY`
plus a reachable Postgres.
"""
from __future__ import annotations

import os
from typing import Any

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-dummy-key")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")


class _FakeStructuredRunnable:
    """Stands in for `chat_model.with_structured_output(Schema)`."""

    def __init__(self, parent: "FakeChatModel"):
        self._parent = parent

    async def ainvoke(self, prompt: Any, *args: Any, **kwargs: Any) -> Any:
        self._parent.calls.append(prompt)
        if not self._parent._responses:
            raise AssertionError("FakeChatModel called more times than responses were queued")
        item = self._parent._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeChatModel:
    """Stand-in for a LangChain chat model used via `.with_structured_output(...)`.

    Construct with a list of canned responses (pydantic model instances, or
    an `Exception` instance to simulate an extraction failure); each call to
    `ainvoke` pops the next one, regardless of prompt content.
    """

    def __init__(self, responses: list[Any]):
        self._responses = list(responses)
        self.calls: list[Any] = []

    def with_structured_output(self, schema: Any) -> _FakeStructuredRunnable:
        return _FakeStructuredRunnable(self)


@pytest.fixture
def fake_chat_model(monkeypatch):
    """Patch `app.graph.nodes.get_chat_model` to return a FakeChatModel.

    Returns a factory: `make(responses=[...])` -> the FakeChatModel instance,
    so each test controls exactly what the "LLM" returns at each graph step.
    """
    holder: dict[str, FakeChatModel] = {}

    def make(responses: list[Any]) -> FakeChatModel:
        model = FakeChatModel(responses)
        holder["model"] = model
        return model

    def fake_get_chat_model(*args: Any, **kwargs: Any) -> FakeChatModel:
        return holder["model"]

    monkeypatch.setattr("app.graph.nodes.get_chat_model", fake_get_chat_model)
    return make


@pytest.fixture
def fake_prompts(monkeypatch):
    """Patch `app.graph.nodes.render_prompt` to a template-free passthrough.

    Node logic is what's under test here, not prompt wording (that's
    covered by the real templates in `app/prompts/seed_prompts.py`, which
    the live smoke test exercises against a real LLM). This just avoids
    requiring a Postgres-backed prompt registry in unit tests.
    """

    def fake_render_prompt(name: str, **kwargs: Any) -> str:
        return f"[[{name}]] {kwargs}"

    monkeypatch.setattr("app.graph.nodes.render_prompt", fake_render_prompt)


@pytest.fixture
def no_ledger_io(monkeypatch):
    """Patch out every real-Postgres call the graph nodes make (ledger
    matching, duplicate detection, ledger loading), so unit/flow/API tests
    never need a live database. Returns a small namespace of the fakes so
    a test can configure return values."""

    class _Fakes:
        match_result: Any = None
        duplicate_results: list[Any] = []
        rows_loaded: int = 0

    fakes = _Fakes()

    def fake_find_ledger_match(vendor, amount, document_date):
        return fakes.match_result

    def fake_find_near_duplicate_ledger_entries(vendor, amount, document_date, *, exclude_id=None):
        return fakes.duplicate_results

    def fake_load_ledger_from_excel(file_path, *, replace=True):
        return fakes.rows_loaded

    monkeypatch.setattr("app.graph.nodes.find_ledger_match", fake_find_ledger_match)
    monkeypatch.setattr(
        "app.graph.nodes.find_near_duplicate_ledger_entries", fake_find_near_duplicate_ledger_entries
    )
    monkeypatch.setattr("app.graph.nodes.load_ledger_from_excel", fake_load_ledger_from_excel)
    return fakes
