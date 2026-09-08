/**
 * Results + history tests (plan todo 31 acceptance).
 *
 * Covers: paginated /submissions table (GET /api/runs); RunDetailModal opens
 * from row click; per-case table with verdict badge, steps, wall_ms, input,
 * expected output (Oculto for hidden cases — plan MUST NOT), and diff_line
 * for WA; BestBadge on assignment-best run; retry button ONLY on
 * infra-failed runs (status=failed); WS run event triggers refetch.
 *
 * fetch is mocked globally (vi.spyOn) — no network, no MSW. WebSocket is
 * replaced with a stub that lets tests push messages to the live hook.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, type AuthUser } from "../src/lib/auth";
import type { RunOut, RunDetailResponse } from "../src/lib/types";
import Submissions from "../src/routes/Submissions";
import ProblemResults from "../src/routes/ProblemResults";

const studentUser: AuthUser = {
  id: 3,
  username: "alumno",
  display_name: "Alumno Uno",
  role: "student",
};

const problemRun = (overrides: Partial<RunOut> = {}): RunOut => ({
  id: 7,
  user_id: 3,
  problem_id: 1,
  kind: "assignment",
  status: "done",
  summary_verdict: "AC",
  steps: 12,
  wall_ms: 3,
  assignment_id: 42,
  contest_id: null,
  created_at: "2026-09-06T00:00:00Z",
  ...overrides,
});

const detailPublic = (): RunDetailResponse => ({
  run: problemRun(),
  test_cases: [
    {
      case_index: 0,
      verdict: "AC",
      steps: 12,
      wall_ms: 3,
      output: "3",
      error: null,
      input: "1 2",
      expected_output: "3",
      diff_line: null,
      is_sample: true,
      is_public: true,
    },
  ],
});

const detailHidden = (): RunDetailResponse => ({
  run: problemRun({ summary_verdict: "WA", steps: 5 }),
  test_cases: [
    {
      case_index: 0,
      verdict: "WA",
      steps: 5,
      wall_ms: 3,
      output: "wrong",
      error: null,
      input: "x".repeat(80) + "...",
      expected_output: null,
      diff_line: 2,
      is_sample: false,
      is_public: false,
    },
  ],
});

type MockHandler = (path: string, init?: RequestInit) => unknown;

function mockFetch(handlers: Record<string, MockHandler | unknown>) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.toString()
          : input.url;
    const method = (init?.method ?? "GET").toUpperCase();
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    const handler = handlers[`${method} ${path}`] ?? handlers[`${method} *`];
    if (handler === undefined) {
      throw new Error(`No mock for ${method} ${path}`);
    }
    const result = typeof handler === "function" ? handler(path, init) : handler;
    if (result && typeof result === "object" && "__error" in result) {
      const err = (result as { __error: { status: number; detail: string } }).__error;
      return {
        ok: false,
        status: err.status,
        json: async () => ({ detail: err.detail }),
      } as Response;
    }
    return { ok: true, status: 200, json: async () => result } as Response;
  });
}

function renderAt(path: string, ui: ReactElement, user: AuthUser | null = studentUser) {
  if (user !== null) {
    localStorage.setItem("pseint:token", "test-token");
    localStorage.setItem("pseint:user", JSON.stringify(user));
  }
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

// --- WebSocket mock ---------------------------------------------------------

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((msg: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  close(): void {
    this.closed = true;
  }

  static push(data: unknown): void {
    const payload = JSON.stringify(data);
    for (const inst of MockWebSocket.instances) {
      if (inst.closed) continue;
      inst.onmessage?.({ data: payload });
    }
  }

  static clear(): void {
    MockWebSocket.instances = [];
  }
}

beforeEach(() => {
  localStorage.clear();
  MockWebSocket.clear();
  vi.stubGlobal("WebSocket", MockWebSocket);
  localStorage.setItem("pseint:token", "test-token");
  localStorage.setItem("pseint:user", JSON.stringify(studentUser));
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  localStorage.clear();
  MockWebSocket.clear();
});

describe("/submissions — paginated runs history", () => {
  it("renders a paginated table of the user's runs", async () => {
    mockFetch({
      "GET /api/runs?page=1&size=20": {
        items: [
          problemRun({ id: 1, problem_id: 10, summary_verdict: "AC", steps: 10 }),
          problemRun({ id: 2, problem_id: 20, summary_verdict: "WA", steps: 20 }),
          problemRun({ id: 3, problem_id: 30, summary_verdict: "TLE", steps: 999 }),
        ],
        page: 1,
        size: 20,
        total: 3,
      },
    });

    renderAt("/submissions", <Submissions />);

    expect(await screen.findByText("#10")).toBeInTheDocument();
    expect(screen.getByText("#20")).toBeInTheDocument();
    expect(screen.getByText("#30")).toBeInTheDocument();
    expect(screen.getAllByText("AC").length).toBeGreaterThan(0);
    expect(screen.getAllByText("WA").length).toBeGreaterThan(0);
    expect(screen.getAllByText("TLE").length).toBeGreaterThan(0);
    // pagination label
    expect(screen.getByText(/Página 1 \/ 1/)).toBeInTheDocument();
  });

  it("navigates to the next page on click", async () => {
    const getSpy = vi.fn((path: string) => {
      if (path.includes("page=1")) {
        return {
          items: [problemRun({ id: 1, problem_id: 10 })],
          page: 1,
          size: 20,
          total: 40,
        };
      }
      if (path.includes("page=2")) {
        return {
          items: [problemRun({ id: 2, problem_id: 20 })],
          page: 2,
          size: 20,
          total: 40,
        };
      }
      throw new Error(`unexpected path ${path}`);
    });
    mockFetch({ "GET *": getSpy });

    renderAt("/submissions", <Submissions />);

    await screen.findByText("#10");
    fireEvent.click(screen.getByRole("button", { name: "Siguiente" }));

    await waitFor(() => {
      expect(getSpy).toHaveBeenCalledWith(
        expect.stringContaining("page=2"),
        expect.anything(),
      );
    });
    expect(await screen.findByText("#20")).toBeInTheDocument();
  });
});

describe("Codeforces-style inline expansion", () => {
  it("expands from a row click and shows the per-case verdict table", async () => {
    mockFetch({
      "GET /api/runs?page=1&size=20": {
        items: [problemRun({ id: 7 })],
        page: 1,
        size: 20,
        total: 1,
      },
      "GET /api/runs/7/detail": detailPublic(),
    });

    renderAt("/submissions", <Submissions />);
    await screen.findByText("#1");

    fireEvent.click(screen.getByText("#1").closest("tr") as HTMLElement);

    expect(await screen.findByText("1 2")).toBeInTheDocument();
    // output "3" and expected "3" both render in the per-case table
    expect(screen.getAllByText("3").length).toBeGreaterThan(0);
  });

  it("renders '(oculto)' for hidden cases (MUST NOT show expected_output)", async () => {
    mockFetch({
      "GET /api/runs?page=1&size=20": {
        items: [problemRun({ id: 8, summary_verdict: "WA", steps: 5 })],
        page: 1,
        size: 20,
        total: 1,
      },
      "GET /api/runs/8/detail": detailHidden(),
    });

    renderAt("/submissions", <Submissions />);
    await screen.findByText("#1");

    fireEvent.click(screen.getByText("#1").closest("tr") as HTMLElement);

    expect(await screen.findByText("(oculto)")).toBeInTheDocument();
    // the masked input renders (first 80 chars + "...")
    expect(screen.getByText("x".repeat(80) + "...")).toBeInTheDocument();
  });

  it("shows the WA diff_line as a safe subset (line number only)", async () => {
    mockFetch({
      "GET /api/runs?page=1&size=20": {
        items: [problemRun({ id: 9, summary_verdict: "WA", steps: 5 })],
        page: 1,
        size: 20,
        total: 1,
      },
      "GET /api/runs/9/detail": detailHidden(),
    });

    renderAt("/submissions", <Submissions />);
    await screen.findByText("#1");

    fireEvent.click(screen.getByText("#1").closest("tr") as HTMLElement);

    expect(await screen.findByText(/Línea que difiere:\s*2/)).toBeInTheDocument();
  });
});

describe("BestBadge", () => {
  it("shows the Mejor badge on the assignment-best run (highest verdict, fewest steps)", async () => {
    mockFetch({
      "GET /api/runs?page=1&size=20": {
        items: [
          problemRun({ id: 1, problem_id: 11, summary_verdict: "WA", steps: 30, assignment_id: 7 }),
          problemRun({ id: 2, problem_id: 11, summary_verdict: "AC", steps: 10, assignment_id: 7 }),
          problemRun({ id: 3, problem_id: 11, summary_verdict: "AC", steps: 50, assignment_id: 7 }),
          problemRun({ id: 4, problem_id: 22, summary_verdict: "AC", steps: 12, assignment_id: 7 }),
        ],
        page: 1,
        size: 20,
        total: 4,
      },
    });

    renderAt("/submissions", <Submissions />);

    // 3 rows for problem 11
    expect(await screen.findAllByText("#11")).toHaveLength(3);

    // id=2 (AC, 10 steps) wins: highest verdict + fewest steps
    const bests = screen.getAllByText("Mejor");
    expect(bests.length).toBeGreaterThan(0);
    // exactly 2 bests: id=2 (assignment 7, problem 11) and id=4 (assignment 7, problem 22)
    expect(bests).toHaveLength(2);
  });

  it("does NOT mark practice runs as best", async () => {
    mockFetch({
      "GET /api/runs?page=1&size=20": {
        items: [
          problemRun({
            id: 1,
            problem_id: 11,
            summary_verdict: "AC",
            steps: 5,
            assignment_id: null,
            kind: "practice",
          }),
        ],
        page: 1,
        size: 20,
        total: 1,
      },
    });

    renderAt("/submissions", <Submissions />);
    await screen.findByText("#11");

    // practice runs are not in any (problem, assignment) group → no Mejor
    expect(screen.queryByText("Mejor")).not.toBeInTheDocument();
  });
});

describe("Retry button (infra-failed only)", () => {
  it("only renders the Retry button for runs with status=failed", async () => {
    mockFetch({
      "GET /api/runs?page=1&size=20": {
        items: [
          problemRun({ id: 1, problem_id: 11, status: "done", summary_verdict: "AC" }),
          problemRun({ id: 2, problem_id: 22, status: "failed", summary_verdict: null, steps: null }),
          problemRun({ id: 3, problem_id: 33, status: "running", summary_verdict: null }),
        ],
        page: 1,
        size: 20,
        total: 3,
      },
    });

    renderAt("/submissions", <Submissions />);
    await screen.findByText("#22");

    const retries = screen.getAllByRole("button", { name: "Reintentar" });
    expect(retries).toHaveLength(1);
  });

  it("clicking Retry on a failed run POSTs /api/runs with the same problem context and source", async () => {
    const runSpy = vi.fn(() => ({ run_id: 99 }));
    mockFetch({
      "GET /api/runs?page=1&size=20": {
        items: [
          problemRun({
            id: 5,
            status: "failed",
            summary_verdict: null,
            steps: null,
            problem_id: 11,
            kind: "assignment",
            assignment_id: 33,
          }),
        ],
        page: 1,
        size: 20,
        total: 1,
      },
      "GET /api/runs/5/detail": {
        run: { ...problemRun({ id: 5, status: "failed" }), source: "Proceso main\nFinProceso" },
        test_cases: [],
      },
      "POST /api/runs": runSpy,
    });

    renderAt("/submissions", <Submissions />);
    await screen.findByText("#11");

    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));

    await waitFor(() => {
      expect(runSpy).toHaveBeenCalled();
    });
    const [, init] = runSpy.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(String(init!.body));
    expect(body.problem_id).toBe(11);
    expect(body.mode).toBe("assignment");
    expect(body.assignment_id).toBe(33);
    expect(body.source).toBe("Proceso main\nFinProceso");
  });
});

describe("WS live-update refetch", () => {
  it("invalidates the runs query when a run event arrives", async () => {
    const fetchSpy = vi.fn((path: string) => {
      if (path.includes("/api/runs")) {
        return {
          items: [problemRun({ id: 1, problem_id: 11, summary_verdict: "AC" })],
          page: 1,
          size: 20,
          total: 1,
        };
      }
      throw new Error(`unexpected ${path}`);
    });
    mockFetch({ "GET *": fetchSpy });

    renderAt("/submissions", <Submissions />);
    await screen.findByText("#11");

    // initial fetch counts as one
    const callsBefore = fetchSpy.mock.calls.length;

    // Push a run event through the mock socket.
    MockWebSocket.push({ submission_id: 99, status: "done", per_case: [] });

    await waitFor(() => {
      expect(fetchSpy.mock.calls.length).toBeGreaterThan(callsBefore);
    });
  });
});

describe("/problem/:id/results — filtered problem history", () => {
  it("renders the filtered runs table for a single problem", async () => {
    mockFetch({
      "GET /api/runs?page=1&size=20&problem_id=1": {
        items: [
          problemRun({
            id: 7,
            problem_id: 1,
            summary_verdict: "AC",
            steps: 12,
            wall_ms: 3,
          }),
        ],
        page: 1,
        size: 20,
        total: 1,
      },
    });

    renderAt(
      "/problem/1/results",
      <Routes>
        <Route path="/problem/:id/results" element={<ProblemResults />} />
      </Routes>,
    );

    // wait for loading state to clear (query resolves)
    await waitFor(() => {
      expect(screen.queryByText("Cargando resultados…")).toBeNull();
    });
    // the row shows the verdict and steps of the single run
    expect(screen.getAllByText("AC").length).toBeGreaterThan(0);
    expect(screen.getByText("12")).toBeInTheDocument();
  });
});
