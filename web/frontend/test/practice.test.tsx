/**
 * Practice sandbox tests (plan todo 30 acceptance).
 *
 * Covers: RunModal opens from "Ejecutar muestra" and pre-fills the sample
 * input; Ejecutar POSTs /api/runs with mode=practice + stdin and the output
 * panel renders per-case rows; 429 quota shows a friendly notice; TLE over
 * the step budget shows the suggested fix; CE renders the compiler error;
 * practice runs are never graded (kind=practice, no graded-results entry).
 *
 * fetch is mocked globally (vi.spyOn) — no network, no MSW.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { EditorView } from "@codemirror/view";
import Solve from "../src/routes/Solve";
import type { ProblemOut, RunDetailOut, TestCaseOut } from "../src/lib/types";

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

const tleProblem: ProblemOut = { ...problem, step_budget: 100 };

const testCases: TestCaseOut[] = [
  {
    id: 1,
    problem_id: 1,
    input: "21\n",
    expected_output: "42\n",
    seed: 0,
    points: 1,
    order: 0,
    is_public: true,
    is_sample: true,
  },
];

function practiceRun(overrides: Partial<RunDetailOut> = {}): RunDetailOut {
  return {
    id: 8,
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
        id: 2,
        case_index: 0,
        verdict: "AC",
        steps: 12,
        wall_ms: 3,
        output: "42",
        error: null,
      },
    ],
    ...overrides,
  };
}

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

async function openRunModal() {
  fireEvent.click(screen.getByRole("button", { name: "Ejecutar muestra" }));
  await screen.findByRole("dialog");
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("practice sandbox", () => {
  it("opens the RunModal and pre-fills the sample input from the problem cases", async () => {
    mockFetch({
      "GET /api/problems/1": problem,
      "GET /api/problems/1/cases": testCases,
    });

    renderSolve("/problem/1");
    await screen.findByText("Suma de dos números");

    await openRunModal();

    const textarea = screen.getByLabelText("Entrada") as HTMLTextAreaElement;
    await waitFor(() => {
      expect(textarea.value).toBe("21\n");
    });
  });

  it("POSTs /api/runs with mode=practice + stdin, closes the modal, and shows per-case rows", async () => {
    const runsSpy = vi.fn(() => ({ run_id: 8 }));
    mockFetch({
      "GET /api/problems/1": problem,
      "GET /api/problems/1/cases": testCases,
      "POST /api/runs": runsSpy,
      "GET /api/runs/8": practiceRun(),
    });

    renderSolve("/problem/1");
    await screen.findByText("Suma de dos números");

    const view = editorView();
    view.dispatch({
      changes: { from: 0, insert: "Proceso P\n  Leer n\n  Escribir n*2\nFinProceso" },
    });
    await new Promise((r) => setTimeout(r, 0));

    await openRunModal();
    await waitFor(() => {
      expect((screen.getByLabelText("Entrada") as HTMLTextAreaElement).value).toBe(
        "21\n",
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Ejecutar" }));

    await waitFor(() => {
      expect(runsSpy).toHaveBeenCalled();
    });
    const [, init] = runsSpy.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init!.body))).toEqual({
      problem_id: 1,
      source: "Proceso P\n  Leer n\n  Escribir n*2\nFinProceso",
      mode: "practice",
      stdin: "21\n",
    });

    // modal closed
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });

    // output panel with per-case rows
    expect(await screen.findByText("Práctica")).toBeInTheDocument();
    expect(screen.getAllByText("AC").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/42/).length).toBeGreaterThan(0);
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("shows a friendly quota notice when the run POST returns 429", async () => {
    mockFetch({
      "GET /api/problems/1": problem,
      "GET /api/problems/1/cases": testCases,
      "POST /api/runs": {
        __error: { status: 429, detail: "rate limit exceeded" },
      },
    });

    renderSolve("/problem/1");
    await screen.findByText("Suma de dos números");

    await openRunModal();
    await waitFor(() => {
      expect((screen.getByLabelText("Entrada") as HTMLTextAreaElement).value).toBe(
        "21\n",
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Ejecutar" }));

    expect(
      await screen.findByText(
        "Límite de envíos alcanzado. Intenta de nuevo en un minuto.",
      ),
    ).toBeInTheDocument();
    // modal stays open so the user keeps their input
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("shows the suggested fix when TLE exceeds the step budget", async () => {
    mockFetch({
      "GET /api/problems/1": tleProblem,
      "GET /api/problems/1/cases": testCases,
      "POST /api/runs": { run_id: 8 },
      "GET /api/runs/8": practiceRun({
        summary_verdict: "TLE",
        steps: 150,
        test_results: [
          {
            id: 2,
            case_index: 0,
            verdict: "TLE",
            steps: 150,
            wall_ms: 3,
            output: null,
            error: null,
          },
        ],
      }),
    });

    renderSolve("/problem/1");
    await screen.findByText("Suma de dos números");

    await openRunModal();
    await waitFor(() => {
      expect((screen.getByLabelText("Entrada") as HTMLTextAreaElement).value).toBe(
        "21\n",
      );
    });
    fireEvent.click(screen.getByRole("button", { name: "Ejecutar" }));

    expect(
      await screen.findByText(
        "Sugerencia: Tu código excede el límite de pasos. Revisa si hay bucles infinitos o reduce la complejidad.",
      ),
    ).toBeInTheDocument();
  });

  it("renders the compiler error in a <pre> block for a CE verdict", async () => {
    mockFetch({
      "GET /api/problems/1": problem,
      "GET /api/problems/1/cases": testCases,
      "POST /api/runs": { run_id: 8 },
      "GET /api/runs/8": practiceRun({
        summary_verdict: "CE",
        test_results: [
          {
            id: 2,
            case_index: 0,
            verdict: "CE",
            steps: null,
            wall_ms: null,
            output: null,
            error: "error de sintaxis: falta FinProceso",
          },
        ],
      }),
    });

    renderSolve("/problem/1");
    await screen.findByText("Suma de dos números");

    await openRunModal();
    await waitFor(() => {
      expect((screen.getByLabelText("Entrada") as HTMLTextAreaElement).value).toBe(
        "21\n",
      );
    });
    fireEvent.click(screen.getByRole("button", { name: "Ejecutar" }));

    expect(
      await screen.findByText("error de sintaxis: falta FinProceso"),
    ).toBeInTheDocument();
    const pre = screen.getByText("error de sintaxis: falta FinProceso").closest("pre");
    expect(pre).not.toBeNull();
  });

  it("never grades practice runs (kind=practice, no graded-results entry)", async () => {
    const runsSpy = vi.fn(() => ({ run_id: 8 }));
    mockFetch({
      "GET /api/problems/1": problem,
      "GET /api/problems/1/cases": testCases,
      "POST /api/runs": runsSpy,
      "GET /api/runs/8": practiceRun(),
    });

    renderSolve("/problem/1");
    await screen.findByText("Suma de dos números");

    await openRunModal();
    await waitFor(() => {
      expect((screen.getByLabelText("Entrada") as HTMLTextAreaElement).value).toBe(
        "21\n",
      );
    });
    fireEvent.click(screen.getByRole("button", { name: "Ejecutar" }));

    await waitFor(() => {
      expect(runsSpy).toHaveBeenCalled();
    });
    const [, init] = runsSpy.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init!.body)).mode).toBe("practice");

    // practice output appears…
    expect(await screen.findByText("Práctica")).toBeInTheDocument();
    // …but the graded results pane stays in its empty state (never graded)
    expect(screen.getByText("Aún no has enviado")).toBeInTheDocument();
    // the run itself is kind=practice
    const runDetail = practiceRun();
    expect(runDetail.kind).toBe("practice");
  });
});