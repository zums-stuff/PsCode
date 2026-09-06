/**
 * Admin classes/assignments UI tests (plan todo 23 acceptance).
 *
 * Covers: class list rendering, class-code copy-to-clipboard, class detail
 * (render + inline rename), teacher-of-class guard (teacher B on teacher A's
 * class -> /403), assignment submissions table with source expand + rejudge
 * POST /api/runs, and the student-role guard on the assignment detail.
 *
 * fetch is mocked globally (vi.spyOn) — no network, no MSW.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, type AuthUser } from "../src/lib/auth";
import AdminClasses from "../src/routes/admin/AdminClasses";
import AdminClassDetail from "../src/routes/admin/AdminClassDetail";
import AdminAssignmentDetail from "../src/routes/admin/AdminAssignmentDetail";
import ClassCodeDisplay from "../src/components/ClassCodeDisplay";

const teacherUser: AuthUser = {
  id: 1,
  username: "profe",
  display_name: "Profa. García",
  role: "teacher",
};

const otherTeacherUser: AuthUser = {
  id: 2,
  username: "otro",
  display_name: "Otro Profe",
  role: "teacher",
};

const studentUser: AuthUser = {
  id: 3,
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

const classOne = {
  id: 1,
  name: "Intro a la programación",
  code: "ABC123",
  teacher_id: 1,
  anticheat_threshold: 0.85,
};

const classTwo = {
  id: 2,
  name: "Estructuras de datos",
  code: "XYZ789",
  teacher_id: 1,
  anticheat_threshold: 0.85,
};

const assignmentFive = {
  id: 5,
  problem_id: 3,
  deadline: "2026-09-30T23:59:00Z",
  status: "open",
  best_verdict: null,
  best_steps: null,
};

const problemThree = {
  id: 3,
  title: "Suma de dos números",
  expected_complexity: "O(1)",
  compare_mode: "exact",
  is_solved: false,
  best_verdict: null,
};

const submissionsFive = [
  {
    user_id: 10,
    username: "alice",
    best_verdict: "AC",
    steps: 12,
    source: "Proceso P\n  Escribir 1\nFinProceso\n",
  },
  {
    user_id: 11,
    username: "bob",
    best_verdict: "WA",
    steps: 8,
    source: "Proceso Q\n  Escribir 2\nFinProceso\n",
  },
];

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("admin classes", () => {
  it("renders class rows from the mocked list endpoint", async () => {
    mockFetch({
      "GET /api/classes": [classOne, classTwo],
    });

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/classes"]}>
        <Routes>
          <Route path="/admin/classes" element={<AdminClasses />} />
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    expect(await screen.findByText("Intro a la programación")).toBeInTheDocument();
    expect(screen.getByText("Estructuras de datos")).toBeInTheDocument();
    expect(screen.getByText("ABC123")).toBeInTheDocument();
    expect(screen.getByText("XYZ789")).toBeInTheDocument();
    // copy button per row
    expect(screen.getAllByRole("button", { name: "Copiar código" })).toHaveLength(2);
    // open links per row
    expect(screen.getAllByRole("link", { name: "Abrir" })).toHaveLength(2);
    // new-class button
    expect(screen.getByRole("link", { name: "Nueva clase" })).toHaveAttribute(
      "href",
      "/admin/classes/new",
    );
  });

  it("copies the class code to the clipboard", async () => {
    const writeText = vi
      .spyOn(navigator.clipboard, "writeText")
      .mockResolvedValue(undefined);

    renderWithProviders(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<ClassCodeDisplay code="ABC123" />} />
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    fireEvent.click(screen.getByRole("button", { name: "Copiar código" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("ABC123"));
  });

  it("renders the class detail with the inline rename form", async () => {
    mockFetch({
      "GET /api/classes": [classOne],
      "GET /api/assignments?page=1&size=100": {
        items: [assignmentFive],
        page: 1,
        size: 100,
        total: 1,
      },
      "GET /api/problems?page=1&size=100": {
        items: [problemThree],
        page: 1,
        size: 100,
        total: 1,
      },
      "GET /api/assignments/5/submissions": [],
    });

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/classes/1"]}>
        <Routes>
          <Route path="/admin/classes/:id" element={<AdminClassDetail />} />
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    // class name in the rename input + code displayed with copy button
    expect(await screen.findByDisplayValue("Intro a la programación")).toBeInTheDocument();
    expect(screen.getByText("ABC123")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copiar código" })).toBeInTheDocument();
    // assignments table resolves the problem title
    expect(await screen.findByText("Suma de dos números")).toBeInTheDocument();
    expect(screen.getByText("Abierta")).toBeInTheDocument();
    // new-assignment link
    expect(
      screen.getByRole("link", { name: "Nueva tarea" }),
    ).toHaveAttribute("href", "/admin/classes/1/assignments/new");
  });

  it("redirects teacher B to /403 when opening teacher A's class", async () => {
    mockFetch({
      "GET /api/classes": [classOne],
    });

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/classes/1"]}>
        <Routes>
          <Route path="/403" element={<div>acceso denegado</div>} />
          <Route path="/admin/classes/:id" element={<AdminClassDetail />} />
        </Routes>
      </MemoryRouter>,
      otherTeacherUser,
    );

    expect(await screen.findByText("acceso denegado")).toBeInTheDocument();
  });

  it("renders the submissions table and rejudges via POST /api/runs", async () => {
    const fetchMock = mockFetch({
      "GET /api/assignments?page=1&size=100": {
        items: [assignmentFive],
        page: 1,
        size: 100,
        total: 1,
      },
      "GET /api/assignments/5/submissions": submissionsFive,
      "POST /api/runs": { run_id: 99 },
    });

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/assignments/5"]}>
        <Routes>
          <Route path="/admin/assignments/:id" element={<AdminAssignmentDetail />} />
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    expect(await screen.findByText("alice")).toBeInTheDocument();
    expect(screen.getByText("bob")).toBeInTheDocument();
    expect(screen.getByText("AC")).toBeInTheDocument();
    expect(screen.getByText("WA")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();

    // expand the source for alice's row
    fireEvent.click(screen.getAllByRole("button", { name: "Ver código" })[0]);
    await waitFor(() => {
      const view = document.querySelector(".source-view");
      expect(view?.textContent).toContain("Proceso P");
    });

    // rejudge alice's row -> POST /api/runs with the same params + source
    fireEvent.click(screen.getAllByRole("button", { name: "Rejuzgar" })[0]);
    await waitFor(() => {
      const postCall = fetchMock.mock.calls.find(([input]) =>
        String(input).includes("/api/runs"),
      );
      expect(postCall).toBeDefined();
      const body = JSON.parse(String(postCall?.[1]?.body)) as Record<string, unknown>;
      expect(body).toMatchObject({
        problem_id: 3,
        mode: "assignment",
        assignment_id: 5,
      });
      expect(String(body.source)).toContain("Proceso P");
    });
  });

  it("redirects a student to /403 on the assignment detail", async () => {
    mockFetch({});

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/assignments/5"]}>
        <Routes>
          <Route path="/403" element={<div>acceso denegado</div>} />
          <Route path="/admin/assignments/:id" element={<AdminAssignmentDetail />} />
        </Routes>
      </MemoryRouter>,
      studentUser,
    );

    expect(await screen.findByText("acceso denegado")).toBeInTheDocument();
  });
});