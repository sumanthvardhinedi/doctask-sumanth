export type PackageSummary = {
  id: string;
  authority_code: string;
  name: string;
  status: string;
  document_count: number;
};

export type PackageDocument = {
  id: string;
  package_id: string;
  filename: string;
  content_type: string;
  file_size_bytes: number | null;
  storage_path: string;
  sort_order: number;
};

export type PackageDetail = PackageSummary & {
  documents: PackageDocument[];
};

export type Finding = {
  id: string;
  validation_run_id: string;
  package_document_id: string | null;
  rule_id: string;
  rule_category: string;
  severity: string;
  result: string;
  location: string | null;
  evidence: string | null;
  explanation: string;
  is_hard_rejection: boolean;
  approved: boolean | null;
  reviewer_notes: string | null;
};

export type AgentStage = {
  stage: string;
  status: string;
  duration_ms: number | null;
  elapsed_ms: number | null;
  error: string | null;
  token_count: number | null;
  estimated_cost: number | null;
};

export type AgentWorkflow = {
  id: string;
  validation_run_id: string | null;
  status: string;
  current_stage: string | null;
  retry_count: number;
  error: string | null;
  elapsed_ms: number | null;
  total_duration_ms: number | null;
  token_count: number | null;
  estimated_cost: number | null;
  stages: AgentStage[];
};

export type SuperDocsReview = {
  id: string;
  finding_id: string;
  status: string;
  human_approved: boolean | null;
  export_result: unknown;
};

function formatDetail(detail: unknown): string {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: unknown }).msg);
        }
        return JSON.stringify(item);
      })
      .join("; ");
  }
  if (detail && typeof detail === "object") {
    return JSON.stringify(detail);
  }
  return String(detail);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
      ...init,
    });
  } catch {
    throw new Error(
      "Cannot reach the API. Keep this UI running, and in another terminal start: python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 (from the backend folder).",
    );
  }
  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!response.ok) {
    const proxyDown =
      response.status >= 500 &&
      (typeof text === "string" &&
        (text.includes("ECONNREFUSED") ||
          text.includes("proxy error") ||
          text.includes("502")));
    if (proxyDown || response.status === 502) {
      throw new Error(
        "The API is not running on port 8000. In another terminal, from backend/: python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000",
      );
    }
    const detail =
      typeof body === "object" && body !== null && "detail" in body
        ? formatDetail((body as { detail: unknown }).detail)
        : text || response.statusText;
    throw new Error(detail);
  }
  return body as T;
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  listPackages: () => request<PackageSummary[]>("/api/v1/packages"),
  createPackage: (authority_code: string, name: string) =>
    request<PackageSummary>("/api/v1/packages", {
      method: "POST",
      body: JSON.stringify({ authority_code, name }),
    }),
  getPackage: (packageId: string) =>
    request<PackageDetail>(`/api/v1/packages/${packageId}`),
  addDocument: (
    packageId: string,
    payload: {
      filename: string;
      content_type: string;
      file_size_bytes: number;
      storage_path: string;
      sort_order: number;
    },
  ) =>
    request<PackageDocument>(`/api/v1/packages/${packageId}/documents`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  validate: (packageId: string) =>
    request<{ id: string; status: string }>(
      `/api/v1/packages/${packageId}/validate`,
      { method: "POST" },
    ),
  listFindings: (packageId: string, runId: string) =>
    request<Finding[]>(
      `/api/v1/packages/${packageId}/validation-runs/${runId}/findings`,
    ),
  decideFinding: (
    packageId: string,
    runId: string,
    findingId: string,
    approved: boolean,
    reviewer_notes: string,
  ) =>
    request(
      `/api/v1/packages/${packageId}/validation-runs/${runId}/findings/${findingId}/approval`,
      {
        method: "POST",
        body: JSON.stringify({
          approved,
          reviewer_notes: reviewer_notes || null,
        }),
      },
    ),
  getWorkflow: (packageId: string) =>
    request<AgentWorkflow>(`/api/v1/packages/${packageId}/agent-workflow`),
  startSuperDocs: (packageId: string, runId: string, findingId: string) =>
    request<SuperDocsReview>(
      `/api/v1/packages/${packageId}/validation-runs/${runId}/findings/${findingId}/superdocs-review`,
      { method: "POST" },
    ),
  decideSuperDocs: (
    packageId: string,
    reviewId: string,
    approved: boolean,
    human_notes: string,
  ) =>
    request<SuperDocsReview>(
      `/api/v1/packages/${packageId}/superdocs-reviews/${reviewId}/decision`,
      {
        method: "POST",
        body: JSON.stringify({
          approved,
          human_notes: human_notes || null,
        }),
      },
    ),
  exportSuperDocs: (packageId: string, reviewId: string) =>
    request<SuperDocsReview>(
      `/api/v1/packages/${packageId}/superdocs-reviews/${reviewId}/export`,
      { method: "POST" },
    ),
};
