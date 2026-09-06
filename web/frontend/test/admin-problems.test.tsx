/**
 * Admin problems UI tests (plan todo 22 acceptance).
 *
 * Covers: list rendering, detail form hydration, inline validation
 * (empty title / empty expected output block submit), the "run sample"
 * validate call, and the student-role guard redirect.
 *
 * fetch is mocked globally (vi.spyOn) — no network, no MSW.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, RequireRole, type AuthUser } from "../src/lib/auth";
import AdminProblems from "../src/routes/admin/AdminProblems";
import AdminProblemDetail from "../src/routes/admin/AdminProblemDetail";

const teacherUser: AuthUser = {
  id: 1,
  username: "profe",
  display_name: "Profa. García",
  role: "teacher",
};

const studentUser: AuthUser = {
  id: 2,
  username: "alumno",
  display_name: "Alumno Uno",
  role: "student",
};

type MockHandler = (path: string, init?: RequestInit) => unknown;

/** Route fetch by `${METHOD} ${path}`; `*` wildcard per method. */
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

function renderWithProviders(ui: ReactElement, user: AuthUser) {
  localStorage.setItem("pseint:token", "test-token");
  localStorage.setItem("pseint:user", JSON.stringify(user));
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{ui}</AuthProvider>
    </QueryClientProvider>,
  );
}

const problemOne = {
  id: 1,
  title: "Suma de dos números",
  statement:
    "Leer dos números y escribir su suma.\n\n```pseint\nProceso Suma\n    Leer a, b\n    Escribir a + b\nFinProceso\n```",
  expected_complexity: "O(1)",
  step_budget: null,
  compare_mode: "exact",
  author_id: 1,
  created_at: "2026-09-05T00:00:00Z",
};

const casesOne = [
  {
    id: 10,
    problem_id: 1,
    input: "2 3",
    expected_output: "5",
    seed: 0,
    points: 1,
    order: 0,
    is_public: false,
    is_sample: true,
  },
  {
    id: 11,
    problem_id: 1,
    input: "10 20",
    expected_output: "30",
    seed: 0,
    points: 1,
    order: 1,
    is_public: false,
    is_sample: false,
  },
];

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("admin problems", () => {
  it("renders problem rows from the mocked list endpoint", async () => {
    mockFetch({
      "GET /api/problems?page=1&size=100": {
        items: [
          {
            id: 1,
            title: "Suma de dos números",
            expected_complexity: "O(1)",
            compare_mode: "exact",
            is_solved: false,
            best_verdict: null,
          },
          {
            id: 2,
            title: "Factorial",
            expected_complexity: "O(n)",
            compare_mode: "exact",
            is_solved: true,
            best_verdict: "AC",
          },
        ],
        page: 1,
        size: 100,
        total: 2,
      },
    });

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/problems"]}>
        <Routes>
          <Route path="/admin/problems" element={<AdminProblems />} />
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    expect(await screen.findByText("Suma de dos números")).toBeInTheDocument();
    expect(screen.getByText("Factorial")).toBeInTheDocument();
    expect(screen.getByText("O(1)")).toBeInTheDocument();
    expect(screen.getByText("O(n)")).toBeInTheDocument();
    // teacher sees per-user solved state
    expect(screen.getByText("Sí")).toBeInTheDocument();
    expect(screen.getByText("No")).toBeInTheDocument();
    // actions per row
    expect(screen.getAllByText("Editar")).toHaveLength(2);
    expect(screen.getAllByText("Eliminar")).toHaveLength(2);
    // new-problem button
    expect(screen.getByRole("link", { name: "Nuevo problema" })).toHaveAttribute(
      "href",
      "/admin/problems/new",
    );
  });

  it("loads problem and test cases and renders the form fields", async () => {
    mockFetch({
      "GET /api/problems/1": problemOne,
      "GET /api/problems/1/cases": casesOne,
    });

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/problems/1"]}>
        <Routes>
          <Route path="/admin/problems/:id" element={<AdminProblemDetail />} />
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    expect(await screen.findByDisplayValue("Suma de dos números")).toBeInTheDocument();
    expect(screen.getByLabelText("Complejidad esperada")).toHaveValue("O(1)");
    expect(screen.getByLabelText("Modo de comparación")).toHaveValue("exact");
    // statement editor holds the markdown
    expect(screen.getByLabelText("Enunciado")).toHaveValue(problemOne.statement);
    // test-case rows hydrated from the cases endpoint
    expect(await screen.findByDisplayValue("2 3")).toBeInTheDocument();
    expect(screen.getByDisplayValue("5")).toBeInTheDocument();
    expect(screen.getByDisplayValue("10 20")).toBeInTheDocument();
    expect(screen.getByDisplayValue("30")).toBeInTheDocument();
    // sample checkbox checked for the sample case
    expect(screen.getByLabelText("Muestra 1")).toBeChecked();
    expect(screen.getByLabelText("Muestra 2")).not.toBeChecked();
  });

  it("blocks save when the title is empty", async () => {
    const fetchMock = mockFetch({});

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/problems/new"]}>
        <Routes>
          <Route path="/admin/problems/new" element={<AdminProblemDetail />} />
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    fireEvent.change(screen.getByLabelText("Complejidad esperada"), {
      target: { value: "O(1)" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("El título es obligatorio.")).toBeInTheDocument();
    const postCalls = fetchMock.mock.calls.filter(
      ([, init]) => (init?.method ?? "GET").toUpperCase() === "POST",
    );
    expect(postCalls).toHaveLength(0);
  });

  it("blocks save when a test case has empty expected output", async () => {
    const fetchMock = mockFetch({});

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/problems/new"]}>
        <Routes>
          <Route path="/admin/problems/new" element={<AdminProblemDetail />} />
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    fireEvent.change(screen.getByLabelText("Título"), {
      target: { value: "Suma" },
    });
    fireEvent.change(screen.getByLabelText("Complejidad esperada"), {
      target: { value: "O(1)" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    expect(
      await screen.findByText("Todos los casos deben tener salida esperada."),
    ).toBeInTheDocument();
    const postCalls = fetchMock.mock.calls.filter(
      ([, init]) => (init?.method ?? "GET").toUpperCase() === "POST",
    );
    expect(postCalls).toHaveLength(0);
  });

  it("runs sample validation and shows errors inline", async () => {
    const fetchMock = mockFetch({
      "GET /api/problems/1": problemOne,
      "GET /api/problems/1/cases": casesOne,
      "POST /api/validate": {
        ok: false,
        errors: [
          {
            code: "ERR_SYNTAX",
            message: "Token inesperado",
            line: 2,
            col: 5,
          },
        ],
      },
    });

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/problems/1"]}>
        <Routes>
          <Route path="/admin/problems/:id" element={<AdminProblemDetail />} />
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    await screen.findByDisplayValue("Suma de dos números");
    fireEvent.click(screen.getByRole("button", { name: "Ejecutar muestra" }));

    expect(await screen.findByText(/Token inesperado/)).toBeInTheDocument();
    const validateCall = fetchMock.mock.calls.find(([input]) =>
      String(input).includes("/api/validate"),
    );
    expect(validateCall).toBeDefined();
    const body = JSON.parse(String(validateCall?.[1]?.body)) as { source: string };
    expect(body.source).toBe(problemOne.statement);
  });

  it("redirects a student to /403 when accessing /admin/problems", async () => {
    mockFetch({});

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/problems"]}>
        <Routes>
          <Route path="/login" element={<div>página de inicio</div>} />
          <Route path="/403" element={<div>acceso denegado</div>} />
          <Route
            path="/admin/problems"
            element={
              <RequireRole roles={["teacher", "admin"]}>
                <div>contenido admin</div>
              </RequireRole>
            }
          />
        </Routes>
      </MemoryRouter>,
      studentUser,
    );

    expect(await screen.findByText("acceso denegado")).toBeInTheDocument();
    expect(screen.queryByText("contenido admin")).not.toBeInTheDocument();
  });
});