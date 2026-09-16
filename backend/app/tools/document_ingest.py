"""Real (non-stub) document ingestion helpers: PDF text extraction, image
base64 encoding for vision-LLM extraction, and doc-type detection.

Why a vision LLM instead of Tesseract OCR for receipts: `pytesseract`
requires the native Tesseract binary to be installed on the host/image,
which is one more moving part to get right across Windows dev machines,
CI runners, and the Docker image -- and thermal-receipt photos (skewed,
low-contrast, creased) are exactly the input Tesseract tends to do worst
on without real image preprocessing. `gpt-4o-mini` accepts image input
directly and, given a schema-constrained extraction prompt, reads a receipt
image (merchant, itemized lines, tax, total) reliably with zero extra
system dependencies. See the README for the fuller discussion.
"""
from __future__ import annotations

import base64
import os

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
PDF_EXTENSIONS = {".pdf"}
LEDGER_EXTENSIONS = {".xlsx", ".xls"}


def detect_doc_type(file_path: str) -> str:
    """Classify a document purely from its file extension.

    A production system might sniff file content/magic bytes too, but for
    this tutorial's three supported inputs (PDF invoice, image receipt,
    Excel ledger) the extension is unambiguous and this stays fully
    deterministic and free.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext in PDF_EXTENSIONS:
        return "invoice"
    if ext in IMAGE_EXTENSIONS:
        return "receipt"
    if ext in LEDGER_EXTENSIONS:
        return "ledger"
    raise ValueError(
        f"Unsupported file extension {ext!r}. Supported: "
        f"{sorted(PDF_EXTENSIONS | IMAGE_EXTENSIONS | LEDGER_EXTENSIONS)}"
    )


def extract_pdf_text(file_path: str) -> str:
    """Extract all text from a PDF using `pdfplumber` (pure Python, no
    native/system dependency -- unlike Tesseract, this works identically on
    Windows, macOS, Linux, and inside the Docker image)."""
    import pdfplumber

    parts: list[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def encode_image_base64(file_path: str) -> str:
    """Read an image file and return its base64-encoded bytes, ready to
    embed in a LangChain `image_url` data-URI content block."""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def image_mime_type(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".png":
        return "image/png"
    return "image/jpeg"
