import type { ReconciliationFinding, ValidationIssue } from "../api/types";

const SEVERITY_LABEL: Record<string, string> = {
  error: "Error",
  warning: "Warning",
  info: "Info",
};

function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span
      className={`severity-${severity} shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide`}
    >
      {SEVERITY_LABEL[severity] ?? severity}
    </span>
  );
}

/** Renders validation issues and/or reconciliation findings as a flagged
 * list -- shared by the live run view and the Run History detail view. */
export function FindingsList({
  title,
  items,
  emptyMessage,
}: {
  title: string;
  items: (ValidationIssue | ReconciliationFinding)[];
  emptyMessage: string;
}) {
  return (
    <section>
      <h4 className="mb-2 text-sm font-semibold text-slate-800">{title}</h4>
      {items.length === 0 ? (
        <p className="rounded-md bg-emerald-50 px-3 py-2 text-xs text-emerald-800">{emptyMessage}</p>
      ) : (
        <ul className="space-y-2">
          {items.map((item, i) => (
            <li
              key={`${item.code}-${i}`}
              className={`severity-${item.severity} flex items-start gap-2 rounded-md border px-3 py-2 text-xs`}
            >
              <SeverityBadge severity={item.severity} />
              <span className="flex-1">
                <span className="mr-1 font-mono text-[10px] opacity-70">{item.code}</span>
                {item.message}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
