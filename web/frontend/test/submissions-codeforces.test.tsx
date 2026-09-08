/**
 * Codeforces-style submissions tests.
 *
 * Covers: default-collapsed rows; inline expansion on row click showing
 * source + verdict + sample cases; hidden cases omitted from collapsed view
 * but shown (with "(oculto)") when expanded; per-problem page same behavior;
 * RunDetailModal summary (sample-only) vs full (all cases) modes.
 *
 * fetch is mocked globally; WebSocket is stubbed.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, type AuthUser } from "../src/lib/auth";
import type { RunOut, RunDetailCaseOut, RunDetailResponse } from "../src/lib/types";
import Submissions from "../src/routes/Submissions";
import ProblemResults from "../src/routes/ProblemResults";
import RunDetailModal from "../src/components/RunDetailModal";

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

const sampleCase = (overrides: Partial<RunDetailCaseOut> = {}): RunDetailCaseOut => ({
  case_index: 0,
  verdict: "AC",
  steps: 3,
  wall_ms: 1,
  output: "3",
  error: null,
  input: "1 2",
  expected_output: "3",
  diff_line: null,
  is_sample: true,
  is_public: true,
  ...overrides,
});

const hiddenCase = (overrides: Partial<RunDetailCaseOut> = {}): RunDetailCaseOut => ({
  case_index: 1,
  verdict: "WA",
  steps: 5,
  wall_ms: 2,
  output: "9",
  error: null,
  input: "xxxxx...",
  expected_output: null,
  diff_line: 1,
  is_sample: false,
  is_public: false,
  ...overrides,
});

const detailWith = (cases: RunDetailCaseOut[]): RunDetailResponse => ({
  run: { ...problemRun(), source: "Proceso main\nFinProceso" },
  test_cases: cases,
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

describe("Codeforces-style submission rows", () => {
  it("renders rows collapsed by default (no test-case list until expanded)", async () => {
    mockFetch({
      "GET /api/runs?page=1&size=20": {
        items: [problemRun({ id: 1, problem_id: 10 })],
        page: 1,
        size: 20,
        total: 1,
      },
    });

    renderAt("/submissions", <Submissions />);
    await screen.findByText("#10");

    expect(document.querySelector(".test-case-list")).toBeNull();
    expect(document.querySelector(".run-expanded-content")).toBeNull();
  });

  it("expands a row on click and shows source, verdict, and first sample case", async () => {
    mockFetch({
      "GET /api/runs?page=1&size=20": {
        items: [problemRun({ id: 1, problem_id: 10, summary_verdict: "AC" })],
        page: 1,
        size: 20,
        total: 1,
      },
      "GET /api/runs/1/detail": detailWith([sampleCase(), hiddenCase()]),
    });

    renderAt("/submissions", <Submissions />);
    await screen.findByText("#10");

    fireEvent.click(screen.getByText("#10").closest("tr") as HTMLElement);

    // source pane + verdict + sample case input/expected render
    expect(await screen.findByText("Casos de muestra")).toBeInTheDocument();
    expect(screen.getAllByText("1 2").length).toBeGreaterThan(0);
    expect(screen.getAllByText("AC").length).toBeGreaterThan(0);
    // source was fetched and rendered via CodeMirror (div with .source-view)
    expect(document.querySelector(".source-view")).toBeInTheDocument();
  });

  it("hidden cases do not appear in the collapsed view", async () => {
    mockFetch({
      "GET /api/runs?page=1&size=20": {
        items: [problemRun({ id: 1, problem_id: 10, summary_verdict: "WA" })],
        page: 1,
        size: 20,
        total: 1,
      },
      "GET /api/runs/1/detail": detailWith([hiddenCase()]),
    });

    renderAt("/submissions", <Submissions />);
    await screen.findByText("#10");

    // no test case list, no oculto marker
    expect(document.querySelector(".test-case-list")).toBeNull();
    expect(screen.queryByText("(oculto)")).not.toBeInTheDocument();
  });

  it("expanded view shows hidden case with (oculto) in the Expected column", async () => {
    mockFetch({
      "GET /api/runs?page=1&size=20": {
        items: [problemRun({ id: 1, problem_id: 10, summary_verdict: "WA" })],
        page: 1,
        size: 20,
        total: 1,
      },
      "GET /api/runs/1/detail": detailWith([
        sampleCase(),
        hiddenCase(),
        hiddenCase({ case_index: 2, verdict: "TLE" }),
      ]),
    });

    renderAt("/submissions", <Submissions />);
    await screen.findByText("#10");
    fireEvent.click(screen.getByText("#10").closest("tr") as HTMLElement);

    // The summary TestCaseList only includes samples by default; the full set
    // + oculto is revealed via "Ver todos los casos".
    const showAll = await screen.findByRole("button", { name: "Ver todos los casos" });
    fireEvent.click(showAll);

    expect(await screen.findAllByText("(oculto)").then((els) => els.length)).toBe(2);
    expect(screen.getAllByText("WA").length).toBeGreaterThan(0);
    expect(screen.getAllByText("TLE").length).toBeGreaterThan(0);
  });

  it("per-problem page (ProblemResults) collapses rows by default and expands inline", async () => {
    mockFetch({
      "GET /api/runs?page=1&size=20&problem_id=1": {
        items: [problemRun({ id: 1, problem_id: 1, summary_verdict: "AC" })],
        page: 1,
        size: 20,
        total: 1,
      },
      "GET /api/runs/1/detail": detailWith([sampleCase()]),
    });

    renderAt(
      "/problem/1/results",
      <Routes>
        <Route path="/problem/:id/results" element={<ProblemResults />} />
      </Routes>,
    );

    await waitFor(() => {
      expect(screen.queryByText("Cargando resultados…")).toBeNull();
    });
    expect(document.querySelector(".test-case-list")).toBeNull();

    const chevron = screen.getByText("▶");
    fireEvent.click(chevron.closest("tr") as HTMLElement);

    expect(await screen.findByText("Casos de muestra")).toBeInTheDocument();
  });
});

describe("RunDetailModal summary vs full modes", () => {
  it("summary mode shows only sample cases", async () => {
    mockFetch({
      "GET /api/runs/1/detail": detailWith([sampleCase(), hiddenCase()]),
    });

    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <MemoryRouter>
          <RunDetailModal
            runId={1}
            mode="summary"
            defaultExpandedCount={2}
            onClose={() => {}}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await screen.findByText("Casos de muestra");
    expect(screen.getAllByText("1 2").length).toBeGreaterThan(0);
    expect(screen.queryByText("(oculto)")).not.toBeInTheDocument();
  });

  it("full mode shows all cases including hidden", async () => {
    mockFetch({
      "GET /api/runs/1/detail": detailWith([sampleCase(), hiddenCase()]),
    });

    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <MemoryRouter>
          <RunDetailModal
            runId={1}
            mode="full"
            defaultExpandedCount={2}
            onClose={() => {}}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findAllByText("(oculto)").then((els) => els.length)).toBe(1);
  });
});
