/**
 * Student layout tests (bug #2: nav was rendered as a vertical stack on the
 * left with no spacing/active state). The fix introduces a horizontal flex
 * nav with a `student-nav-link-active` highlight.
 *
 * Covers:
 *  - Brand text is rendered (Juez PseInt)
 *  - All five primary nav links render: Problems, Practice, Submissions,
 *    Forum, Contests
 *  - User display name and role render in the user badge
 *  - The active nav link carries `student-nav-link-active` and matches the
 *    current pathname (with `/` exact-match vs prefix-match behaviour)
 *  - Clicking the logout button calls `logout()` AND navigates to `/login`
 *
 * fetch is mocked globally (vi.spyOn) — no network, no MSW. Pattern mirrors
 * the existing admin-dashboard.test.tsx mockFetch helper.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, type AuthUser } from "../src/lib/auth";
import StudentLayout from "../src/routes/StudentLayout";

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

function seedAuth(user: AuthUser) {
  localStorage.setItem("pseint:token", "test-token");
  localStorage.setItem("pseint:user", JSON.stringify(user));
}

function buildQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function renderAt(
  initialPath: string,
  user: AuthUser,
): ReturnType<typeof render> {
  seedAuth(user);
  const queryClient = buildQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={[initialPath]}>
          <StudentLayout />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

function renderWithRoutes(
  initialPath: string,
  user: AuthUser,
): ReturnType<typeof render> {
  seedAuth(user);
  const queryClient = buildQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={[initialPath]}>
          <Routes>
            <Route element={<StudentLayout />}>
              <Route path="/" element={<div>problems landing</div>} />
              <Route path="/practice" element={<div>practice sandbox</div>} />
              <Route
                path="/submissions"
                element={<div>submissions list</div>}
              />
              <Route path="/forum" element={<div>forum landing</div>} />
              <Route path="/contests" element={<div>contests landing</div>} />
              <Route
                path="/admin/problems"
                element={<div>admin area</div>}
              />
              <Route path="/login" element={<div>login page</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  mockFetch({ "GET /api/me": studentUser });
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("student layout - brand + nav links", () => {
  it("renders the brand text and all five primary nav links", () => {
    renderAt("/", studentUser);

    expect(screen.getByTestId("student-brand")).toHaveTextContent("Juez PseInt");

    // Each primary link has a data-testid derived from the path.
    expect(screen.getByTestId("student-nav-home")).toHaveTextContent("Problemas");
    expect(screen.getByTestId("student-nav-practice")).toHaveTextContent("Práctica");
    expect(screen.getByTestId("student-nav-submissions")).toHaveTextContent("Entregas");
    expect(screen.getByTestId("student-nav-forum")).toHaveTextContent("Foro");
    expect(screen.getByTestId("student-nav-contests")).toHaveTextContent("Concursos");
  });

  it("renders the user display name and role in the badge", () => {
    renderAt("/", studentUser);

    const userBadge = screen.getByTestId("student-user");
    expect(userBadge).toHaveTextContent("Alumno Uno");
    expect(userBadge).toHaveTextContent("student");
  });

  it("renders the logout button", () => {
    renderAt("/", studentUser);
    expect(screen.getByTestId("student-logout")).toHaveTextContent("Cerrar sesión");
  });
});

describe("student layout - active link highlighting", () => {
  it("highlights the Problems link on /", () => {
    renderAt("/", studentUser);

    const active = document.querySelectorAll(".student-nav-link-active");
    expect(active).toHaveLength(1);
    expect(active[0]?.textContent).toBe("Problemas");
  });

  it("highlights the Practice link on /practice", () => {
    renderAt("/practice", studentUser);

    const active = document.querySelectorAll(".student-nav-link-active");
    expect(active).toHaveLength(1);
    expect(active[0]?.textContent).toBe("Práctica");
  });

  it("highlights the Submissions link on /submissions", () => {
    renderAt("/submissions", studentUser);

    const active = document.querySelectorAll(".student-nav-link-active");
    expect(active).toHaveLength(1);
    expect(active[0]?.textContent).toBe("Entregas");
  });

  it("highlights the Forum link on /forum/problem/3 (prefix match)", () => {
    renderAt("/forum/problem/3", studentUser);

    const active = document.querySelectorAll(".student-nav-link-active");
    expect(active).toHaveLength(1);
    expect(active[0]?.textContent).toBe("Foro");
  });

  it("does not highlight any link on an unrelated path", () => {
    // Render the layout directly without nested routes so the parent
    // pathname is what we ask for.
    renderAt("/some/unrelated/path", studentUser);

    const active = document.querySelectorAll(".student-nav-link-active");
    expect(active).toHaveLength(0);
  });

  it("does not falsely highlight Problems on /practice (exact-match on /)", () => {
    renderAt("/practice", studentUser);

    const problemsLink = screen.getByTestId("student-nav-home");
    expect(problemsLink.className).not.toMatch(/student-nav-link-active/);
  });
});

describe("student layout - admin link for non-students", () => {
  it("renders the admin link for a teacher", () => {
    renderAt("/", teacherUser);

    expect(screen.getByTestId("student-nav-admin")).toHaveTextContent("Administración");
  });

  it("hides the admin link for a student", () => {
    renderAt("/", studentUser);

    expect(screen.queryByTestId("student-nav-admin")).not.toBeInTheDocument();
  });
});

describe("student layout - logout", () => {
  it("calls logout and navigates to /login when the logout button is clicked", async () => {
    renderWithRoutes("/", studentUser);

    // The header should render before we click.
    expect(await screen.findByTestId("student-logout")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("student-logout"));

    await waitFor(() => {
      expect(screen.getByText("login page")).toBeInTheDocument();
    });

    // Token is cleared by the auth context's logout().
    expect(localStorage.getItem("pseint:token")).toBeNull();
  });
});
