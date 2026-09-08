/**
 * Contest page regression tests (contest-page fix).
 *
 * Guards the blank-page bug reported at /contest/:id. ROOT CAUSE: the
 * student's "my runs" section (MyRuns) called getContestMyRuns(), which is
 * typed as RunOut[] but the backend actually returns a PAGINATED
 * Page<RunOut> ({items, page, size, total}). `data.map` on that object threw
 * a TypeError mid-render → React unmounted the whole tree → blank page.
 *
 * These tests assert the page renders for the real response shapes (incl.
 * the paginated /api/runs payload) and degrades gracefully on 404 / API
 * error instead of going blank. The ErrorBoundary wrapper is also covered.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Contest from "../src/routes/Contest";
import { AuthProvider, type AuthUser } from "../src/lib/auth";

const studentUser: AuthUser = {
  id: 3,
  username: "student01",
  display_name: "Estudiante 01",
  role: "student",
};

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

  static clear(): void {
    MockWebSocket.instances = [];
  }
}

function renderContest(initialEntry: string) {
  localStorage.setItem("pseint:token", "test-token");
  localStorage.setItem("pseint:user", JSON.stringify(studentUser));
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const ui: ReactElement = (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <Routes>
            <Route path="/contest/:id" element={<Contest />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
  return render(ui);
}

const now = Date.now();
const contestRunning = {
  id: 1,
  title: "CF Round 1 — Fibonacci Sprint",
  start_at: new Date(now - 3600_000).toISOString(),
  end_at: new Date(now + 7200_000).toISOString(),
  scoring_mode: "cf",
  teams_enabled: false,
  created_by: 2,
};

const contestProblems = [
  { contest_id: 1, problem_id: 4, order: 0, title: "Fibonacci" },
];

// Real /api/contests/1/scoreboard shape (cf mode, rows present).
const scoreboard = {
  mode: "cf",
  rows: [
    {
      participant_id: "3",
      rank: 1,
      solves: 1,
      penalty: 60,
      points: 0,
      total_ac_cases: 0,
      problems: {},
    },
  ],
};

// REAL /api/runs?contest_id=1&kind=contest shape — a PAGINATED Page, NOT a
// bare array.  This is the payload that used to make the page go blank.
const paginatedRuns = {
  items: [
    {
      id: 4,
      user_id: 3,
      problem_id: 4,
      kind: "contest",
      status: "done",
      summary_verdict: "AC",
      steps: 66,
      wall_ms: 132,
      assignment_id: null,
      contest_id: 1,
      created_at: new Date(now).toISOString(),
    },
  ],
  page: 1,
  size: 100,
  total: 1,
};

const myRunsUrl = "GET /api/runs?contest_id=1&kind=contest&size=100";

beforeEach(() => {
  localStorage.clear();
  MockWebSocket.clear();
  vi.stubGlobal("WebSocket", MockWebSocket);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  localStorage.clear();
  MockWebSocket.clear();
});

describe("Contest page — running phase (blank-page regression)", () => {
  it("renders title, status badge, countdown, problem list, scoreboard and my-runs for the real API shapes", async () => {
    mockFetch({
      "GET /api/contests/1": contestRunning,
      "GET /api/contests/1/contest-problems": contestProblems,
      "GET /api/contests/1/scoreboard": scoreboard,
      [myRunsUrl]: paginatedRuns,
    });

    renderContest("/contest/1");

    // Title (hero h2) + status badge + countdown for a running contest.
    expect(
      await screen.findByText("CF Round 1 — Fibonacci Sprint"),
    ).toBeInTheDocument();
    expect(screen.getByText("En curso")).toBeInTheDocument();
    expect(screen.getByTestId("countdown-timer")).toBeInTheDocument();

    // Problem list links carry the ?contest= context.
    const fibLink = await screen.findByRole("link", { name: /#1 Fibonacci/ });
    expect(fibLink).toHaveAttribute("href", "/problem/4?contest=1");

    // Scoreboard (running phase) renders the seeded row by participant_id.
    expect(screen.getByText("Tabla de posiciones")).toBeInTheDocument();
    await waitFor(() => {
      const rows = screen.getAllByRole("row");
      expect(rows.some((r) => r.textContent?.includes("3"))).toBe(true);
    });

    // My-runs section renders the paginated response's items (NOT blank).
    expect(screen.getByText("Resultados")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("AC")).toBeInTheDocument();
      expect(screen.getByText("66")).toBeInTheDocument();
    });
    // No error boundary visible — the page fully rendered.
    expect(screen.queryByTestId("error-boundary")).not.toBeInTheDocument();
  });

  it("does not go blank when the my-runs payload is paginated (root cause)", async () => {
    mockFetch({
      "GET /api/contests/1": contestRunning,
      "GET /api/contests/1/contest-problems": contestProblems,
      "GET /api/contests/1/scoreboard": { mode: "cf", rows: [] },
      [myRunsUrl]: paginatedRuns,
    });

    renderContest("/contest/1");

    expect(
      await screen.findByText("CF Round 1 — Fibonacci Sprint"),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("AC")).toBeInTheDocument();
      expect(screen.getByText("66")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("error-boundary")).not.toBeInTheDocument();
  });
});

describe("Contest page — graceful error handling (no blank page)", () => {
  it("shows a not-found message when /api/contests/:id returns 404", async () => {
    mockFetch({
      "GET /api/contests/1": {
        __error: { status: 404, detail: "Contest not found" },
      },
    });

    renderContest("/contest/1");

    expect(
      await screen.findByText("Concurso no encontrado."),
    ).toBeInTheDocument();
    // The page shows a useful message instead of a blank div.
    expect(screen.queryByTestId("error-boundary")).not.toBeInTheDocument();
  });

  it("shows a not-found message when /api/contests/:id errors (500)", async () => {
    mockFetch({
      "GET /api/contests/1": {
        __error: { status: 500, detail: "boom" },
      },
    });

    renderContest("/contest/1");

    expect(
      await screen.findByText("Concurso no encontrado."),
    ).toBeInTheDocument();
  });

  it("renders the page (with per-section errors) when the scoreboard API fails", async () => {
    mockFetch({
      "GET /api/contests/1": contestRunning,
      "GET /api/contests/1/contest-problems": contestProblems,
      "GET /api/contests/1/scoreboard": {
        __error: { status: 500, detail: "scoreboard exploded" },
      },
      [myRunsUrl]: { items: [], page: 1, size: 100, total: 0 },
    });

    renderContest("/contest/1");

    // The page still renders: title, problems, my-runs empty state.
    expect(
      await screen.findByText("CF Round 1 — Fibonacci Sprint"),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("link", { name: /#1 Fibonacci/ }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("Aún no hay entregas.")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("error-boundary")).not.toBeInTheDocument();
  });

  it("renders the page even when my-runs itself 500s", async () => {
    mockFetch({
      "GET /api/contests/1": contestRunning,
      "GET /api/contests/1/contest-problems": contestProblems,
      "GET /api/contests/1/scoreboard": { mode: "cf", rows: [] },
      [myRunsUrl]: {
        __error: { status: 500, detail: "runs exploded" },
      },
    });

    renderContest("/contest/1");

    expect(
      await screen.findByText("CF Round 1 — Fibonacci Sprint"),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(
        screen.getByText("No se pudieron cargar los resultados."),
      ).toBeInTheDocument();
    });
    expect(screen.queryByTestId("error-boundary")).not.toBeInTheDocument();
  });
});