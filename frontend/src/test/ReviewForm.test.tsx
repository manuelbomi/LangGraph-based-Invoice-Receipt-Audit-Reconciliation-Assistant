import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { InterruptPayload } from "../api/types";
import { ReviewForm } from "../components/ReviewForm";

const INTERRUPT: InterruptPayload = {
  original_filename: "INV-1001_bright_office_supplies.pdf",
  doc_type: "invoice",
  extracted_fields: {
    vendor: "Bright Office Supplies Inc.",
    document_number: "INV-1001",
    document_date: "2026-08-05",
    line_items: [],
    subtotal: 1170.0,
    tax: 96.53,
    total: 1266.53,
    currency: "USD",
  },
  validation_issues: [],
  reconciliation_findings: [
    {
      code: "ledger_match_found",
      severity: "info",
      message: "Matched ledger entry #1.",
      details: {},
    },
  ],
};

describe("ReviewForm", () => {
  it("pre-fills the form with the extracted fields", () => {
    render(<ReviewForm interrupt={INTERRUPT} onDecision={vi.fn()} />);

    expect(screen.getByLabelText(/^vendor$/i)).toHaveValue("Bright Office Supplies Inc.");
    expect(screen.getByLabelText(/^total$/i)).toHaveValue("1266.53");
  });

  it("calls onDecision with approve and no corrected fields when Approve is clicked", async () => {
    const onDecision = vi.fn();
    const user = userEvent.setup();
    render(<ReviewForm interrupt={INTERRUPT} onDecision={onDecision} />);

    await user.click(screen.getByRole("button", { name: /^approve$/i }));

    expect(onDecision).toHaveBeenCalledWith({ decision: "approve", feedback: "" });
  });

  it("calls onDecision with reject", async () => {
    const onDecision = vi.fn();
    const user = userEvent.setup();
    render(<ReviewForm interrupt={INTERRUPT} onDecision={onDecision} />);

    await user.type(screen.getByLabelText(/reviewer note/i), "Duplicate of INV-1001.");
    await user.click(screen.getByRole("button", { name: /^reject$/i }));

    expect(onDecision).toHaveBeenCalledWith({ decision: "reject", feedback: "Duplicate of INV-1001." });
  });

  it("sends edited fields as corrected_fields when Correct & Approve is clicked", async () => {
    const onDecision = vi.fn();
    const user = userEvent.setup();
    render(<ReviewForm interrupt={INTERRUPT} onDecision={onDecision} />);

    const vendorInput = screen.getByLabelText(/^vendor$/i);
    await user.clear(vendorInput);
    await user.type(vendorInput, "Bright Office Supplies Incorporated");
    await user.click(screen.getByRole("button", { name: /correct & approve/i }));

    expect(onDecision).toHaveBeenCalledWith(
      expect.objectContaining({
        decision: "correct",
        corrected_fields: expect.objectContaining({ vendor: "Bright Office Supplies Incorporated" }),
      }),
    );
  });

  it("renders reconciliation findings", () => {
    render(<ReviewForm interrupt={INTERRUPT} onDecision={vi.fn()} />);

    expect(screen.getByText(/matched ledger entry #1/i)).toBeInTheDocument();
  });

  it("disables the buttons while submitting", () => {
    render(<ReviewForm interrupt={INTERRUPT} onDecision={vi.fn()} submitting />);

    expect(screen.getByRole("button", { name: /^approve$/i })).toBeDisabled();
  });
});
