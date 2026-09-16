"""Seed version-1 prompts for the `extract_fields` node (text + vision
variants).

Run with:
    python -m app.prompts.seed_prompts

Safe to re-run: it only inserts a new version if the active template text
for a given name has actually changed.
"""
from __future__ import annotations

from sqlalchemy import select

from app.db.models import Prompt
from app.db.session import SessionLocal
from app.prompts.registry import add_prompt_version

_COMMON_INSTRUCTIONS = (
    "You are a meticulous accounts-payable data entry clerk. Extract structured "
    "fields exactly as they appear on the document -- do not guess or invent "
    "values that aren't present. Normalize the document date to ISO 8601 "
    "'YYYY-MM-DD'. If tax is not shown or the document is tax-exempt, use 0. "
    "If a document number isn't shown, use an empty string. Include every line "
    "item you can see, with quantity, unit price, and amount."
)

PROMPTS_V1: dict[str, str] = {
    "extract_fields_text": (
        f"{_COMMON_INSTRUCTIONS}\n\n"
        "Below is text extracted from a PDF invoice:\n\n"
        "-----\n{raw_text}\n-----\n\n"
        "Extract the vendor, document number, document date, line items, "
        "subtotal, tax, total, and currency."
    ),
    "extract_fields_vision": (
        f"{_COMMON_INSTRUCTIONS}\n\n"
        "The attached image is a photo/scan of a purchase receipt. Read the "
        "merchant name, receipt/transaction number, date, itemized purchases, "
        "subtotal, tax, and total directly from the image. Use the merchant "
        "name as the vendor."
    ),
}


def seed() -> None:
    with SessionLocal() as db:
        for name, template in PROMPTS_V1.items():
            active = db.execute(
                select(Prompt).where(Prompt.name == name, Prompt.is_active.is_(True))
            ).scalar_one_or_none()
            if active is not None and active.template == template:
                print(f"[skip] '{name}' already has this template active (v{active.version})")
                continue
            version = add_prompt_version(name, template, activate=True)
            print(f"[seeded] '{name}' -> v{version}")


if __name__ == "__main__":
    seed()
