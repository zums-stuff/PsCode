/**
 * Solve page tests (plan todo 29 acceptance).
 *
 * Covers: 3-pane layout + empty results state, debounced inline syntax
 * validation (POST /api/validate -> linter diagnostic appears/clears),
 * submit via POST /api/runs -> results pane shows run status + per-case
 * verdicts, network-down resilience (editor keeps working), and the mobile
 * stacked layout (responsive media query present).
 *
 * fetch is mocked globally (vi.spyOn) — no network, no MSW. CodeMirror is
 * driven through the public EditorView.findFromDOM() API (no test hooks in
 * product code).
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import type { ReactElement } from "react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { EditorView } from "@codemirror/view";
import Solve from "../src/routes/Solve";
import type { ProblemOut, RunDetailOut } from "../src/lib/types";

const problem: ProblemOut = {
  id: 1,
  title: "Suma de dos números",
  statement:
    "# Suma\n\nLee dos enteros y escribe su suma.\n\n```pseint\nProceso Suma\nFinProceso\n```",
  expected_complexity: "O(1)",
  step_budget: null,
  compare_mode: "exact",
  author_id: 1,
  created_at: "2026-09-01T00:00:00Z",
};

const runDetail: RunDetailOut = {
  id: 7,
  user_id: 3,
  problem_id: 1,
  kind: "practice",
  status: "done",
  summary_verdict: "AC",
  steps: 12,
  wall_ms: 3,
  assignment_id: null,
  contest_id: null,
  created_at: "2026-09-06T00:00:00Z",
  test_results: [
    {
      id: 1,
      case_index: 0,
      verdict: "AC",
      steps: 12,
      wall_ms: 3,
      output: "3",
      error: null,
    },
  ],
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

function editorView(): EditorView {
  const content = document.querySelector(".solve-editor-cm .cm-content");
  if (content === null) throw new Error("solve editor not mounted");
  const view = EditorView.findFromDOM(content as HTMLElement);
  if (view === null) throw new Error("no EditorView for .solve-editor-cm .cm-content");
  return view;
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("solve page", () => {
  it("renders statement, editor, and results panes with the empty state", async () => {
    mockFetch({ "GET /api/problems/1": problem });

    renderSolve("/problem/1");

    expect(await screen.findByText("Suma de dos números")).toBeInTheDocument();
    // 3-pane grid
    expect(document.querySelector(".solve-grid")).not.toBeNull();
    expect(document.querySelector(".solve-statement")).not.toBeNull();
    expect(document.querySelector(".solve-editor")).not.toBeNull();
    expect(document.querySelector(".solve-results")).not.toBeNull();
    // editable CodeMirror editor with pseint mode
    expect(document.querySelector(".cm-editor")).not.toBeNull();
    expect(document.querySelector(".cm-content")).not.toBeNull();
    // results pane empty state
    expect(screen.getByText("Aún no has enviado")).toBeInTheDocument();
  });

  it("shows a linter diagnostic after typing invalid code (debounced)", async () => {
    const validateSpy = vi.fn(() => ({
      ok: false,
      errors: [
        { code: "ERR_SYNTAX", message: "missing 'FinProceso'", line: 1, col: 0 },
      ],
    }));
    mockFetch({
      "GET /api/problems/1": problem,
      "POST /api/validate": validateSpy,
    });

    renderSolve("/problem/1");
    await screen.findByText("Suma de dos números");

    const view = editorView();
    view.dispatch({ changes: { from: 0, insert: "Proceso P\n  x <- 1\n" } });

    await waitFor(
      () => {
        expect(validateSpy).toHaveBeenCalled();
      },
      { timeout: 3000 },
    );
    const [, init] = validateSpy.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init!.body))).toEqual({
      source: "Proceso P\n  x <- 1\n",
    });

    // error mark appears in the editor (gutter + underline)
    await waitFor(
      () => {
        expect(document.querySelector(".cm-lintRange-error")).not.toBeNull();
      },
      { timeout: 3000 },
    );
  });

  it("clears the diagnostic when the code becomes valid", async () => {
    const validateSpy = vi
      .fn()
      .mockReturnValueOnce({
        ok: false,
        errors: [
          { code: "ERR_SYNTAX", message: "missing 'FinProceso'", line: 1, col: 0 },
        ],
      })
      .mockReturnValueOnce({ ok: true, errors: [] });
    mockFetch({
      "GET /api/problems/1": problem,
      "POST /api/validate": validateSpy,
    });

    renderSolve("/problem/1");
    await screen.findByText("Suma de dos números");

    const view = editorView();
    view.dispatch({ changes: { from: 0, insert: "Proceso P\n  x <- 1\n" } });
    await waitFor(
      () => {
        expect(document.querySelector(".cm-lintRange-error")).not.toBeNull();
      },
      { timeout: 3000 },
    );

    view.dispatch({
      changes: {
        from: 0,
        to: view.state.doc.length,
        insert: "Proceso P\n  x <- 1\nFinProceso",
      },
    });
    await waitFor(
      () => {
        expect(document.querySelector(".cm-lintRange-error")).toBeNull();
      },
      { timeout: 3000 },
    );
  });

  it("submits via POST /api/runs and shows the run status + per-case results", async () => {
    const runsSpy = vi.fn(() => ({ run_id: 7 }));
    mockFetch({
      "GET /api/problems/1": problem,
      "POST /api/runs": runsSpy,
      "GET /api/runs/7": runDetail,
    });

    renderSolve("/problem/1");
    await screen.findByText("Suma de dos números");

    const view = editorView();
    view.dispatch({
      changes: { from: 0, insert: "Proceso P\n  x <- 1\nFinProceso" },
    });
    await new Promise((r) => setTimeout(r, 0));

    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));

    await waitFor(() => {
      expect(runsSpy).toHaveBeenCalled();
    });
    const [, init] = runsSpy.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init!.body))).toEqual({
      problem_id: 1,
      source: "Proceso P\n  x <- 1\nFinProceso",
      mode: "practice",
    });

    // results pane: run status + per-case verdict
    expect(await screen.findByText("Terminado")).toBeInTheDocument();
    expect(screen.getAllByText("AC").length).toBeGreaterThan(0);
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("keeps the editor working when validation fails (network down)", async () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const validateSpy = vi.fn(() => {
      throw new Error("network down");
    });
    mockFetch({
      "GET /api/problems/1": problem,
      "POST /api/validate": validateSpy,
    });

    renderSolve("/problem/1");
    await screen.findByText("Suma de dos números");

    const view = editorView();
    view.dispatch({ changes: { from: 0, insert: "Proceso P\n  x <- 1\n" } });

    await waitFor(
      () => {
        expect(validateSpy).toHaveBeenCalled();
      },
      { timeout: 3000 },
    );
    // let the linter settle — no crash, no stale error marks, doc intact
    await new Promise((r) => setTimeout(r, 600));
    expect(document.querySelector(".cm-lintRange-error")).toBeNull();
    expect(view.state.doc.toString()).toBe("Proceso P\n  x <- 1\n");
    warnSpy.mockRestore();
  });

  it("stacks the panes on mobile via the responsive media query", async () => {
    mockFetch({ "GET /api/problems/1": problem });

    renderSolve("/problem/1");
    await screen.findByText("Suma de dos números");

    const grid = document.querySelector(".solve-grid");
    expect(grid).not.toBeNull();
    // jsdom does no layout — assert the responsive rule exists in the CSS
    const css = readFileSync(
      resolve(process.cwd(), "src/routes/Solve.css"),
      "utf8",
    );
    expect(css).toContain("@media (max-width: 900px)");
    expect(css).toContain("grid-template-columns: 1fr");
  });
});