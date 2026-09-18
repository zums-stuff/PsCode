/**
 * Solve page — previous submissions tests.
 *
 * Covers the bug fix: previous runs for the current problem must load on
 * mount via GET /api/runs?problem_id=X. Also covers the contest-materials
 * block visibility (only shown when ?contest= is present).
 */

import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Solve from "../src/routes/Solve";
import type { ProblemOut, RunOut } from "../src/lib/types";

const problem: ProblemOut = {
  id: 1,
  title: "Suma",
  statement: "Lee dos enteros y escribe su suma.",
  expected_complexity: "O(1)",
  step_budget: null,
  compare_mode: "exact",
  author_id: 1,
  created_at: "2026-09-01T00:00:00Z",
};

const previousRun: RunOut = {
  id: 42,
  user_id: 3,
  problem_id: 1,
  kind: "practice",
  status: "done",
  summary_verdict: "AC",
  steps: 12,
  wall_ms: 3,
  assignment_id: null,
  contest_id: null,
  created_at: "2026-09-10T12:00:00Z",
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
    if (handler === undefined) throw new Error(`No mock for ${method} ${path}`);
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

function renderSolve(initialEntry: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const ui: ReactElement = (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/problem/:id" element={<Solve />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
  return render(ui);
}

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("solve page — previous submissions", () => {
  it("shows placeholder when no previous runs exist", async () => {
    mockFetch({
      "GET /api/problems/1": problem,
      "GET /api/runs?page=1&size=10&problem_id=1": {
        items: [],
        page: 1,
        size: 10,
        total: 0,
      },
    });

    renderSolve("/problem/1");
    expect(
      await screen.findByText("Aún no has enviado este problema."),
    ).toBeInTheDocument();
  });

  it("renders 1 row when the API returns 1 previous run", async () => {
    mockFetch({
      "GET /api/problems/1": problem,
      "GET /api/runs?page=1&size=10&problem_id=1": {
        items: [previousRun],
        page: 1,
        size: 10,
        total: 1,
      },
    });

    renderSolve("/problem/1");
    await screen.findByText("Suma");

    const row = await screen.findByTestId("my-run-42");
    expect(row).toBeInTheDocument();
    expect(row).toHaveTextContent("AC");
    expect(row).toHaveTextContent("12");
  });

  it("expands a row on click and shows per-case details", async () => {
    const detailResponse = {
      run: { ...previousRun, source: "Proceso P\nFinProceso" },
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
    };

    mockFetch({
      "GET /api/problems/1": problem,
      "GET /api/runs?page=1&size=10&problem_id=1": {
        items: [previousRun],
        page: 1,
        size: 10,
        total: 1,
      },
      "GET /api/runs/42/detail": detailResponse,
    });

    renderSolve("/problem/1");
    await screen.findByText("Suma");

    const row = await screen.findByTestId("my-run-42");
    fireEvent.click(row);

    await waitFor(() => {
      expect(screen.getByText(/Detalle del envío #42/)).toBeInTheDocument();
    });
    const expandedContent = document.querySelector(".my-runs-expanded-content");
    expect(expandedContent).not.toBeNull();
    expect(expandedContent!.querySelector(".status-badge")).toHaveTextContent("AC");
  });

  it("hides the contest-materials block when there is no ?contest= param", async () => {
    mockFetch({
      "GET /api/problems/1": problem,
      "GET /api/runs?page=1&size=10&problem_id=1": {
        items: [],
        page: 1,
        size: 10,
        total: 0,
      },
    });

    renderSolve("/problem/1");
    await screen.findByText("Suma");

    expect(
      document.querySelector(".solve-contest-materials"),
    ).toBeNull();
  });
});
