import { Background, type Edge, Handle, type Node, Position, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";

import type { GraphNodeName } from "../api/types";

interface GraphViewProps {
  currentNode: GraphNodeName | null;
  completedNodes: GraphNodeName[];
  isLedgerRun?: boolean;
}

interface NodeData extends Record<string, unknown> {
  label: string;
  active: boolean;
  done: boolean;
  skipped: boolean;
}

function StepNode({ data }: { data: NodeData }) {
  const base =
    "rounded-lg border-2 px-3 py-2 text-sm font-medium shadow-sm min-w-[150px] text-center transition-colors";
  const cls = data.active
    ? `${base} border-brand-500 bg-brand-500 text-white animate-pulse`
    : data.done
      ? `${base} border-brand-300 bg-brand-50 text-brand-800`
      : data.skipped
        ? `${base} border-dashed border-slate-200 bg-slate-50 text-slate-300`
        : `${base} border-slate-300 bg-white text-slate-500`;
  return (
    <div className={cls}>
      <Handle type="target" position={Position.Top} className="!bg-slate-400" />
      {data.label}
      <Handle type="source" position={Position.Bottom} className="!bg-slate-400" />
    </div>
  );
}

const nodeTypes = { step: StepNode };

const LAYOUT: Record<GraphNodeName, { x: number; y: number; label: string }> = {
  ingest: { x: 260, y: 0, label: "1. Ingest" },
  extract_fields: { x: 260, y: 100, label: "2. Extract Fields" },
  validate: { x: 260, y: 200, label: "3. Validate" },
  reconcile: { x: 260, y: 300, label: "4. Reconcile" },
  human_review: { x: 260, y: 420, label: "5. Human Review" },
  finalize: { x: 260, y: 520, label: "6. Finalize" },
};

const MIDDLE_NODES: GraphNodeName[] = ["extract_fields", "validate", "reconcile", "human_review"];

export function GraphView({ currentNode, completedNodes, isLedgerRun }: GraphViewProps) {
  const nodes: Node[] = useMemo(
    () =>
      (Object.keys(LAYOUT) as GraphNodeName[]).map((id) => ({
        id,
        type: "step",
        position: { x: LAYOUT[id].x, y: LAYOUT[id].y },
        data: {
          label: LAYOUT[id].label,
          active: currentNode === id,
          done: completedNodes.includes(id) && currentNode !== id,
          skipped: Boolean(isLedgerRun) && MIDDLE_NODES.includes(id),
        } satisfies NodeData,
        draggable: false,
      })),
    [currentNode, completedNodes, isLedgerRun],
  );

  const edgeStyle = (active: boolean) => ({ stroke: active ? "#265ef2" : "#cbd5e1", strokeWidth: active ? 2.5 : 1.5 });

  const edges: Edge[] = useMemo(
    () => [
      {
        id: "e-ingest-extract",
        source: "ingest",
        target: "extract_fields",
        style: edgeStyle(completedNodes.includes("extract_fields")),
        hidden: Boolean(isLedgerRun),
      },
      {
        id: "e-extract-validate",
        source: "extract_fields",
        target: "validate",
        style: edgeStyle(completedNodes.includes("validate")),
        hidden: Boolean(isLedgerRun),
      },
      {
        id: "e-validate-reconcile",
        source: "validate",
        target: "reconcile",
        style: edgeStyle(completedNodes.includes("reconcile")),
        hidden: Boolean(isLedgerRun),
      },
      {
        id: "e-reconcile-human",
        source: "reconcile",
        target: "human_review",
        style: edgeStyle(completedNodes.includes("human_review")),
        hidden: Boolean(isLedgerRun),
      },
      {
        id: "e-human-finalize",
        source: "human_review",
        target: "finalize",
        style: edgeStyle(completedNodes.includes("finalize")),
        hidden: Boolean(isLedgerRun),
      },
      {
        id: "e-ingest-finalize-ledger",
        source: "ingest",
        target: "finalize",
        label: "ledger upload (skip review)",
        type: "smoothstep",
        style: { stroke: "#0f766e", strokeWidth: 2 },
        hidden: !isLedgerRun,
      },
    ],
    [completedNodes, isLedgerRun],
  );

  return (
    <div className="h-[560px] w-full rounded-xl border border-slate-200 bg-white">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
      >
        <Background gap={16} color="#e2e8f0" />
      </ReactFlow>
    </div>
  );
}
