import { runFileUrl } from "../api/client";
import type { DocType } from "../api/types";

/** Shows the original source document next to its extracted fields --
 * PDFs render inline, receipt images render as an <img>, and the ledger
 * .xlsx (which browsers can't render inline) offers a download link. */
export function DocumentViewer({
  runId,
  docType,
  filename,
}: {
  runId: string;
  docType: DocType;
  filename: string;
}) {
  const url = runFileUrl(runId);

  if (docType === "receipt") {
    return (
      <div className="flex justify-center rounded-lg border border-slate-200 bg-slate-50 p-3">
        <img src={url} alt={`Receipt: ${filename}`} className="max-h-[600px] rounded shadow-sm" />
      </div>
    );
  }

  if (docType === "invoice") {
    return (
      <iframe
        title={`Invoice: ${filename}`}
        src={url}
        className="h-[600px] w-full rounded-lg border border-slate-200"
      />
    );
  }

  return (
    <div className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
      <p className="mb-2">{filename}</p>
      <a href={url} className="text-brand-600 hover:underline">
        Download the general ledger file
      </a>
    </div>
  );
}
