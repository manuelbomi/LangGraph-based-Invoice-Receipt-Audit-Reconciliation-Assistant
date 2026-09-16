/**
 * Hand-written TypeScript mirror of `backend/app/api/schemas.py`.
 * Keep these two files in sync when the API contract changes.
 */

export type RunStatus = "pending" | "running" | "awaiting_human" | "completed" | "rejected" | "error";
export type DocType = "invoice" | "receipt" | "ledger" | "unknown";

export interface SampleDocument {
  id: string;
  label: string;
  doc_type: DocType;
}

export interface SamplesResponse {
  samples: SampleDocument[];
}

export interface RunCreateResponse {
  id: string;
  status: RunStatus;
  original_filename: string;
  doc_type: DocType;
}

export interface HumanDecisionRequest {
  decision: "approve" | "correct" | "reject";
  feedback: string;
  corrected_fields?: Record<string, unknown> | null;
}

export interface TraceEventOut {
  node: string;
  timestamp: string;
  summary: string;
}

export interface LineItem {
  description: string;
  quantity: number;
  unit_price: number;
  amount: number;
}

export interface ExtractedFields {
  vendor?: string;
  document_number?: string;
  document_date?: string;
  line_items?: LineItem[];
  subtotal?: number;
  tax?: number;
  total?: number;
  currency?: string;
}

export type IssueSeverity = "info" | "warning" | "error";

export interface ValidationIssue {
  code: string;
  severity: IssueSeverity;
  message: string;
}

export interface ReconciliationFinding {
  code: string;
  severity: IssueSeverity;
  message: string;
  details: Record<string, unknown>;
}

export interface RunSummary {
  id: string;
  original_filename: string;
  doc_type: DocType;
  status: RunStatus;
  final_status: string | null;
  flagged: boolean;
  is_duplicate: boolean;
  created_at: string;
  updated_at: string;
}

/** Loosely-typed mirror of `AuditState` (backend/app/graph/state.py). */
export interface StateSnapshot extends ExtractedFields {
  doc_type?: DocType;
  validation_issues?: ValidationIssue[];
  reconciliation_findings?: ReconciliationFinding[];
  ledger_match_id?: number | null;
  is_duplicate?: boolean;
  requires_approval?: boolean;
  human_decision?: string;
  human_feedback?: string;
  final_status?: string;
  status?: RunStatus;
  ledger_rows_loaded?: number;
  interrupt?: InterruptPayload;
}

export interface RunDetail {
  id: string;
  original_filename: string;
  doc_type: DocType;
  status: RunStatus;
  final_status: string | null;
  extracted_fields: ExtractedFields;
  validation_issues: ValidationIssue[];
  reconciliation_findings: ReconciliationFinding[];
  trace: TraceEventOut[];
  state_snapshot: StateSnapshot;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface RunListResponse {
  runs: RunSummary[];
}

export interface InterruptPayload {
  original_filename: string;
  doc_type: DocType;
  extracted_fields: ExtractedFields;
  validation_issues: ValidationIssue[];
  reconciliation_findings: ReconciliationFinding[];
}

/** Shapes of the SSE events emitted by GET /runs/{id}/stream. */
export type StreamEvent =
  | { type: "node"; node: string; output: Record<string, unknown>; trace: TraceEventOut[] }
  | { type: "interrupt"; data: InterruptPayload }
  | { type: "done"; status: RunStatus; final_status: string | null }
  | { type: "error"; message: string }
  | {
      type: "replay";
      status: RunStatus;
      trace: TraceEventOut[];
      state_snapshot: StateSnapshot;
      final_status: string | null;
    };

/** The graph node names, in the order they appear in the LangGraph
 * StateGraph (backend/app/graph/graph.py) -- used to drive the GraphView.
 * A ledger upload only ever visits `ingest` -> `finalize`. */
export const GRAPH_NODES = [
  "ingest",
  "extract_fields",
  "validate",
  "reconcile",
  "human_review",
  "finalize",
] as const;

export type GraphNodeName = (typeof GRAPH_NODES)[number];
