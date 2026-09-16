import { Link } from "react-router-dom";

import type { RunSummary } from "../api/types";

function statusBadge(run: RunSummary): { label: string; className: string } {
  if (run.status === "rejected") {
    return { label: "Rejected", className: "bg-rose-100 text-rose-800" };
  }
  if (run.status === "error") {
    return { label: "Error", className: "bg-rose-100 text-rose-800" };
  }
  if (run.status === "awaiting_human") {
    return { label: "Awaiting review", className: "bg-amber-100 text-amber-800" };
  }
  if (run.status === "pending" || run.status === "running") {
    return { label: "Processing", className: "bg-brand-100 text-brand-800" };
  }
  if (run.is_duplicate) {
    return { label: "Duplicate", className: "bg-rose-100 text-rose-800" };
  }
  if (run.flagged) {
    return { label: "Flagged", className: "bg-amber-100 text-amber-800" };
  }
  return { label: "Clean", className: "bg-emerald-100 text-emerald-800" };
}

const DOC_TYPE_LABEL: Record<string, string> = {
  invoice: "Invoice",
  receipt: "Receipt",
  ledger: "Ledger",
  unknown: "Document",
};

export function RunHistoryList({ runs }: { runs: RunSummary[] }) {
  if (runs.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
        No documents processed yet. Upload one or run a bundled sample to see it appear here.
      </p>
    );
  }

  return (
    <ul className="divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white" role="list">
      {runs.map((run) => {
        const badge = statusBadge(run);
        return (
          <li key={run.id}>
            <Link
              to={`/runs/${run.id}`}
              className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-slate-50"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-slate-800">{run.original_filename}</p>
                <p className="text-xs text-slate-400">
                  {DOC_TYPE_LABEL[run.doc_type] ?? run.doc_type} &middot;{" "}
                  {new Date(run.created_at).toLocaleString()}
                </p>
              </div>
              <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${badge.className}`}>
                {badge.label}
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
