import { useState } from "react";

import type { HumanDecisionRequest, InterruptPayload } from "../api/types";
import { FindingsList } from "./FindingsList";

interface ReviewFormProps {
  interrupt: InterruptPayload;
  onDecision: (decision: HumanDecisionRequest) => void;
  submitting?: boolean;
}

/** Human-in-the-loop review: shows the extracted fields as an editable
 * form alongside validation/reconciliation flags, with
 * Approve / Correct-and-Approve / Reject actions that call `onDecision` --
 * the page wires that to `POST /runs/{id}/resume`. Nothing is posted to the
 * ledger without one of these three explicit decisions. */
export function ReviewForm({ interrupt, onDecision, submitting }: ReviewFormProps) {
  const fields = interrupt.extracted_fields;
  const [vendor, setVendor] = useState(fields.vendor ?? "");
  const [documentNumber, setDocumentNumber] = useState(fields.document_number ?? "");
  const [documentDate, setDocumentDate] = useState(fields.document_date ?? "");
  const [subtotal, setSubtotal] = useState(String(fields.subtotal ?? ""));
  const [tax, setTax] = useState(String(fields.tax ?? ""));
  const [total, setTotal] = useState(String(fields.total ?? ""));
  const [currency, setCurrency] = useState(fields.currency ?? "USD");
  const [feedback, setFeedback] = useState("");

  const correctedFields = () => ({
    vendor,
    document_number: documentNumber,
    document_date: documentDate,
    subtotal: Number(subtotal),
    tax: Number(tax),
    total: Number(total),
    currency,
  });

  return (
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-5">
      <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-amber-700">
        Human review required
      </h3>
      <p className="mb-4 text-sm text-amber-900">
        This {interrupt.doc_type} is paused before posting. Confirm or correct the fields below,
        then Approve, Correct &amp; Approve, or Reject. Nothing is written to the ledger until you
        decide.
      </p>

      <div className="mb-4 grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-amber-200 bg-white p-4">
          <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">
            Extracted fields (editable)
          </h4>
          <div className="space-y-2 text-sm">
            <label className="block">
              <span className="text-xs text-slate-500">Vendor</span>
              <input
                className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1"
                value={vendor}
                onChange={(e) => setVendor(e.target.value)}
                aria-label="Vendor"
              />
            </label>
            <label className="block">
              <span className="text-xs text-slate-500">Document #</span>
              <input
                className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1"
                value={documentNumber}
                onChange={(e) => setDocumentNumber(e.target.value)}
                aria-label="Document number"
              />
            </label>
            <label className="block">
              <span className="text-xs text-slate-500">Date (YYYY-MM-DD)</span>
              <input
                className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1"
                value={documentDate}
                onChange={(e) => setDocumentDate(e.target.value)}
                aria-label="Document date"
              />
            </label>
            <div className="grid grid-cols-3 gap-2">
              <label className="block">
                <span className="text-xs text-slate-500">Subtotal</span>
                <input
                  className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1"
                  value={subtotal}
                  onChange={(e) => setSubtotal(e.target.value)}
                  aria-label="Subtotal"
                />
              </label>
              <label className="block">
                <span className="text-xs text-slate-500">Tax</span>
                <input
                  className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1"
                  value={tax}
                  onChange={(e) => setTax(e.target.value)}
                  aria-label="Tax"
                />
              </label>
              <label className="block">
                <span className="text-xs text-slate-500">Total</span>
                <input
                  className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1"
                  value={total}
                  onChange={(e) => setTotal(e.target.value)}
                  aria-label="Total"
                />
              </label>
            </div>
            <label className="block">
              <span className="text-xs text-slate-500">Currency</span>
              <input
                className="mt-0.5 w-24 rounded border border-slate-300 px-2 py-1"
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                aria-label="Currency"
              />
            </label>
          </div>
        </div>

        <div className="space-y-3">
          <FindingsList
            title="Validation"
            items={interrupt.validation_issues}
            emptyMessage="No validation issues."
          />
          <FindingsList
            title="Reconciliation"
            items={interrupt.reconciliation_findings}
            emptyMessage="No reconciliation findings."
          />
        </div>
      </div>

      <textarea
        className="mb-3 w-full rounded-md border border-slate-300 p-2 text-sm"
        rows={2}
        placeholder="Reviewer note (optional) -- why you approved, corrected, or rejected this"
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        aria-label="Reviewer note"
      />

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={submitting}
          onClick={() => onDecision({ decision: "approve", feedback })}
          className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          Approve
        </button>
        <button
          type="button"
          disabled={submitting}
          onClick={() => onDecision({ decision: "correct", feedback, corrected_fields: correctedFields() })}
          className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          Correct &amp; Approve
        </button>
        <button
          type="button"
          disabled={submitting}
          onClick={() => onDecision({ decision: "reject", feedback })}
          className="rounded-md bg-rose-600 px-4 py-2 text-sm font-medium text-white hover:bg-rose-700 disabled:opacity-50"
        >
          Reject
        </button>
      </div>
    </div>
  );
}
