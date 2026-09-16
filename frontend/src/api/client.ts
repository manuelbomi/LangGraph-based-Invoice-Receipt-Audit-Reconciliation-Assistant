import type {
  HumanDecisionRequest,
  RunCreateResponse,
  RunDetail,
  RunListResponse,
  SamplesResponse,
} from "./types";

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return (await res.json()) as T;
}

export async function listSamples(): Promise<SamplesResponse> {
  const res = await fetch(`${API_BASE_URL}/documents/samples`);
  return handle<SamplesResponse>(res);
}

export async function runSampleDocument(sampleId: string): Promise<RunCreateResponse> {
  const res = await fetch(`${API_BASE_URL}/documents/samples/${sampleId}/run`, { method: "POST" });
  return handle<RunCreateResponse>(res);
}

export async function uploadDocument(file: File): Promise<RunCreateResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE_URL}/documents/upload`, { method: "POST", body: formData });
  return handle<RunCreateResponse>(res);
}

export async function resumeRun(runId: string, payload: HumanDecisionRequest): Promise<RunCreateResponse> {
  const res = await fetch(`${API_BASE_URL}/runs/${runId}/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<RunCreateResponse>(res);
}

export async function listRuns(): Promise<RunListResponse> {
  const res = await fetch(`${API_BASE_URL}/runs`);
  return handle<RunListResponse>(res);
}

export async function getRun(runId: string): Promise<RunDetail> {
  const res = await fetch(`${API_BASE_URL}/runs/${runId}`);
  return handle<RunDetail>(res);
}

export function streamUrl(runId: string): string {
  return `${API_BASE_URL}/runs/${runId}/stream`;
}

export function runFileUrl(runId: string): string {
  return `${API_BASE_URL}/documents/${runId}/file`;
}
