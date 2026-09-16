import type { ExtractedFields } from "../api/types";

function money(value: number | undefined, currency?: string): string {
  if (value === undefined || value === null) return "-";
  return `${currency ?? "USD"} ${value.toFixed(2)}`;
}

/** Read-only display of extracted invoice/receipt fields -- shared by the
 * live extraction panel and the Run History detail view. */
export function ExtractedFieldsCard({ fields }: { fields: ExtractedFields }) {
  const lineItems = fields.line_items ?? [];
  return (
    <div className="space-y-3">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        <dt className="text-slate-500">Vendor</dt>
        <dd className="font-medium text-slate-800">{fields.vendor || "-"}</dd>
        <dt className="text-slate-500">Document #</dt>
        <dd className="text-slate-800">{fields.document_number || "-"}</dd>
        <dt className="text-slate-500">Date</dt>
        <dd className="text-slate-800">{fields.document_date || "-"}</dd>
        <dt className="text-slate-500">Currency</dt>
        <dd className="text-slate-800">{fields.currency || "-"}</dd>
      </dl>

      {lineItems.length > 0 && (
        <div className="overflow-x-auto rounded-md border border-slate-200">
          <table className="w-full text-xs">
            <thead className="bg-slate-100 text-slate-600">
              <tr>
                <th className="px-2 py-1 text-left">Description</th>
                <th className="px-2 py-1 text-right">Qty</th>
                <th className="px-2 py-1 text-right">Unit Price</th>
                <th className="px-2 py-1 text-right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {lineItems.map((li, i) => (
                <tr key={i} className="border-t border-slate-100">
                  <td className="px-2 py-1">{li.description}</td>
                  <td className="px-2 py-1 text-right">{li.quantity}</td>
                  <td className="px-2 py-1 text-right">{li.unit_price.toFixed(2)}</td>
                  <td className="px-2 py-1 text-right">{li.amount.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <dl className="ml-auto grid max-w-[220px] grid-cols-2 gap-x-4 gap-y-1 text-sm">
        <dt className="text-slate-500">Subtotal</dt>
        <dd className="text-right text-slate-800">{money(fields.subtotal, fields.currency)}</dd>
        <dt className="text-slate-500">Tax</dt>
        <dd className="text-right text-slate-800">{money(fields.tax, fields.currency)}</dd>
        <dt className="font-semibold text-slate-700">Total</dt>
        <dd className="text-right font-semibold text-slate-900">{money(fields.total, fields.currency)}</dd>
      </dl>
    </div>
  );
}
