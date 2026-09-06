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

/** List a problem's test cases (todo 18); filter is_sample client-side. */
export function getProblemCases(
  problemId: number,
): Promise<import("./types").TestCaseOut[]> {
  return api.get<import("./types").TestCaseOut[]>(
    `/api/problems/${problemId}/cases`,
  );
}

/** Enqueue a practice run with custom stdin (todo 30 sandbox). */
export function submitPracticeRun(
  problemId: number,
  source: string,
  stdin: string,
): Promise<{ run_id: number }> {
  return api.post<{ run_id: number }>("/api/runs", {
    problem_id: problemId,
    source,
    mode: "practice",
    stdin,
  });
}

/** List paginated runs (todo 31 submissions + history). */
export function getRuns(
  page: number,
  size: number,
  problemId?: number,
): Promise<import("./types").Page<import("./types").RunOut>> {
  const qs = new URLSearchParams({ page: String(page), size: String(size) });
  if (problemId !== undefined) qs.set("problem_id", String(problemId));
  return api.get<import("./types").Page<import("./types").RunOut>>(
    `/api/runs?${qs.toString()}`,
  );
}

/** Run + per-case detail (todo 31 hidden-case masking). */
export function getRunDetail(
  runId: number,
): Promise<import("./types").RunDetailResponse> {
  return api.get<import("./types").RunDetailResponse>(
    `/api/runs/${runId}/detail`,
  );
}

/** List a problem's forum threads (todo 18 / todo 33). */
export function listForumThreads(
  problemId: number,
): Promise<import("./types").ForumThread[]> {
  return api.get<import("./types").ForumThread[]>(
    `/api/problems/${problemId}/threads`,
  );
}

/** Create a new thread (todo 18). Returns the new thread. */
export function createForumThread(
  problemId: number,
  title: string,
  body: string,
): Promise<import("./types").ForumThread> {
  return api.post<import("./types").ForumThread>(
    `/api/problems/${problemId}/threads`,
    { title, body },
  );
}

/** List a thread's posts (todo 18). */
export function listForumPosts(
  threadId: number,
): Promise<import("./types").ForumPost[]> {
  return api.get<import("./types").ForumPost[]>(
    `/api/threads/${threadId}/posts`,
  );
}

/** Post a reply on a thread. `parentId` is optional (todo 33 nested replies). */
export function createForumPost(
  threadId: number,
  body: string,
  parentId?: number | null,
): Promise<import("./types").ForumPost> {
  return api.post<import("./types").ForumPost>(
    `/api/threads/${threadId}/posts`,
    { body, parent_id: parentId ?? null },
  );
}

/** Pin / unpin a thread (teacher/admin — todo 33 moderation). */
export function pinForumThread(
  threadId: number,
  pinned: boolean,
): Promise<import("./types").ForumThread> {
  return api.patch<import("./types").ForumThread>(
    `/api/threads/${threadId}`,
    { pinned },
  );
}

/** Edit a post body (teacher/admin — todo 33 moderation). */
export function updateForumPost(
  postId: number,
  body: string,
): Promise<import("./types").ForumPost> {
  return api.patch<import("./types").ForumPost>(`/api/posts/${postId}`, {
    body,
  });
}

/** Delete a post (teacher/admin — todo 33 moderation). */
export function deleteForumPost(postId: number): Promise<void> {
  return api.delete<void>(`/api/posts/${postId}`);
}