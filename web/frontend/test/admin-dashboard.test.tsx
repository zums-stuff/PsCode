/**
 * Admin dashboard tests (plan todo 26 acceptance).
 *
 * Covers:
 *  - Dashboard renders seeded counts (assignments, contests, submissions)
 *  - Empty state renders when no data (NOT crash)
 *  - Recent submissions link to /submissions
 *  - Upcoming contest link to /admin/contests
 *  - Sidebar anticheat badge updates on flagged-pair count change
 *  - Student role → /403 (re-verified on the new page)
 *
 * fetch is mocked globally (vi.spyOn) — no network, no MSW. Pattern mirrors
 * the existing admin-anticheat.test.tsx mockFetch helper.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, RequireRole, type AuthUser } from "../src/lib/auth";
import AdminLayout from "../src/routes/admin/AdminLayout";
import AdminDashboard from "../src/routes/admin/AdminDashboard";

const teacherUser: AuthUser = {
  id: 1,
  username: "profe",
  display_name: "Profa. García",
  role: "teacher",
};

const adminUser: AuthUser = {
  id: 9,
  username: "admin",
  display_name: "Admin",
  role: "admin",
};

const studentUser: AuthUser = {
  id: 2,
  username: "alumno",
  display_name: "Alumno Uno",
  role: "student",
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

function renderWithProviders(
  ui: ReactElement,
  user: AuthUser,
): ReturnType<typeof render> {
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

function buildHandlers(opts: {
  assignments: { id: number; status: string }[];
  contests: { id: number; status: string; title: string }[];
  classes: { id: number }[];
  flaggedByClass?: Record<number, unknown[]>;
}) {
  const flaggedByClass = opts.flaggedByClass ?? {};
  return {
    "GET /api/assignments?page=1&size=100": {
      items: opts.assignments.map((a, i) => ({
        id: a.id,
        problem_id: i + 1,
        deadline: `2026-12-${String(10 + i).padStart(2, "0")}T23:59:00Z`,
        status: a.status,
        best_verdict: null,
        best_steps: null,
      })),
      page: 1,
      size: 100,
      total: opts.assignments.length,
    },
    "GET /api/problems?page=1&size=100": {
      items: [
        { id: 1, title: "Suma", expected_complexity: "O(1)", compare_mode: "exact", is_solved: false, best_verdict: null },
        { id: 2, title: "Factorial", expected_complexity: "O(n)", compare_mode: "exact", is_solved: false, best_verdict: null },
        { id: 3, title: "Merge", expected_complexity: "O(n log n)", compare_mode: "exact", is_solved: false, best_verdict: null },
      ],
      page: 1,
      size: 100,
      total: 3,
    },
    "GET /api/contests?page=1&size=100": {
      items: opts.contests.map((c, i) => ({
        id: c.id,
        title: c.title,
        start_at: `2026-09-${String(10 + i).padStart(2, "0")}T00:00:00Z`,
        end_at: `2027-01-${String(10 + i).padStart(2, "0")}T00:00:00Z`,
        status: c.status,
        scoring_mode: "cf",
        teams_enabled: false,
        is_registered: false,
      })),
      page: 1,
      size: 100,
      total: opts.contests.length,
    },
    "GET /api/classes": opts.classes.map((c, i) => ({
      id: c.id,
      name: `Clase ${c.id}`,
      code: `CODE${c.id}`,
      teacher_id: teacherUser.id,
      anticheat_threshold: 0.85,
    })),
    "GET /api/assignments/1/submissions": [
      {
        user_id: 11,
        username: "alice",
        best_verdict: "AC",
        steps: 5,
        source: "Proceso P\nFinProceso\n",
      },
    ],
    "GET /api/assignments/2/submissions": [
      {
        user_id: 12,
        username: "bob",
        best_verdict: "WA",
        steps: 20,
        source: "Proceso P\nFinProceso\n",
      },
    ],
    "GET /api/assignments/3/submissions": [
      {
        user_id: 13,
        username: "carol",
        best_verdict: "TLE",
        steps: 1000,
        source: "Proceso P\nFinProceso\n",
      },
    ],
    ...Object.fromEntries(
      opts.classes.map((c) => [
        `GET /api/admin/anticheat?scope=class&scope_id=${c.id}&threshold=0.85`,
        flaggedByClass[c.id] ?? [],
      ]),
    ),
  };
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("admin dashboard - rendered counts", () => {
  it("renders active assignments, upcoming contests, and recent submissions", async () => {
    mockFetch(
      buildHandlers({
        assignments: [
          { id: 1, status: "open" },
          { id: 2, status: "open" },
          { id: 3, status: "closed" },
        ],
        contests: [
          { id: 7, status: "upcoming", title: "Concurso A" },
          { id: 8, status: "running", title: "Concurso B" },
          { id: 9, status: "ended", title: "Concurso C" },
        ],
        classes: [{ id: 1 }],
        flaggedByClass: { 1: [{}] },
      }),
    );

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin"]}>
        <Routes>
          <Route path="/admin" element={<AdminDashboard />} />
          <Route path="/admin/assignments/:id" element={<div>tarea detalle</div>} />
          <Route path="/admin/contests" element={<div>lista concursos</div>} />
          <Route path="/submissions" element={<div>lista entregas</div>} />
          <Route path="/admin/contests/:id" element={<div>concurso detalle</div>} />
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    // Active assignments (open only — id 3 is closed)
    expect(await screen.findByTestId("active-assignments-table")).toBeInTheDocument();
    expect(screen.getByText("Suma")).toBeInTheDocument();
    expect(screen.getByText("Factorial")).toBeInTheDocument();

    // Upcoming + running contests only (id 9 ended is filtered)
    const contestsTable = await screen.findByTestId("upcoming-contests-table");
    expect(contestsTable).toBeInTheDocument();
    expect(contestsTable.textContent).toContain("Concurso A");
    expect(contestsTable.textContent).toContain("Concurso B");
    expect(contestsTable.textContent).not.toContain("Concurso C");

    // Recent submissions: one row per open assignment
    const submissionsTable = await screen.findByTestId("recent-submissions-table");
    expect(submissionsTable).toBeInTheDocument();
    expect(screen.getByText("alice")).toBeInTheDocument();
    expect(screen.getByText("bob")).toBeInTheDocument();

    // Flagged-pair count is rendered (one per class)
    const flagged = screen.getByTestId("flagged-pair-count");
    expect(flagged).toHaveAttribute("data-count", "1");
  });

  it("renders the empty state when no assignments, contests, or submissions exist", async () => {
    mockFetch(
      buildHandlers({
        assignments: [{ id: 1, status: "closed" }],
        contests: [{ id: 7, status: "ended", title: "Concurso viejo" }],
        classes: [],
      }),
    );

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin"]}>
        <Routes>
          <Route path="/admin" element={<AdminDashboard />} />
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    expect(await screen.findByText("Aún no hay actividad.")).toBeInTheDocument();
    expect(screen.getByText("No hay tareas abiertas.")).toBeInTheDocument();
    expect(
      screen.getByText("No hay concursos próximos o en curso."),
    ).toBeInTheDocument();
    expect(screen.getByText("Aún no hay entregas recientes.")).toBeInTheDocument();
    // No flagged pairs when there are no classes
    expect(screen.getByTestId("flagged-pair-count")).toHaveAttribute(
      "data-count",
      "0",
    );
  });
});

describe("admin dashboard - links", () => {
  it("the recent submissions section links to /submissions", async () => {
    mockFetch(
      buildHandlers({
        assignments: [{ id: 1, status: "open" }],
        contests: [],
        classes: [],
      }),
    );

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin"]}>
        <Routes>
          <Route path="/admin" element={<AdminDashboard />} />
          <Route path="/submissions" element={<div>lista entregas</div>} />
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    const link = await screen.findByTestId("view-all-submissions-link");
    expect(link).toHaveAttribute("href", "/submissions");
  });

  it("the upcoming contests section links to /admin/contests", async () => {
    mockFetch(
      buildHandlers({
        assignments: [{ id: 1, status: "open" }],
        contests: [{ id: 7, status: "upcoming", title: "Concurso A" }],
        classes: [],
      }),
    );

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin"]}>
        <Routes>
          <Route path="/admin" element={<AdminDashboard />} />
          <Route path="/admin/contests" element={<div>lista concursos</div>} />
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    const link = await screen.findByTestId("view-all-contests-link");
    expect(link).toHaveAttribute("href", "/admin/contests");
  });
});

describe("admin layout - anticheat badge", () => {
  it("shows the flagged-pair count badge in the sidebar nav", async () => {
    mockFetch(
      buildHandlers({
        assignments: [],
        contests: [],
        classes: [
          { id: 1 },
          { id: 2 },
        ],
        flaggedByClass: { 1: [{}, {}], 2: [{}] },
      }),
    );

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/problems"]}>
        <Routes>
          <Route element={<AdminLayout />}>
            <Route path="/admin/problems" element={<div>página problemas</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    const badge = await screen.findByTestId("admin-nav-anticheat-badge");
    expect(badge).toHaveAttribute("data-count", "3");
    expect(badge).toHaveTextContent("3");
  });

  it("hides the badge when no pairs are flagged", async () => {
    mockFetch(
      buildHandlers({
        assignments: [],
        contests: [],
        classes: [{ id: 1 }],
        flaggedByClass: { 1: [] },
      }),
    );

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/problems"]}>
        <Routes>
          <Route element={<AdminLayout />}>
            <Route path="/admin/problems" element={<div>página problemas</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    // Wait for classes query to settle
    await screen.findByText("Problemas");
    expect(screen.queryByTestId("admin-nav-anticheat-badge")).not.toBeInTheDocument();
  });

  it("updates the badge when the flagged-pair count changes (rerender with new mock)", async () => {
    // First render with one flagged pair.
    mockFetch(
      buildHandlers({
        assignments: [],
        contests: [],
        classes: [{ id: 1 }],
        flaggedByClass: { 1: [{}] },
      }),
    );

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <MemoryRouter initialEntries={["/admin/problems"]}>
            <Routes>
              <Route element={<AdminLayout />}>
                <Route path="/admin/problems" element={<div>página problemas</div>} />
              </Route>
            </Routes>
          </MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>,
    );

    expect(
      (await screen.findByTestId("admin-nav-anticheat-badge")).getAttribute(
        "data-count",
      ),
    ).toBe("1");

    // Re-render with a different mock — a 5-pair count. Same QueryClient
    // so the cached query key updates when the mock changes; the badge
    // re-renders with the new count.
    mockFetch(
      buildHandlers({
        assignments: [],
        contests: [],
        classes: [{ id: 1 }],
        flaggedByClass: { 1: [{}, {}, {}, {}, {}] },
      }),
    );

    queryClient.invalidateQueries({ queryKey: ["admin", "dashboard", "anticheat"] });

    rerender(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <MemoryRouter initialEntries={["/admin/problems"]}>
            <Routes>
              <Route element={<AdminLayout />}>
                <Route path="/admin/problems" element={<div>página problemas</div>} />
              </Route>
            </Routes>
          </MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>,
    );

    await waitFor(() =>
      expect(
        screen.getByTestId("admin-nav-anticheat-badge").getAttribute("data-count"),
      ).toBe("5"),
    );
  });
});

describe("admin dashboard - guard", () => {
  it("redirects a student to /403 when accessing /admin", async () => {
    mockFetch(
      buildHandlers({
        assignments: [],
        contests: [],
        classes: [],
      }),
    );

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin"]}>
        <Routes>
          <Route path="/403" element={<div>acceso denegado</div>} />
          <Route
            path="/admin"
            element={
              <RequireRole roles={["teacher", "admin"]}>
                <AdminDashboard />
              </RequireRole>
            }
          />
        </Routes>
      </MemoryRouter>,
      studentUser,
    );

    expect(await screen.findByText("acceso denegado")).toBeInTheDocument();
    expect(screen.queryByTestId("admin-dashboard")).not.toBeInTheDocument();
  });

  it("renders the admin role label for an admin user", async () => {
    mockFetch(
      buildHandlers({
        assignments: [{ id: 1, status: "open" }],
        contests: [],
        classes: [],
      }),
    );

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin"]}>
        <Routes>
          <Route path="/admin" element={<AdminDashboard />} />
        </Routes>
      </MemoryRouter>,
      adminUser,
    );

    expect(await screen.findByText("Administrador")).toBeInTheDocument();
    expect(
      screen.getByText("Bienvenido, Admin"),
    ).toBeInTheDocument();
  });
});

describe("admin layout - active route highlighting", () => {
  it("applies the active class to the matching nav link", async () => {
    mockFetch(
      buildHandlers({
        assignments: [],
        contests: [],
        classes: [],
      }),
    );

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/contests"]}>
        <Routes>
          <Route element={<AdminLayout />}>
            <Route path="/admin/contests" element={<div>página concursos</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    await screen.findByText("página concursos");
    const activeLinks = document.querySelectorAll(".admin-nav-link-active");
    expect(activeLinks).toHaveLength(1);
    expect(activeLinks[0]?.textContent).toContain("Concursos");
  });
});