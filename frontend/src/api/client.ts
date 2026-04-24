import type {
  AuditCreatedResponse,
  AuditRequest,
  AuditStatus,
  DiagnosticReport,
} from "../types/schemas";

const BASE = "/api/v1";

export interface ApiErrorPayload {
  error?: { type: string; message: string; details?: Record<string, unknown> };
}

export class ApiError extends Error {
  status: number;
  type: string;
  details: Record<string, unknown>;
  constructor(status: number, payload: ApiErrorPayload, fallback: string) {
    const err = payload.error ?? { type: "unknown", message: fallback };
    super(err.message || fallback);
    this.status = status;
    this.type = err.type || "unknown";
    this.details = err.details || {};
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers || {}),
    },
  });
  if (!resp.ok) {
    let payload: ApiErrorPayload = {};
    try {
      payload = await resp.json();
    } catch {
      /* ignore */
    }
    throw new ApiError(resp.status, payload, `${resp.status} ${resp.statusText}`);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

export const api = {
  createAudit: (body: AuditRequest) =>
    request<AuditCreatedResponse>("/audit", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getStatus: (id: string) => request<AuditStatus>(`/audit/${id}/status`),

  getReport: (id: string) =>
    request<DiagnosticReport>(`/audit/${id}/report`),

  cancelAudit: (id: string) =>
    request<void>(`/audit/${id}`, { method: "DELETE" }),

  getFile: async (
    id: string,
    path: string,
    start?: number,
    end?: number,
  ) => {
    const q = new URLSearchParams({ path });
    if (start != null) q.set("start", String(start));
    if (end != null) q.set("end", String(end));
    return request<{
      audit_id: string;
      path: string;
      start: number;
      end: number;
      total_lines: number;
      content: string;
      sha256: string;
    }>(`/audit/${id}/file?${q.toString()}`);
  },

  uploadPdf: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const resp = await fetch(`${BASE}/audit/upload-pdf`, {
      method: "POST",
      body: form,
    });
    if (!resp.ok) {
      let payload: ApiErrorPayload = {};
      try {
        payload = await resp.json();
      } catch {
        /* ignore */
      }
      throw new ApiError(
        resp.status,
        payload,
        `${resp.status} ${resp.statusText}`,
      );
    }
    return (await resp.json()) as { upload_id: string; size_bytes: number };
  },

  streamUrl: (id: string) => `${BASE}/audit/${id}/stream`,
};
