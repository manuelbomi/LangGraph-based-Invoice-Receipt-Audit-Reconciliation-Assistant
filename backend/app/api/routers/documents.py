"""Document intake: file upload, the bundled-sample-document catalog (for a
zero-setup demo), and serving the original file back to the frontend detail
view (so it can show the source document alongside extracted fields)."""
from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.api.routers.runs import start_document_run
from app.api.schemas import RunCreateResponse, SampleDocument, SamplesResponse
from app.config import get_settings
from app.db.models import Run
from app.db.session import SessionLocal
from app.tools.document_ingest import detect_doc_type

router = APIRouter(prefix="/documents", tags=["documents"])

_ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".xlsx", ".xls"}

# The catalog backing the "or pick one of the bundled sample documents"
# zero-setup demo path -- see sample-data/README.md for what each one is.
SAMPLE_CATALOG: list[dict[str, str]] = [
    {
        "id": "inv-1001",
        "label": "Invoice - Bright Office Supplies Inc. ($1,266.53, clean match)",
        "doc_type": "invoice",
        "relative_path": "invoices/INV-1001_bright_office_supplies.pdf",
    },
    {
        "id": "inv-1006-duplicate",
        "label": "Invoice - Bright Office Supplies Inc. RESUBMIT ($1,266.53, duplicate payment)",
        "doc_type": "invoice",
        "relative_path": "invoices/INV-1006_bright_office_supplies_DUPLICATE.pdf",
    },
    {
        "id": "inv-2044",
        "label": "Invoice - Summit Cloud Hosting LLC ($3,518.13, exceeds policy threshold)",
        "doc_type": "invoice",
        "relative_path": "invoices/INV-2044_summit_cloud_hosting.pdf",
    },
    {
        "id": "fm-778",
        "label": "Invoice - Redwood Facilities Maintenance ($612.75, no ledger match)",
        "doc_type": "invoice",
        "relative_path": "invoices/FM-778_redwood_facilities.pdf",
    },
    {
        "id": "cafe-receipt",
        "label": "Receipt - Downtown Cafe ($17.86)",
        "doc_type": "receipt",
        "relative_path": "receipts/downtown_cafe_receipt.png",
    },
    {
        "id": "quickmart-receipt",
        "label": "Receipt - QuickMart Convenience ($19.99)",
        "doc_type": "receipt",
        "relative_path": "receipts/quickmart_receipt.png",
    },
    {
        "id": "taxi-receipt",
        "label": "Receipt - Metro Taxi Co ($47.00, clean match)",
        "doc_type": "receipt",
        "relative_path": "receipts/metro_taxi_receipt.png",
    },
    {
        "id": "general-ledger",
        "label": "General Ledger (.xlsx) - reload the demo ledger",
        "doc_type": "ledger",
        "relative_path": "ledger/general_ledger.xlsx",
    },
]
_SAMPLE_BY_ID = {s["id"]: s for s in SAMPLE_CATALOG}


@router.get("/samples", response_model=SamplesResponse)
async def list_samples() -> SamplesResponse:
    return SamplesResponse(
        samples=[SampleDocument(id=s["id"], label=s["label"], doc_type=s["doc_type"]) for s in SAMPLE_CATALOG]
    )


@router.post("/samples/{sample_id}/run", response_model=RunCreateResponse)
async def run_sample_document(sample_id: str, request: Request) -> RunCreateResponse:
    entry = _SAMPLE_BY_ID.get(sample_id)
    if entry is None:
        raise HTTPException(404, "unknown sample id")

    settings = get_settings()
    src_path = os.path.join(settings.sample_data_dir, entry["relative_path"])
    if not os.path.exists(src_path):
        raise HTTPException(500, f"sample file missing on server: {entry['relative_path']}")

    return await start_document_run(
        request,
        file_path=src_path,
        original_filename=os.path.basename(entry["relative_path"]),
        doc_type=entry["doc_type"],
    )


@router.post("/upload", response_model=RunCreateResponse)
async def upload_document(request: Request, file: UploadFile = File(...)) -> RunCreateResponse:
    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type {ext or '(none)'!r}. Allowed: {sorted(_ALLOWED_EXTENSIONS)}")

    settings = get_settings()
    run_id = str(uuid.uuid4())
    dest_dir = os.path.join(settings.upload_dir, run_id)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)

    contents = await file.read()
    with open(dest_path, "wb") as f:
        f.write(contents)

    doc_type = detect_doc_type(dest_path)
    return await start_document_run(
        request, file_path=dest_path, original_filename=filename, doc_type=doc_type, run_id=run_id
    )


@router.get("/{run_id}/file")
async def get_run_source_file(run_id: str):
    """Serve the original uploaded/sample file back to the frontend, so the
    Run History detail view can show the source document alongside its
    extracted fields."""
    with SessionLocal() as db:
        run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "run not found")

    settings = get_settings()
    candidate = os.path.join(settings.upload_dir, run_id, run.original_filename)
    if not os.path.exists(candidate):
        for sample in SAMPLE_CATALOG:
            if os.path.basename(sample["relative_path"]) == run.original_filename:
                candidate = os.path.join(settings.sample_data_dir, sample["relative_path"])
                break

    if not os.path.exists(candidate):
        raise HTTPException(404, "original file not found on the server")

    return FileResponse(candidate, filename=run.original_filename)
