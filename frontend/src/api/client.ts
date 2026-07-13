// Dünner fetch-Wrapper um das FastAPI-Backend. Spricht NIEMALS direkt mit
// Etherscan - der API-Key existiert ausschließlich serverseitig (siehe
// api/dependencies.py).

import type { ImportCreatedResponse, JobStatusResponse, TransactionsPage } from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // Antwort war kein JSON - statusText als Fallback verwenden.
    }
    throw new ApiError(detail, response.status);
  }

  return response.json() as Promise<T>;
}

export function createImport(addresses: string[]): Promise<ImportCreatedResponse> {
  return request<ImportCreatedResponse>("/api/v1/imports", {
    method: "POST",
    body: JSON.stringify({ addresses }),
  });
}

export function getImportStatus(jobId: string): Promise<JobStatusResponse> {
  return request<JobStatusResponse>(`/api/v1/imports/${jobId}`);
}

export interface TransactionsQuery {
  category?: string;
  minConfidence?: number;
  search?: string;
  sort?: string;
  order?: "asc" | "desc";
  page?: number;
  pageSize?: number;
}

export function getImportTransactions(jobId: string, query: TransactionsQuery = {}): Promise<TransactionsPage> {
  const params = new URLSearchParams();
  if (query.category) params.set("category", query.category);
  if (query.minConfidence !== undefined) params.set("min_confidence", String(query.minConfidence));
  if (query.search) params.set("search", query.search);
  if (query.sort) params.set("sort", query.sort);
  if (query.order) params.set("order", query.order);
  params.set("page", String(query.page ?? 1));
  params.set("page_size", String(query.pageSize ?? 25));

  return request<TransactionsPage>(`/api/v1/imports/${jobId}/transactions?${params.toString()}`);
}

export function exportUrl(jobId: string, format: "csv" | "json"): string {
  return `${API_BASE_URL}/api/v1/imports/${jobId}/export/${format}`;
}
