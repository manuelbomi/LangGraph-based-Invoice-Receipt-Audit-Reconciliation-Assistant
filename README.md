# LangGraph Tutorial 02: Invoice & Receipt Audit / Reconciliation Assistant

A production-shaped, end-to-end example of a **document-processing agentic
workflow with a mandatory human-in-the-loop gate**, built with
[LangGraph](https://github.com/langchain-ai/langgraph): it ingests an
invoice (PDF), a receipt (image), or a general ledger (Excel), extracts
structured fields with an LLM, runs deterministic bookkeeping validation,
cross-checks the document against a Postgres general ledger to catch
**duplicate payments** and **out-of-policy amounts**, and pauses for an
accountant to approve, correct, or reject it before anything is recorded as
posted.

This is the second repo in the tutorial series (see
[`langgraph-tutorial-01-research-report-assistant`](../langgraph-tutorial-01-research-report-assistant)
for the first) and reuses that repo's established conventions -- project
layout, Postgres-backed prompt registry, `AsyncPostgresSaver` checkpointer,
Docker/CI setup -- applied to a different, equally real problem domain. It
is a fully independent, standalone repository.

## What it does

**Backend:** Python 3.11 / FastAPI / LangGraph `StateGraph`, checkpointed to
Postgres (`langgraph-checkpoint-postgres`), streaming node-by-node progress
to the frontend over Server-Sent Events.

**Frontend:** React 18 / TypeScript / Vite / Tailwind, with a live
[React Flow](https://reactflow.dev/) diagram of the running graph, an
editable human-review form, and a run-history / example-analyses view.

### The graph

```mermaid
flowchart TD
    START([START]) --> ingest[1. ingest\ndetect type; PDF text / image b64 / xlsx load]
    ingest -- "ledger upload" --> finalize[6. finalize\nrecord audited outcome]
    ingest -- "invoice / receipt" --> extract[2. extract_fields\nLLM structured output text or vision]
    extract --> validate[3. validate\ndeterministic arithmetic + field checks]
    validate --> reconcile[4. reconcile\ndeterministic ledger match + duplicate + policy check]
    reconcile --> human_review[5. human_review\ninterrupt: pauses for an accountant]
    human_review --> finalize
    finalize --> END([END])

    classDef gate stroke:#f59e0b,stroke-width:2px;
    class human_review gate;
```

The only branch point is right after `ingest`: a general-ledger upload is
parsed and loaded straight into Postgres deterministically (nothing to
review), while an invoice or receipt goes through the full pipeline ending
at a mandatory human decision. Three of the six nodes are **deterministic,
not LLM calls** -- `validate`, `reconcile`, and the ledger-loading branch of
`ingest` -- because arithmetic checks and database matching should be exact
and inspectable, not left to a model.

### Why a vision LLM instead of OCR for receipts

`extract_fields` reads PDFs via extracted text (`pdfplumber`) and reads
receipt images by sending the image directly to `gpt-4o-mini`'s vision
input, rather than running OCR (e.g. `pytesseract`) locally. Two reasons:

1. **Fewer moving parts.** `pytesseract` requires the native Tesseract
   binary installed on the host/image -- one more thing to get right
   consistently across Windows dev machines, CI runners, and the Docker
   image. `pdfplumber` and a vision API call have no such native dependency.
2. **Robustness on the actual input.** Thermal-receipt photos (skewed,
   low-contrast, creased) are exactly the input classic OCR does worst on
   without real image preprocessing. A vision-capable chat model, given a
   schema-constrained extraction prompt, reads a receipt image (merchant,
   itemized lines, tax, total) reliably with zero extra system dependencies.

Both extraction paths use the same Pydantic schema
(`app/graph/extraction_schema.py::ExtractedDocument`) via
`chat_model.with_structured_output(...)`, so `validate` and `reconcile`
don't need to know which path produced the fields.

### The UI

1. **Upload & Process** -- upload a document, or pick one of the bundled
   sample documents for a zero-setup demo. Watch the live graph diagram
   highlight the currently-executing node as SSE events arrive, with a side
   panel streaming in each node's output (extracted fields, validation
   issues, reconciliation findings).
2. **Human Review** -- when the run reaches `human_review`, the extracted
   fields are shown in an **editable form** alongside validation and
   reconciliation flags, with **Approve**, **Correct & Approve**, and
   **Reject** actions that call `POST /runs/{id}/resume`. Nothing is posted
   without one of these three explicit decisions.
3. **Run History / Example Analyses** -- every document processed
   (including four seeded, realistic example runs) with a status badge
   (**Clean** / **Flagged** / **Duplicate** / **Rejected**), and a detail
   view showing the original source document alongside its extracted
   fields, validation issues, and reconciliation findings.

## The sample documents (and why they're synthetic)

`sample-data/` contains 4 invoices (PDF, 3 distinct layouts), 3 receipts
(PNG, thermal-receipt style), and a general ledger (`.xlsx`) -- all
**synthetic**: fictitious vendors, fictitious amounts, generated by
[`sample-data/scripts/generate_samples.py`](./sample-data/scripts/generate_samples.py)
(reportlab + PIL + openpyxl), not sourced from any real company or scraped
commercial invoice template. See
[`sample-data/README.md`](./sample-data/README.md) for the full rationale
and a table of every document, including the intentional
**near-duplicate invoice pair** (`INV-1001` / `INV-1006`, same vendor and
amount, posted to the ledger twice two days apart) and the invoice with
**no matching ledger entry** (`FM-778`) that the app is designed to catch.

For a zero-setup demo, use the **Upload & Process** page's sample-document
picker instead of uploading your own file -- it runs the exact same graph
against these bundled documents.

## Real-world pain points this addresses

- **Manual data entry from invoices/receipts.** Keying vendor, line items,
  and totals from a PDF or a photographed receipt into a system of record
  is slow, repetitive, and error-prone -- `extract_fields` automates it,
  and `validate` catches arithmetic mistakes (line items not summing to the
  subtotal, subtotal + tax not matching the total) before anyone acts on
  bad numbers.
- **Duplicate payment detection.** Paying the same invoice twice (a
  resubmitted PDF, a vendor billing error, a data-entry mistake creating a
  second GL row) is one of the most common and costly things an audit
  catches after the fact. `reconcile` catches it proactively by looking for
  a second ledger entry with the same vendor and amount within a
  configurable date window.
- **Ledger reconciliation.** Confirming a document actually corresponds to
  a real posted transaction (and flagging when it doesn't) is core to any
  audit trail; `reconcile` does this automatically against the real
  Postgres-backed ledger, not a mocked lookup.
- **Policy threshold flags.** Payments above a configured amount
  (`POLICY_APPROVAL_THRESHOLD`) are flagged as needing extra sign-off,
  encoding a real AP control (e.g. "anything over $3,000 needs manager
  approval") directly into the workflow.

### Why the LangGraph interrupt/checkpoint pattern matters here specifically

Financial postings should **never be fully autonomous**. `human_review`'s
`interrupt()` is not a UI nicety bolted on afterward -- it's a hard gate in
the graph itself: the `finalize` node cannot run, and nothing is recorded as
`posted`, until a human calls `POST /runs/{id}/resume` with an explicit
decision. There is no code path that skips it for invoices/receipts.

And because that pause is backed by `AsyncPostgresSaver` rather than
in-memory state, it survives the backend process restarting entirely. That
matters concretely for an audit queue: an accountant working through a
stack of flagged documents over the course of a day (or several days) can
close their laptop, the server can redeploy, and every paused document
picks up exactly where it left off when they come back -- see
`backend/tests/live/test_live_smoke.py`, which proves this by closing the
checkpointer completely and opening a **brand new** one against the same
thread before resuming.

## Setup & run

### Required environment variables

Copy `.env.example` to `.env` and fill in:

| Variable | Default | Notes |
|---|---|---|
| `OPENAI_API_KEY` | -- | Required (this repo is tested against OpenAI) |
| `LLM_PROVIDER` | `openai` | `openai` or `anthropic` |
| `LLM_MODEL` | `gpt-4o-mini` | Cheap, fast; used for `extract_fields` |
| `ANTHROPIC_API_KEY` | -- | Only needed if `LLM_PROVIDER=anthropic` |
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/invoice_audit` | Prompts, run history, ledger, and LangGraph checkpoints |
| `POLICY_APPROVAL_THRESHOLD` | `3000.0` | Amount above which `reconcile` flags "requires additional approval" |
| `SAMPLE_DATA_DIR` | `../sample-data` | Where the bundled sample documents live |

See `.env.example` for the full list (vendor-matching thresholds, CORS, etc).

### Option A: docker-compose (recommended, works on Windows/macOS/Linux)

```bash
cp .env.example .env   # then edit OPENAI_API_KEY
docker compose up --build
```

This starts `postgres` (healthchecked), `backend` (runs Alembic migrations,
seeds the v1 prompts, loads the sample general ledger, seeds four example
runs, then serves the API on `:8000` -- see `backend/docker-entrypoint.sh`),
and `frontend` (built + served via nginx on `:8080`). Open
**http://localhost:8080**.

Port collisions are common on a dev box; override any of them without
touching the compose file:

```bash
BACKEND_PORT=8091 POSTGRES_PORT=5544 FRONTEND_PORT=8092 docker compose up --build
```

### Option B: local dev (backend + frontend separately)

Backend (Python 3.11+; no native OS dependency is required -- unlike the
first tutorial's embedded vector store, `pdfplumber`/`pandas`/`openpyxl` are
all pure-Python and work identically on Windows/macOS/Linux):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

# Start Postgres however you like, e.g.:
docker run -d --name invoice-audit-postgres -p 5432:5432 \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=invoice_audit postgres:16-alpine

export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/invoice_audit
export OPENAI_API_KEY=sk-...

alembic upgrade head
python -m app.prompts.seed_prompts
python -m scripts.seed_ledger      # loads sample-data/ledger/general_ledger.xlsx
python -m scripts.seed_examples
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
echo "VITE_API_BASE_URL=http://localhost:8000" > .env
npm run dev   # http://localhost:5173
```

### Running the tests

```bash
# Backend: fully mocked (no API key, no real DB needed) -- 46 tests
cd backend && pytest

# Backend: REAL end-to-end smoke test (needs a real OPENAI_API_KEY + reachable
# Postgres) -- proves the interrupt/resume cycle survives a checkpointer
# restart, using a real LLM call and the real sample ledger
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/invoice_audit \
  pytest -m live tests/live/test_live_smoke.py -v -s

# Frontend
cd frontend
npm run typecheck && npm run build && npm run test
```

## Repo structure

```
sample-data/
  invoices/        # 4 synthetic PDF invoices, 3 distinct layouts
  receipts/        # 3 synthetic thermal-receipt-style PNG images
  ledger/          # general_ledger.xlsx (the demo GL / expense register)
  scripts/         # generate_samples.py -- regenerates everything above
backend/
  app/
    graph/          # StateGraph state schema (state.py), nodes (nodes.py),
                     # wiring (graph.py), extraction schema (pydantic)
    tools/          # document_ingest.py (PDF/image), ledger.py (matching,
                     # duplicate detection, Excel loader)
    prompts/        # registry.py (Postgres-backed prompt versions), seed_prompts.py
    db/             # SQLAlchemy models, Alembic migrations, session, checkpointer wiring
    api/             # FastAPI routers (documents.py: upload/samples/file,
                     # runs.py: stream/resume/list/detail), schemas.py
    llm.py           # provider-agnostic chat model + embeddings factory
    main.py          # FastAPI app + lifespan (opens the one AsyncPostgresSaver)
  scripts/
    seed_ledger.py   # loads sample-data/ledger/general_ledger.xlsx into Postgres
    seed_examples.py # seeds 4 realistic example runs for the History page
  tests/             # pytest, fully mocked (LLM, ledger DB)
    live/            # tests/live/test_live_smoke.py -- REAL OpenAI + Postgres
  Dockerfile, docker-entrypoint.sh, requirements.txt, pyproject.toml
frontend/
  src/
    api/             # types.ts (hand-written mirror of backend schemas), client.ts
    hooks/           # useRunStream.ts (SSE -> React state)
    components/      # GraphView (React Flow), ReviewForm, ExtractedFieldsCard,
                     # FindingsList, RunHistoryList, DocumentViewer
    pages/           # UploadPage, HistoryPage, RunDetailPage
    test/            # Vitest + React Testing Library component tests
  Dockerfile, nginx.conf
docker-compose.yml
.github/workflows/ci.yml
```

## The prompt registry

Prompts aren't hardcoded strings in the node functions -- they're rows in a
Postgres `prompts` table (`name`, `version`, `template`, `is_active`,
`created_at`), loaded through `app/prompts/registry.py::get_prompt(name)`
(with a small process-local cache) and formatted with `render_prompt(name,
**kwargs)`. `backend/app/prompts/seed_prompts.py` seeds real v1 templates
for `extract_fields_text` (the PDF path) and `extract_fields_vision` (the
receipt-image path).

**To add a new prompt version:**

```python
from app.prompts.registry import add_prompt_version

add_prompt_version(
    "extract_fields_text",
    "...your improved template, with the same {raw_text} placeholder...",
    activate=True,  # flips is_active on this version, off on the previous one
)
```

Run that from a one-off script, a Python shell, or wire it behind an
admin-only API route -- `add_prompt_version` handles version numbering and
activation atomically. Because `get_prompt` caches per-process, restart the
backend (or call `registry.invalidate_cache()`) to pick up the change
immediately in a running process.

## License

MIT -- see [LICENSE](./LICENSE).

**Author:** Emmanuel Oyekanlu
