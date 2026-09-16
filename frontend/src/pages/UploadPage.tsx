import { useMutation, useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { listSamples, runSampleDocument, uploadDocument } from "../api/client";

export function UploadPage() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedSample, setSelectedSample] = useState("");

  const { data: samplesData } = useQuery({ queryKey: ["samples"], queryFn: listSamples });

  const uploadMutation = useMutation({
    mutationFn: uploadDocument,
    onSuccess: (data) => navigate(`/runs/${data.id}`),
  });

  const sampleMutation = useMutation({
    mutationFn: runSampleDocument,
    onSuccess: (data) => navigate(`/runs/${data.id}`),
  });

  const busy = uploadMutation.isPending || sampleMutation.isPending;

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <div>
        <h2 className="mb-2 text-xl font-semibold text-slate-900">Upload a document</h2>
        <p className="mb-4 text-sm text-slate-500">
          Upload a PDF invoice, an image receipt (PNG/JPG), or an Excel general ledger (.xlsx). The
          graph will extract fields, validate them, cross-check them against the ledger in
          Postgres, then pause for your review before posting.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const file = fileInputRef.current?.files?.[0];
            if (file) uploadMutation.mutate(file);
          }}
          className="flex flex-col gap-3 rounded-lg border border-dashed border-slate-300 p-6"
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls"
            aria-label="Choose a document to upload"
            className="text-sm"
          />
          <button
            type="submit"
            disabled={busy}
            className="self-start rounded-md bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-brand-700 disabled:opacity-50"
          >
            {uploadMutation.isPending ? "Uploading..." : "Upload & process"}
          </button>
          {uploadMutation.isError && (
            <p className="text-sm text-rose-600">{(uploadMutation.error as Error).message}</p>
          )}
        </form>
      </div>

      <div>
        <h2 className="mb-2 text-xl font-semibold text-slate-900">Or run a bundled sample</h2>
        <p className="mb-4 text-sm text-slate-500">
          Zero-setup demo: these are synthetic documents bundled with this repo (see{" "}
          <code>sample-data/README.md</code>), including a caught duplicate payment and a
          policy-threshold flag.
        </p>
        <div className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-6">
          <select
            value={selectedSample}
            onChange={(e) => setSelectedSample(e.target.value)}
            aria-label="Choose a sample document"
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">Choose a sample document...</option>
            {samplesData?.samples.map((sample) => (
              <option key={sample.id} value={sample.id}>
                {sample.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={busy || !selectedSample}
            onClick={() => sampleMutation.mutate(selectedSample)}
            className="self-start rounded-md bg-slate-800 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-slate-900 disabled:opacity-50"
          >
            {sampleMutation.isPending ? "Starting..." : "Run sample document"}
          </button>
          {sampleMutation.isError && (
            <p className="text-sm text-rose-600">{(sampleMutation.error as Error).message}</p>
          )}
        </div>
      </div>
    </div>
  );
}
