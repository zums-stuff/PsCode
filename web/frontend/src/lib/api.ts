/**
 * API client — fetch wrapper with Bearer token interceptor.
 *
 * Base URL resolution:
 *   - VITE_API_URL set to a non-empty value → absolute URL (e.g. "https://api.example.com").
 *   - VITE_API_URL set to empty string (LOCAL-FIRST default) → relative URLs
 *     ("/api/*"), which the browser resolves against the current origin and
 *     Caddy proxies to the api container.  Same-origin avoids CORS and works
 *     on the developer laptop (plan §Success Criteria).
 *
 * Non-2xx responses throw ApiError carrying the body's ``detail`` field.
 * The token is injected by AuthProvider via setAuthToken() — the server is
 * the source of truth; the client never verifies anything.
 */

const BASE_URL: string = import.meta.env.VITE_API_URL ?? "";

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

/** List contests with pagination and per-user registration state. */
export function listContests({
  page = 1,
  size = 20,
}: { page?: number; size?: number } = {}): Promise<
  import("./types").Page<import("./types").ContestListItem>
> {
  const qs = new URLSearchParams({
    page: String(page),
    size: String(size),
  });
  return api.get<import("./types").Page<import("./types").ContestListItem>>(
    `/api/contests?${qs.toString()}`,
  );
}

/**
 * Current user's runs for a contest (filtered by contest_id server-side).
 *
 * NOTE the backend returns a **paginated** Page<RunOut> — `{items, page,
 * size, total}` — NOT a bare array.  Callers must read `data.items`.
 */
export function getContestMyRuns(
  contestId: number,
): Promise<import("./types").Page<import("./types").RunOut>> {
  const qs = new URLSearchParams({
    contest_id: String(contestId),
    kind: "contest",
    size: "100",
  });
  return api.get<import("./types").Page<import("./types").RunOut>>(
    `/api/runs?${qs.toString()}`,
  );
}

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

/**
 * Enqueue a run (any mode) with a known source — used by the submissions
 * "Reenviar"/"Reintentar" actions to re-submit an existing run's source as a
 * fresh run (Bug A). Mirrors POST /api/runs' RunCreateRequest shape.
 */
export function createRun(params: {
  problemId: number;
  source: string;
  mode: "practice" | "assignment" | "contest";
  assignmentId?: number | null;
  contestId?: number | null;
}): Promise<{ run_id: number }> {
  return api.post<{ run_id: number }>("/api/runs", {
    problem_id: params.problemId,
    source: params.source,
    mode: params.mode,
    assignment_id: params.assignmentId ?? null,
    contest_id: params.contestId ?? null,
  });
}

/**
 * Re-grade an existing run as a fresh submission (teacher/admin only).
 *
 * Hits ``POST /api/runs/{run_id}/rejudge`` which copies the source/stdin
 * and re-enqueues the run through the same worker pipeline.  Exempt from
 * the per-user runs/submission rate limits (admin action).  Returns the
 * NEW run id so the caller can poll for the verdict.
 */
export function rejudgeRun(runId: number): Promise<{ run_id: number }> {
  // The endpoint reads everything from the path; send no body to keep
  // the request a pure POST (no JSON parsing on the server either).
  return api.post<{ run_id: number }>(`/api/runs/${runId}/rejudge`);
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

/** Fetch a single thread by id (forums index tab). */
export function getSingleThread(
  threadId: number,
): Promise<import("./types").ForumThread> {
  return api.get<import("./types").ForumThread>(`/api/threads/${threadId}`);
}

/** List a thread's posts (forums index / thread detail). */
export function listPosts(
  threadId: number,
): Promise<import("./types").ForumPost[]> {
  return listForumPosts(threadId);
}

/** Create a new thread (forums index modal / per-problem form). */
export function createThread(
  problemId: number,
  title: string,
  body: string,
): Promise<import("./types").ForumThread> {
  return createForumThread(problemId, title, body);
}

/** Post a reply (thread detail / index). `parentId` is optional. */
export function createPost(
  threadId: number,
  body: string,
  parentId?: number,
): Promise<import("./types").ForumPost> {
  return createForumPost(threadId, body, parentId ?? null);
}

/**
 * Paginated forum index across all problems the user can see (forums tab).
 * Optional problem_id / class_id filters are forwarded as query params.
 */
export function listAllThreads(opts?: {
  page?: number;
  size?: number;
  problemId?: number;
  classId?: number;
}): Promise<import("./types").Page<import("./types").ThreadIndexItem>> {
  const qs = new URLSearchParams();
  if (opts?.page !== undefined && opts.page > 1) {
    qs.set("page", String(opts.page));
  }
  if (opts?.size !== undefined) qs.set("size", String(opts.size));
  if (opts?.problemId !== undefined) qs.set("problem_id", String(opts.problemId));
  if (opts?.classId !== undefined) qs.set("class_id", String(opts.classId));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return api.get<import("./types").Page<import("./types").ThreadIndexItem>>(
    `/api/threads${suffix}`,
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

/** Anticheat pairs for a scope (todo 39 / todo 25). */
export function listAnticheatPairs(
  scope: "class" | "contest",
  scopeId: number,
  threshold?: number,
): Promise<import("./types").AnticheatPair[]> {
  const qs = new URLSearchParams({ scope, scope_id: String(scopeId) });
  if (threshold !== undefined) qs.set("threshold", String(threshold));
  return api.get<import("./types").AnticheatPair[]>(
    `/api/admin/anticheat?${qs.toString()}`,
  );
}

/** Pair diff payload (originals + score). */
export function getAnticheatPair(
  runAId: number,
  runBId: number,
): Promise<import("./types").AnticheatPairDetail> {
  return api.get<import("./types").AnticheatPairDetail>(
    `/api/admin/anticheat/pair/${runAId}/${runBId}`,
  );
}

/** Update a class's anticheat threshold. */
export function updateClassAnticheatThreshold(
  classId: number,
  threshold: number,
): Promise<import("./types").ClassOut> {
  return api.post<import("./types").ClassOut>(
    `/api/admin/classes/${classId}/anticheat-threshold`,
    { threshold },
  );
}