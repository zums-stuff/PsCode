import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, type AuthUser } from "../src/lib/auth";
import Practice from "../src/routes/Practice";
import type {
  Page,
  ProblemListItem,
  ProblemOut,
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
      is_solved: false,
      best_verdict: null,
    },
  ],
  page: 1,
  size: 100,
  total: 1,
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
  is_public: true,
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

function historyRun(overrides: Partial<RunOut> = {}): RunOut {
  return {
    id: 10,
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
    ...overrides,
  };
}

function historyPage(items: RunOut[]): Page<RunOut> {
  return { items, page: 1, size: 10, total: items.length };
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

const HISTORY_KEY = "GET /api/runs?page=1&size=10&problem_id=1";

function baseHandlers(overrides: Record<string, MockHandler | unknown> = {}) {
  return {
    "GET /api/problems?page=1&size=100": problemsPage,
    "GET /api/problems/1": problem,
    "GET /api/problems/1/cases": testCases,
    [HISTORY_KEY]: historyPage([]),
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

describe("/practice — previous runs sidebar", () => {
  it("shows 'no runs yet' message when a problem is selected and history is empty", async () => {
    mockFetch(baseHandlers({ [HISTORY_KEY]: historyPage([]) }));

    renderPractice();

    const select = await screen.findByRole("combobox");
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(select, { target: { value: "1" } });

    expect(
      await screen.findByText("Aún no has ejecutado código en este problema."),
    ).toBeInTheDocument();
  });

  it("renders a table with 2 rows when history has 2 runs", async () => {
    const runs = [
      historyRun({ id: 10, summary_verdict: "AC", steps: 12, created_at: "2026-09-06T10:00:00Z" }),
      historyRun({ id: 11, summary_verdict: "WA", steps: 20, created_at: "2026-09-06T09:00:00Z" }),
    ];
    mockFetch(baseHandlers({ [HISTORY_KEY]: historyPage(runs) }));

    renderPractice();

    const select = await screen.findByRole("combobox");
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(select, { target: { value: "1" } });

    await screen.findByTestId("practice-history-10");
    await screen.findByTestId("practice-history-11");

    expect(screen.getByTestId("practice-history-10")).toBeInTheDocument();
    expect(screen.getByTestId("practice-history-11")).toBeInTheDocument();

    const acBadges = screen.getAllByText("AC");
    expect(acBadges.length).toBeGreaterThan(0);
    const waBadges = screen.getAllByText("WA");
    expect(waBadges.length).toBeGreaterThan(0);

    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("20")).toBeInTheDocument();
  });

  it("shows 'select a problem first' hint in standalone mode (no problem selected)", async () => {
    mockFetch(baseHandlers());

    renderPractice();

    expect(
      (await screen.findAllByText("Selecciona un problema y ejecuta tu código para ver la salida por caso.")).length,
    ).toBeGreaterThanOrEqual(1);

    expect(screen.queryByRole("table")).toBeNull();
  });
});
