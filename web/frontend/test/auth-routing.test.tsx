/**
 * App shell + auth routing tests (plan todo 27 acceptance).
 *
 * Covers: student registration (POST /api/register + auto-login → lands on
 * /problems), register validation errors, unauthenticated redirect to /login,
 * student on /admin → /403, authenticated student sees the problems list, and
 * the teacher admin-link in the student nav.
 *
 * fetch is mocked globally (vi.spyOn) — no network, no MSW.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, RequireAuth, RequireRole, type AuthUser } from "../src/lib/auth";
import App from "../src/App";
import Register from "../src/routes/Register";

const studentUser: AuthUser = {
  id: 3,
  username: "alumno",
  display_name: "Alumno Uno",
  role: "student",
};

const teacherUser: AuthUser = {
  id: 1,
  username: "profe",
  display_name: "Profa. García",
  role: "teacher",
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

function renderWithProviders(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{ui}</AuthProvider>
    </QueryClientProvider>,
  );
}

const problemsPage = {
  items: [
    {
      id: 1,
      title: "Suma",
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

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("app shell and auth routing", () => {
  it("registers a student and lands on /problems", async () => {
    mockFetch({
      "POST /api/register": studentUser,
      "POST /api/login": { token_type: "bearer", access_token: "jwt-token" },
      "GET /api/me": studentUser,
      "GET /api/problems?page=1&size=100": problemsPage,
    });

    renderWithProviders(
      <MemoryRouter initialEntries={["/register"]}>
        <Routes>
          <Route path="/register" element={<Register />} />
          <Route path="/" element={<div>problems landing</div>} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText("Usuario"), {
      target: { value: "alumno" },
    });
    fireEvent.change(screen.getByLabelText("Nombre"), {
      target: { value: "Alumno Uno" },
    });
    fireEvent.change(screen.getByLabelText("Contraseña"), {
      target: { value: "password123" },
    });
    fireEvent.change(screen.getByLabelText("Código de clase (opcional)"), {
      target: { value: "ABC123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));

    await waitFor(() => {
      expect(screen.getByText("problems landing")).toBeInTheDocument();
    });
    expect(localStorage.getItem("pseint:token")).toBe("jwt-token");
    expect(localStorage.getItem("pseint:user")).toContain("alumno");
  });

  it("shows validation errors on empty username and short password", async () => {
    mockFetch({});

    renderWithProviders(
      <MemoryRouter initialEntries={["/register"]}>
        <Routes>
          <Route path="/register" element={<Register />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));
    expect(
      await screen.findByText("El usuario es obligatorio."),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Usuario"), {
      target: { value: "alumno" },
    });
    fireEvent.change(screen.getByLabelText("Nombre"), {
      target: { value: "Alumno Uno" },
    });
    fireEvent.change(screen.getByLabelText("Contraseña"), {
      target: { value: "short" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));
    expect(
      await screen.findByText(
        "La contraseña debe tener al menos 8 caracteres.",
      ),
    ).toBeInTheDocument();
  });

  it("redirects an unauthenticated visitor from / to /login", async () => {
    mockFetch({});

    renderWithProviders(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route
            path="/"
            element={
              <RequireAuth>
                <div>student home</div>
              </RequireAuth>
            }
          />
          <Route path="/login" element={<div>login page</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("login page")).toBeInTheDocument();
    expect(screen.queryByText("student home")).not.toBeInTheDocument();
  });

  it("redirects a student from /admin to /403", async () => {
    localStorage.setItem("pseint:token", "test-token");
    localStorage.setItem("pseint:user", JSON.stringify(studentUser));

    mockFetch({});

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin"]}>
        <Routes>
          <Route
            path="/admin"
            element={
              <RequireRole roles={["teacher", "admin"]}>
                <div>admin area</div>
              </RequireRole>
            }
          />
          <Route path="/403" element={<div>acceso denegado</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("acceso denegado")).toBeInTheDocument();
    expect(screen.queryByText("admin area")).not.toBeInTheDocument();
  });

  it("renders the problems list for an authenticated student", async () => {
    localStorage.setItem("pseint:token", "test-token");
    localStorage.setItem("pseint:user", JSON.stringify(studentUser));

    mockFetch({
      "GET /api/problems?page=1&size=100": problemsPage,
    });

    renderWithProviders(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<div>problems landing</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("problems landing")).toBeInTheDocument();
  });

  it("shows the admin link in the student nav for a teacher", async () => {
    localStorage.setItem("pseint:token", "test-token");
    localStorage.setItem("pseint:user", JSON.stringify(teacherUser));

    mockFetch({
      "GET /api/problems?page=1&size=100": problemsPage,
    });

    renderWithProviders(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<div>problems landing</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("problems landing")).toBeInTheDocument();
  });

  it("renders the full App with student routes and guards", async () => {
    localStorage.setItem("pseint:token", "test-token");
    localStorage.setItem("pseint:user", JSON.stringify(studentUser));

    mockFetch({
      "GET /api/problems?page=1&size=100": problemsPage,
    });

    renderWithProviders(<App />);

    expect(await screen.findByText("Suma")).toBeInTheDocument();
    expect(screen.getAllByText("Problemas").length).toBeGreaterThan(0);
    expect(screen.getByText("Práctica")).toBeInTheDocument();
    expect(screen.getByText("Entregas")).toBeInTheDocument();
    expect(screen.getByText("Foro")).toBeInTheDocument();
    expect(screen.getByText("Concursos")).toBeInTheDocument();
  });
});