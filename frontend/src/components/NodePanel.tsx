import type { StateSnapshot, TraceEventOut } from "../api/types";
import { ExtractedFieldsCard } from "./ExtractedFieldsCard";
import { FindingsList } from "./FindingsList";

interface NodePanelProps {
  snapshot: StateSnapshot;
  trace: TraceEventOut[];
}

/** Side panel rendering each node's intermediate output as it streams in:
 * extracted fields from `extract_fields`, flags from `validate` and
 * `reconcile`, and the running trace log. */
export function NodePanel({ snapshot, trace }: NodePanelProps) {
  const hasExtractedFields = Boolean(snapshot.vendor || snapshot.total || snapshot.document_date);

  return (
    <div className="flex h-[560px] flex-col gap-4 overflow-y-auto rounded-xl border border-slate-200 bg-white p-4">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Live node output</h3>

      {snapshot.doc_type === "ledger" ? (
        <section>
          <h4 className="mb-1 text-sm font-semibold text-slate-800">General ledger upload</h4>
          <p className="text-sm text-slate-600">
            {snapshot.ledger_rows_loaded !== undefined
              ? `${snapshot.ledger_rows_loaded} row(s) loaded into the ledger.`
              : "Loading..."}
          </p>
        </section>
      ) : (
        <>
          {hasExtractedFields && (
            <section>
              <h4 className="mb-1 text-sm font-semibold text-slate-800">Extracted fields</h4>
              <ExtractedFieldsCard fields={snapshot} />
            </section>
          )}

          {snapshot.validation_issues && (
            <FindingsList
              title="Validation"
              items={snapshot.validation_issues}
              emptyMessage="No validation issues found."
            />
          )}

          {snapshot.reconciliation_findings && (
            <FindingsList
              title="Reconciliation"
              items={snapshot.reconciliation_findings}
              emptyMessage="No reconciliation findings."
            />
          )}
        </>
      )}

      <section className="mt-auto">
        <h4 className="mb-1 text-sm font-semibold text-slate-800">Trace</h4>
        <ul className="space-y-1 text-xs text-slate-500">
          {trace.map((t, i) => (
            <li key={`${t.node}-${i}`}>
              <span className="font-mono text-slate-400">{new Date(t.timestamp).toLocaleTimeString()}</span>{" "}
              <span className="font-semibold text-slate-600">{t.node}</span>: {t.summary}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
