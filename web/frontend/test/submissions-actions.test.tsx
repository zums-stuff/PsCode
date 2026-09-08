/**
 * Submissions Actions column tests (Bug A).
 *
 * Every run row now renders useful actions instead of a blank column:
 *   - done   → "Ver detalle" + "Reenviar" + "Copiar enlace"
 *   - failed → "Ver detalle" + "Reintentar" + "Copiar enlace"
 *   - queued / running → disabled buttons + "Sin acciones…" hint
 *
 * "Ver detalle" toggles the same inline expansion as a row click; Reenviar /
 * Reintentar re-submit the run's REAL source (fetched via /detail) as a new
 * run via POST /api/runs; "Copiar enlace" writes /submissions#<id> to the
 * clipboard. Same actions appear on the per-problem page (ProblemResults).
 *
 * fetch is mocked globally; WebSocket is stubbed (Submissions uses useRunSocket).
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

const detailWithSource = (source: string): RunDetailResponse => ({
  run: { ...problemRun(), source },
  test_cases: [],
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

const listUrl = "GET /api/runs?page=1&size=20";

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

describe("Bug A — submissions actions column", () => {
  it("renders Ver detalle + Reenviar + Copiar enlace for a done run", async () => {
    mockFetch({
      [listUrl]: {
        items: [problemRun()],
        page: 1,
        size: 20,
        total: 1,
      },
    });

    renderAt("/submissions", <Submissions />);
    await screen.findByText("#1");

    expect(screen.getByRole("button", { name: "Ver detalle" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reenviar" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copiar enlace" })).toBeInTheDocument();
    // No "Reintentar" for a done run.
    expect(screen.queryByRole("button", { name: "Reintentar" })).not.toBeInTheDocument();
  });

  it("renders Ver detalle + Reintentar (not Reenviar) for a failed run", async () => {
    mockFetch({
      [listUrl]: {
        items: [problemRun({ status: "failed", summary_verdict: null, steps: null })],
        page: 1,
        size: 20,
        total: 1,
      },
    });

    renderAt("/submissions", <Submissions />);
    await screen.findByText("#1");

    expect(screen.getByRole("button", { name: "Ver detalle" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reenviar" })).not.toBeInTheDocument();
  });

  it("renders disabled buttons + 'Sin acciones' hint for queued/running runs", async () => {
    mockFetch({
      [listUrl]: {
        items: [
          problemRun({ id: 1, status: "queued", summary_verdict: null }),
          problemRun({ id: 2, status: "running", summary_verdict: null }),
        ],
        page: 1,
        size: 20,
        total: 2,
      },
    });

    renderAt("/submissions", <Submissions />);
    await screen.findByText("#1");

    expect(screen.getByText("Sin acciones — la ejecución está en cola")).toBeInTheDocument();
    expect(screen.getByText("Sin acciones — la ejecución está en ejecución")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Ver detalle" }).every((b) => b.hasAttribute("disabled"))).toBe(true);
    expect(screen.getAllByRole("button", { name: "Reenviar" }).every((b) => b.hasAttribute("disabled"))).toBe(true);
  });

  it("Ver detalle toggles the same inline expansion as the row click", async () => {
    mockFetch({
      [listUrl]: {
        items: [problemRun({ id: 7, problem_id: 10 })],
        page: 1,
        size: 20,
        total: 1,
      },
      "GET /api/runs/7/detail": detailWithSource("Proceso main\nFinProceso"),
    });

    renderAt("/submissions", <Submissions />);
    await screen.findByText("#10");

    fireEvent.click(screen.getByRole("button", { name: "Ver detalle" }));
    expect(await screen.findByText("Casos de muestra")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Ver detalle" }));
    await waitFor(() => {
      expect(screen.queryByText("Casos de muestra")).not.toBeInTheDocument();
    });
  });

  it("Reenviar re-submits the run's real source as a practice run when the original was practice", async () => {
    const runSpy = vi.fn(() => ({ run_id: 99 }));
    mockFetch({
      [listUrl]: {
        items: [problemRun({ id: 7, kind: "practice", assignment_id: null })],
        page: 1,
        size: 20,
        total: 1,
      },
      "GET /api/runs/7/detail": detailWithSource("Proceso sumar\nFinProceso"),
      "POST /api/runs": runSpy,
    });

    renderAt("/submissions", <Submissions />);
    await screen.findByText("#1");

    fireEvent.click(screen.getByRole("button", { name: "Reenviar" }));

    await waitFor(() => {
      expect(runSpy).toHaveBeenCalled();
    });
    const [, init] = runSpy.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(String(init!.body));
    expect(body.problem_id).toBe(1);
    expect(body.mode).toBe("practice");
    expect(body.source).toBe("Proceso sumar\nFinProceso");
    expect(body.assignment_id).toBeNull();
  });

  it("Reenviar keeps the original mode for assignment/contest runs", async () => {
    const runSpy = vi.fn(() => ({ run_id: 100 }));
    mockFetch({
      [listUrl]: {
        items: [problemRun({ id: 7, kind: "assignment", assignment_id: 42 })],
        page: 1,
        size: 20,
        total: 1,
      },
      "GET /api/runs/7/detail": detailWithSource("Proceso tarea\nFinProceso"),
      "POST /api/runs": runSpy,
    });

    renderAt("/submissions", <Submissions />);
    await screen.findByText("#1");

    fireEvent.click(screen.getByRole("button", { name: "Reenviar" }));

    await waitFor(() => {
      expect(runSpy).toHaveBeenCalled();
    });
    const [, init] = runSpy.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(String(init!.body));
    expect(body.mode).toBe("assignment");
    expect(body.assignment_id).toBe(42);
    expect(body.source).toBe("Proceso tarea\nFinProceso");
  });

  it("Copiar enlace writes /submissions#<id> to the clipboard and confirms", async () => {
    const clipboardWrite = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: clipboardWrite },
      configurable: true,
    });
    mockFetch({
      [listUrl]: {
        items: [problemRun({ id: 42 })],
        page: 1,
        size: 20,
        total: 1,
      },
    });

    renderAt("/submissions", <Submissions />);
    await screen.findByText("#1");

    fireEvent.click(screen.getByRole("button", { name: "Copiar enlace" }));

    await waitFor(() => {
      expect(clipboardWrite).toHaveBeenCalledTimes(1);
    });
    const copied = String(clipboardWrite.mock.calls[0][0]);
    expect(copied.startsWith(window.location.origin)).toBe(true);
    expect(copied).toContain("/submissions#42");
    // Button label flips to a confirmation.
    expect(await screen.findByRole("button", { name: "¡Copiado!" })).toBeInTheDocument();
  });

  it("per-problem page (ProblemResults) shows the same actions and posts with the run source", async () => {
    const runSpy = vi.fn(() => ({ run_id: 101 }));
    mockFetch({
      "GET /api/runs?page=1&size=20&problem_id=1": {
        items: [problemRun({ id: 7, problem_id: 1 })],
        page: 1,
        size: 20,
        total: 1,
      },
      "GET /api/runs/7/detail": detailWithSource("Proceso main\nFinProceso"),
      "POST /api/runs": runSpy,
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
    expect(screen.getByRole("button", { name: "Ver detalle" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reenviar" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copiar enlace" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Reenviar" }));
    await waitFor(() => {
      expect(runSpy).toHaveBeenCalled();
    });
    const [, init] = runSpy.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(String(init!.body));
    expect(body.problem_id).toBe(1);
    expect(body.mode).toBe("assignment");
    expect(body.source).toBe("Proceso main\nFinProceso");
  });
});