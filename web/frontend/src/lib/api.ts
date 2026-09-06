/**
 * API client — fetch wrapper with Bearer token interceptor.
 *
 * Base URL from VITE_API_URL (prod) or http://localhost:8000 (local-first).
 * Non-2xx responses throw ApiError carrying the body's `detail` field.
 * The token is injected by AuthProvider via setAuthToken() — the server is
 * the source of truth; the client never verifies anything.
 */

const BASE_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

let authToken: string | null = null;

export function setAuthToken(token: string | null): void {
  authToken = token;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (authToken !== null) headers.Authorization = `Bearer ${authToken}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const response = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = (await response.json()) as { detail?: unknown };
      if (typeof data.detail === "string") detail = data.detail;
    } catch {
      // non-JSON error body — keep statusText
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string): Promise<T> => request<T>("GET", path),
  post: <T>(path: string, body?: unknown): Promise<T> => request<T>("POST", path, body),
  patch: <T>(path: string, body?: unknown): Promise<T> => request<T>("PATCH", path, body),
  delete: <T>(path: string): Promise<T> => request<T>("DELETE", path),
};

/** Per-student best runs on an assignment (owning teacher or admin only). */
export function getAssignmentSubmissions(
  assignmentId: number,
): Promise<import("./types").AssignmentSubmissionOut[]> {
  return api.get<import("./types").AssignmentSubmissionOut[]>(
    `/api/assignments/${assignmentId}/submissions`,
  );
}

/** Validate PseInt source server-side (todo 29 inline errors). */
export function validateSource(
  source: string,
): Promise<import("./types").ValidateResult> {
  return api.post<import("./types").ValidateResult>("/api/validate", { source });
}