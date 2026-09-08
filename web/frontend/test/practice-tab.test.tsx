/**
 * /practice tab tests (plan todo 30 — C4 practice UX).
 *
 * Covers:
 *  - Standalone mode: editor + Run button visible without a problem; Run is
 *    disabled with a message; the "Pick a problem" picker is collapsible.
 *  - Problem picker: choosing a problem shows the statement + template;
 *    switching problems resets the editor; deselecting returns to standalone.
 *  - RunModal: pre-fills sample input; shows test cases table when >1 case;
 *    hides it for a single case; POSTs /api/runs {mode:practice}.
 *  - History, WS events, 429 quota notice (existing).
 *
 * fetch is mocked globally (vi.spyOn); WebSocket is a stub.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { EditorView } from "@codemirror/view";
import { AuthProvider, type AuthUser } from "../src/lib/auth";
import Practice from "../src/routes/Practice";
import type {
  Page,
  ProblemListItem,
  ProblemOut,
  RunDetailOut,
  RunOut,
  TestCaseOut,
} from "../src/lib/types";

const studentUser: AuthUser = {
  id: 3,
  username: "alumno",
  display_name: "Alumno Uno",
  role: "student",
};

const problemsPage: Page<ProblemListItem> = {
  items: [
    {
      id: 1,
      title: "Suma de dos números",
      expected_complexity: "O(1)",
      compare_mode: "exact",
      is_solved: true,
      best_verdict: "AC",
    },
    {
      id: 2,
      title: "Primo",
      expected_complexity: "O(n)",
      compare_mode: "exact",
      is_solved: false,
      best_verdict: null,
    },
  ],
  page: 1,
  size: 100,
  total: 2,
};

const problem: ProblemOut = {
  id: 1,
  title: "Suma de dos números",
  statement: "# Suma\n\nLee dos enteros y escribe su suma.\n",
  expected_complexity: "O(1)",
  step_budget: null,
  compare_mode: "exact",
  author_id: 1,
  created_at: "2026-09-01T00:00:00Z",
};

const problemPrimo: ProblemOut = {
  id: 2,
  title: "Primo",
  statement: "# Primo\n\nDetermina si un número es primo.\n",
  expected_complexity: "O(n)",
  step_budget: null,
  compare_mode: "exact",
  author_id: 1,
  created_at: "2026-09-01T00:00:00Z",
};

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

const multiCaseTestCases: TestCaseOut[] = [
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
  {
    id: 2,
    problem_id: 1,
    input: "0\n",
    expected_output: "0\n",
    seed: 1,
    points: 1,
    order: 1,
    is_public: true,
    is_sample: false,
  },
  {
    id: 3,
    problem_id: 1,
    input: "-5\n10\n",
    expected_output: "5\n",
    seed: 2,
    points: 1,
    order: 2,
    is_public: true,
    is_sample: false,
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

function historyRun(overrides: Partial<RunOut> = {}): RunOut {
  const detail = practiceRun(overrides as Partial<RunDetailOut>);
  return {
    id: detail.id,
    user_id: detail.user_id,
    problem_id: detail.problem_id,
    kind: detail.kind,
    status: detail.status,
    summary_verdict: detail.summary_verdict,
    steps: detail.steps,
    wall_ms: detail.wall_ms,
    assignment_id: detail.assignment_id,
    contest_id: detail.contest_id,
    created_at: detail.created_at,
  };
}

function historyPage(items: RunOut[]): Page<RunOut> {
  return { items, page: 1, size: 5, total: items.length };
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

const HISTORY_URL = "/api/runs?page=1&size=5&problem_id=1";
const HISTORY_KEY = `GET ${HISTORY_URL}`;
const HISTORY_URL_2 = "/api/runs?page=1&size=5&problem_id=2";
const HISTORY_KEY_2 = `GET ${HISTORY_URL_2}`;

function baseHandlers(overrides: Record<string, MockHandler | unknown> = {}) {
  return {
    "GET /api/problems?page=1&size=100": problemsPage,
    "GET /api/problems/1": problem,
    "GET /api/problems/1/cases": testCases,
    "GET /api/problems/2": problemPrimo,
    "GET /api/problems/2/cases": [],
    [HISTORY_KEY]: historyPage([historyRun()]),
    [HISTORY_KEY_2]: historyPage([]),
    "GET /api/runs/8": practiceRun(),
    ...overrides,
  };
}

function renderPractice() {
  localStorage.setItem("pseint:token", "test-token");
  localStorage.setItem("pseint:user", JSON.stringify(studentUser));
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const ui: ReactElement = (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={["/practice"]}>
          <Routes>
            <Route path="/practice" element={<Practice />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
  return render(ui);
}

function editorView(): EditorView {
  const content = document.querySelector(".solve-editor-cm .cm-content");
  if (content === null) throw new Error("practice editor not mounted");
  const view = EditorView.findFromDOM(content as HTMLElement);
  if (view === null) throw new Error("no EditorView for .solve-editor-cm .cm-content");
  return view;
}

function editorText(): string {
  return editorView().state.doc.toString();
}

async function selectProblem(value: string) {
  const select = await screen.findByRole("combobox");
  fireEvent.change(select, { target: { value } });
}

async function openRunModal() {
  fireEvent.click(
    await screen.findByRole("button", { name: "Ejecutar muestra" }),
  );
  await screen.findByRole("dialog");
}

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

describe("/practice — standalone mode (no problem selected)", () => {
  it("renders the editor + Run button + output panel without a problem selected", async () => {
    mockFetch(baseHandlers());

    renderPractice();

    expect(await screen.findByRole("heading", { level: 1, name: "Práctica" }))
      .toBeInTheDocument();
    // editor is visible with the default template
    await waitFor(() => {
      expect(editorText()).toBe("Proceso P\n\nFinProceso");
    });
    // Run button is enabled (sandbox mode — runs without a problem too)
    const runBtn = await screen.findByRole("button", { name: "Ejecutar muestra" });
    expect(runBtn).not.toBeDisabled();
    // output placeholder is shown
    expect(
      screen.getByText("Selecciona un problema y ejecuta tu código para ver la salida por caso."),
    ).toBeInTheDocument();
    // standalone hint is shown
    expect(
      screen.getByText("Modo libre: practica sin un problema específico."),
    ).toBeInTheDocument();
  });

  it("clicking Run without a problem selected opens the modal with empty stdin", async () => {
    mockFetch(baseHandlers());

    renderPractice();

    const runBtn = await screen.findByRole("button", { name: "Ejecutar muestra" });
    fireEvent.click(runBtn);
    // the Run modal opens — sandbox runs have empty stdin by default
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("the problem picker is collapsible and starts collapsed when no problem is selected", async () => {
    mockFetch(baseHandlers());

    renderPractice();

    const summary = await screen.findByText("Selecciona un problema…", {
      selector: "summary",
    });
    expect(summary.closest("details")).not.toBeNull();
  });

  it("Reset button in standalone mode restores the default Proceso template", async () => {
    mockFetch(baseHandlers());

    renderPractice();
    await waitFor(() => {
      expect(editorText()).toBe("Proceso P\n\nFinProceso");
    });

    // edit the code
    const view = editorView();
    view.dispatch({
      changes: { from: 0, insert: "Proceso Editado\nFinProceso" },
    });
    await new Promise((r) => setTimeout(r, 0));
    expect(editorText()).toContain("Editado");

    // click Reset
    fireEvent.click(screen.getByRole("button", { name: "Reiniciar" }));
    await waitFor(() => {
      expect(editorText()).toBe("Proceso P\n\nFinProceso");
    });
  });
});

describe("/practice — problem picker + editor", () => {
  it("renders the title and an empty picker, and never auto-selects a problem", async () => {
    mockFetch(baseHandlers());

    renderPractice();

    expect(await screen.findByRole("heading", { level: 1, name: "Práctica" }))
      .toBeInTheDocument();
    const select = await screen.findByRole("combobox");
    expect((select as HTMLSelectElement).value).toBe("");
    expect(screen.getByRole("option", { name: "Selecciona un problema…" }))
      .toBeInTheDocument();
    // editor is visible in standalone mode
    await waitFor(() => {
      expect(editorText()).toBe("Proceso P\n\nFinProceso");
    });
    // no statement (that requires a problem)
    expect(screen.queryByRole("heading", { level: 2, name: "Suma de dos números" })).toBeNull();
  });

  it("selecting a problem shows the statement, the default Proceso template, and an empty history", async () => {
    mockFetch(baseHandlers({ [HISTORY_KEY]: historyPage([]) }));

    renderPractice();
    await selectProblem("1");

    expect(
      await screen.findByRole("heading", { name: "Suma de dos números" }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(editorText()).toBe("Proceso Suma_de_dos_numeros\n\nFinProceso");
    });
    expect(
      await screen.findByText("Aún no has ejecutado código en este problema."),
    ).toBeInTheDocument();
  });

  it("switching problems resets the editor to the new template and clears the previous run", async () => {
    mockFetch(baseHandlers());

    renderPractice();
    await selectProblem("1");
    await waitFor(() => {
      expect(editorText()).toBe("Proceso Suma_de_dos_numeros\n\nFinProceso");
    });

    // edit the code…
    const view = editorView();
    view.dispatch({
      changes: { from: 0, insert: "Proceso Editado\nFinProceso" },
    });
    await new Promise((r) => setTimeout(r, 0));

    // …then switch to problem 2
    await selectProblem("2");
    await waitFor(() => {
      expect(editorText()).toBe("Proceso Primo\n\nFinProceso");
    });
    // the previous run/output is cleared (placeholder back)
    expect(
      await screen.findByText(
        "Selecciona un problema y ejecuta tu código para ver la salida por caso.",
      ),
    ).toBeInTheDocument();
  });

  it("deselecting the problem returns to standalone mode with the default template", async () => {
    mockFetch(baseHandlers());

    renderPractice();
    await selectProblem("1");
    await waitFor(() => {
      expect(editorText()).toBe("Proceso Suma_de_dos_numeros\n\nFinProceso");
    });

    // deselect (pick empty value)
    await selectProblem("");
    await waitFor(() => {
      expect(editorText()).toBe("Proceso P\n\nFinProceso");
    });
    // standalone hint reappears
    expect(
      screen.getByText("Modo libre: practica sin un problema específico."),
    ).toBeInTheDocument();
    // Run button stays enabled in standalone mode (sandbox-friendly)
    expect(screen.getByRole("button", { name: "Ejecutar muestra" })).not.toBeDisabled();
  });
});

describe("/practice — practice runs (model:practice, never graded)", () => {
  it("Ejecutar muestra POSTs /api/runs with mode=practice and renders per-case output", async () => {
    const runsSpy = vi.fn(() => ({ run_id: 8 }));
    mockFetch(baseHandlers({ "POST /api/runs": runsSpy }));

    renderPractice();
    await selectProblem("1");
    await waitFor(() => {
      expect(editorText()).toBe("Proceso Suma_de_dos_numeros\n\nFinProceso");
    });

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
      source: "Proceso Suma_de_dos_numeros\n\nFinProceso",
      mode: "practice",
      stdin: "21\n",
    });

    // modal closed, per-case rows rendered (verdict AC, steps, output)
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    const stepsCells = await screen.findAllByText("12");
    expect(stepsCells.length).toBeGreaterThan(0);
    expect(screen.getAllByText("AC").length).toBeGreaterThan(0);
    expect(screen.getAllByText("42").length).toBeGreaterThan(0);
  });

  it("shows a friendly quota notice when the run POST returns 429", async () => {
    mockFetch(
      baseHandlers({
        "POST /api/runs": {
          __error: { status: 429, detail: "rate limit exceeded" },
        },
      }),
    );

    renderPractice();
    await selectProblem("1");
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
});

describe("/practice — RunModal test cases table", () => {
  it("shows the test cases table when the problem has >1 test case", async () => {
    mockFetch(
      baseHandlers({
        "GET /api/problems/1/cases": multiCaseTestCases,
      }),
    );

    renderPractice();
    await selectProblem("1");
    await openRunModal();

    await screen.findByRole("dialog");

    // the summary shows the count
    expect(
      screen.getByText("Casos de prueba (3)"),
    ).toBeInTheDocument();
    // the table has 3 data rows
    const rows = screen.getAllByRole("row");
    // header row + 3 data rows = 4
    expect(rows.length).toBe(4);
    // inputs are shown
    expect(screen.getAllByText(/21/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/^0/).length).toBeGreaterThan(0);
    // expected outputs are shown
    expect(screen.getAllByText(/42/).length).toBeGreaterThan(0);
  });

  it("does NOT show the test cases table when the problem has exactly 1 test case", async () => {
    mockFetch(baseHandlers());

    renderPractice();
    await selectProblem("1");
    await openRunModal();

    await screen.findByRole("dialog");

    // no "Casos de prueba" summary
    expect(screen.queryByText(/Casos de prueba/)).toBeNull();
    // no table
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("pre-fills stdin with the sample case input (first sample found)", async () => {
    mockFetch(
      baseHandlers({
        "GET /api/problems/1/cases": multiCaseTestCases,
      }),
    );

    renderPractice();
    await selectProblem("1");
    await openRunModal();

    await screen.findByRole("dialog");
    await waitFor(() => {
      expect((screen.getByLabelText("Entrada") as HTMLTextAreaElement).value).toBe(
        "21\n",
      );
    });
  });
});

describe("/practice — run history", () => {
  it("shows only practice runs for the problem (assignment runs filtered out)", async () => {
    const assignmentRun: RunOut = {
      ...historyRun({ id: 99, kind: "assignment", assignment_id: 42 }),
    };
    mockFetch(
      baseHandlers({
        [HISTORY_KEY]: historyPage([historyRun(), assignmentRun]),
      }),
    );

    renderPractice();
    await selectProblem("1");

    expect(await screen.findByRole("button", { name: /#8/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /#99/ })).toBeNull();
    expect(
      screen.queryByText("Aún no has ejecutado código en este problema."),
    ).toBeNull();
  });

  it("clicking a history row loads that run's detail into the output panel", async () => {
    mockFetch(baseHandlers());

    renderPractice();
    await selectProblem("1");

    fireEvent.click(await screen.findByRole("button", { name: /#8/ }));

    // poll fetches GET /api/runs/8 → per-case rows with verdict + steps
    const stepsCells = await screen.findAllByText("12");
    expect(stepsCells.length).toBeGreaterThan(0);
    expect(screen.getAllByText("AC").length).toBeGreaterThan(0);
    expect(screen.getAllByText("42").length).toBeGreaterThan(0);
  });

  it("a WS run event invalidates the history query (refetch)", async () => {
    const historySpy = vi.fn(() => historyPage([historyRun()]));
    mockFetch(
      baseHandlers({
        [HISTORY_KEY]: historySpy as unknown,
        "POST /api/runs": { run_id: 8 },
      }),
    );

    renderPractice();
    await selectProblem("1");
    await screen.findByRole("button", { name: /#8/ });

    const callsBefore = historySpy.mock.calls.length;

    MockWebSocket.push({ submission_id: 5, status: "done", per_case: [] });

    await waitFor(() => {
      expect(historySpy.mock.calls.length).toBeGreaterThan(callsBefore);
    });
  });

  it("history section shows a message when no problem is selected", async () => {
    mockFetch(baseHandlers());

    renderPractice();

    const matches = await screen.findAllByText("Selecciona un problema para ejecutar tu código.");
    // appears in both the editor hint and the history section
    expect(matches.length).toBe(2);
  });
});
