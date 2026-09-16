import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getRun, resumeRun } from "../api/client";
import type { GraphNodeName, HumanDecisionRequest } from "../api/types";
import { DocumentViewer } from "../components/DocumentViewer";
import { ExtractedFieldsCard } from "../components/ExtractedFieldsCard";
import { FindingsList } from "../components/FindingsList";
import { GraphView } from "../components/GraphView";
import { NodePanel } from "../components/NodePanel";
import { ReviewForm } from "../components/ReviewForm";
import { useRunStream } from "../hooks/useRunStream";

const TERMINAL_STATUSES = new Set(["completed", "rejected", "error"]);

const FINAL_STATUS_LABEL: Record<string, string> = {
  posted: "Posted",
  corrected_posted: "Posted (corrected)",
  rejected: "Rejected",
  ledger_loaded: "Ledger reloaded",
};

export function RunDetailPage() {
  const { id } = useParams<{ id: string }>();
  const runId = id ?? null;
  const [generation, setGeneration] = useState(0);
  const queryClient = useQueryClient();

  const { data: runDetail } = useQuery({
    queryKey: ["run", runId],
    queryFn: () => getRun(runId as string),
    enabled: !!runId,
  });

  const stream = useRunStream(runId, generation);

  const resumeMutation = useMutation({
    mutationFn: (payload: HumanDecisionRequest) => resumeRun(runId as string, payload),
    onSuccess: () => {
      setGeneration((g) => g + 1);
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });

  const docType = stream.snapshot.doc_type ?? runDetail?.doc_type ?? "unknown";
  const isLedgerRun = docType === "ledger";
  const currentNode: GraphNodeName | null = (stream.currentNode as GraphNodeName) ?? null;
  const completedNodes = stream.completedNodes as GraphNodeName[];
  const isLive = !TERMINAL_STATUSES.has(stream.status) || resumeMutation.isPending;

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <Link to="/history" className="text-sm text-brand-600 hover:underline">
          &larr; Back to run history
        </Link>
        <h2 className="mt-1 text-xl font-semibold text-slate-900">
          {runDetail?.original_filename ?? "Loading..."}
        </h2>
        <p className="text-sm text-slate-500">
          Status:{" "}
          <span className="font-medium text-slate-700">
            {stream.status === "connecting" ? "connecting..." : stream.status.replace("_", " ")}
          </span>
          {stream.finalStatus && (
            <span className="ml-2 text-slate-500">
              &middot; {FINAL_STATUS_LABEL[stream.finalStatus] ?? stream.finalStatus}
            </span>
          )}
          {isLive && <span className="ml-2 text-brand-600">(live)</span>}
        </p>
      </div>

      {stream.error && <p className="rounded-md bg-rose-50 p-3 text-sm text-rose-700">{stream.error}</p>}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <GraphView currentNode={currentNode} completedNodes={completedNodes} isLedgerRun={isLedgerRun} />
        <NodePanel snapshot={stream.snapshot} trace={stream.trace} />
      </div>

      {stream.status === "awaiting_human" && stream.interrupt && (
        <ReviewForm
          interrupt={stream.interrupt}
          submitting={resumeMutation.isPending}
          onDecision={(decision) => resumeMutation.mutate(decision)}
        />
      )}

      {TERMINAL_STATUSES.has(stream.status) && runId && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
              Source document
            </h3>
            <DocumentViewer runId={runId} docType={docType} filename={runDetail?.original_filename ?? ""} />
          </div>
          <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-4">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
              Final record
            </h3>
            {!isLedgerRun && <ExtractedFieldsCard fields={stream.snapshot} />}
            {!isLedgerRun && (
              <>
                <FindingsList
                  title="Validation"
                  items={stream.snapshot.validation_issues ?? []}
                  emptyMessage="No validation issues."
                />
                <FindingsList
                  title="Reconciliation"
                  items={stream.snapshot.reconciliation_findings ?? []}
                  emptyMessage="No reconciliation findings."
                />
              </>
            )}
            {stream.snapshot.human_feedback && (
              <div>
                <h4 className="mb-1 text-sm font-semibold text-slate-800">Reviewer note</h4>
                <p className="rounded-md bg-slate-50 p-2 text-xs text-slate-600">
                  {stream.snapshot.human_feedback}
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
