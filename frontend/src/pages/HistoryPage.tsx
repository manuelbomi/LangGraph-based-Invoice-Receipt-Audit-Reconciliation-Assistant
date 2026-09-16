import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { listRuns } from "../api/client";
import { RunHistoryList } from "../components/RunHistoryList";

export function HistoryPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["runs"],
    queryFn: listRuns,
    refetchInterval: 5000,
  });

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">Run history / example analyses</h2>
          <p className="text-sm text-slate-500">
            Every document processed, including seeded example analyses -- click any run for its
            source document, extracted fields, validation issues, and reconciliation findings.
          </p>
        </div>
        <Link
          to="/"
          className="shrink-0 rounded-md bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700"
        >
          Upload
        </Link>
      </div>

      {isLoading && <p className="text-sm text-slate-500">Loading runs...</p>}
      {isError && <p className="text-sm text-rose-600">{(error as Error).message}</p>}
      {data && <RunHistoryList runs={data.runs} />}
    </div>
  );
}
