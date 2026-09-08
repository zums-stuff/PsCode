/**
 * Admin contest "create new problem" UI tests.
 *
 * Covers the tabbed ProblemSetEditor: switching to "Crear nuevo" renders the
 * problem form, submitting fires both POST /api/problems (is_public=false)
 * and POST /api/contests/{id}/contest-problems, and success refreshes the
 * contest problem list.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, type AuthUser } from "../src/lib/auth";
import AdminContestDetail from "../src/routes/admin/AdminContestDetail";

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

const now = new Date();
const contestDetail = {
  id: 1,
  title: "Concurso de prueba",
  start_at: new Date(now.getTime() - 3600_000).toISOString(),
  end_at: new Date(now.getTime() + 3600_000).toISOString(),
  scoring_mode: "cf",
  teams_enabled: false,
  created_by: 1,
};

const contestProblems = [
  { contest_id: 1, problem_id: 10, order: 0, title: "Suma" },
];

const participants = [{ user_id: 20, username: "alice" }];
const teams: unknown[] = [];
const cfScoreboard = { mode: "cf", rows: [] as unknown[] };

function baseHandlers() {
  return {
    "GET /api/contests/1": contestDetail,
    "GET /api/contests/1/contest-problems": contestProblems,
    "GET /api/contests/1/participants": participants,
    "GET /api/contests/1/teams": teams,
    "GET /api/contests/1/scoreboard": cfScoreboard,
  };
}

const CREATED_PROBLEM = {
  id: 99,
  title: "Nuevo problema",
  statement: "Enunciado del problema",
  expected_complexity: "O(1)",
  step_budget: null,
  compare_mode: "exact",
  is_public: false,
  author_id: 1,
  created_at: now.toISOString(),
};

const CREATED_CASE = {
  id: 500,
  problem_id: 99,
  input: "1",
  expected_output: "1",
  seed: 0,
  points: 1,
  order: 0,
  is_sample: true,
};

const LINK_RESULT = {
  contest_id: 1,
  problem_id: 99,
  order: 1,
  title: "Nuevo problema",
};

async function fillAndSubmitNewProblemForm() {
  await screen.findByText("Concurso de prueba");
  fireEvent.click(screen.getByRole("tab", { name: "Crear nuevo" }));
  fireEvent.change(screen.getByLabelText("Título"), {
    target: { value: "Nuevo problema" },
  });
  fireEvent.change(screen.getByLabelText("Enunciado"), {
    target: { value: "Enunciado del problema" },
  });
  fireEvent.change(screen.getByLabelText("Complejidad esperada"), {
    target: { value: "O(1)" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Crear y agregar" }));
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("admin contest create-new-problem", () => {
  it("switches to the 'Crear nuevo' tab and renders the problem-creation form", async () => {
    mockFetch(baseHandlers());

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/contests/1"]}>
        <Routes>
          <Route path="/admin/contests/:id" element={<AdminContestDetail />} />
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    await screen.findByText("Concurso de prueba");

    expect(screen.getByRole("tab", { name: "Buscar existente" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Crear nuevo" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Crear nuevo" }));

    expect(screen.getByLabelText("Título")).toBeInTheDocument();
    expect(screen.getByLabelText("Complejidad esperada")).toBeInTheDocument();
    expect(screen.getByLabelText("Modo de comparación")).toBeInTheDocument();
    expect(screen.getByText("Casos de prueba")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Crear y agregar" }),
    ).toBeInTheDocument();
  });

  it("submits the form firing POST /api/problems with is_public=false and then the contest link", async () => {
    const fetchMock = mockFetch({
      ...baseHandlers(),
      "POST /api/problems": CREATED_PROBLEM,
      "POST /api/problems/99/cases": CREATED_CASE,
      "POST /api/contests/1/contest-problems": LINK_RESULT,
    });

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/contests/1"]}>
        <Routes>
          <Route path="/admin/contests/:id" element={<AdminContestDetail />} />
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    await fillAndSubmitNewProblemForm();

    await waitFor(() => {
      const calls = fetchMock.mock.calls;

      const createCall = calls.find(
        ([input, init]) =>
          (init?.method ?? "GET").toUpperCase() === "POST" &&
          String(input) === "/api/problems",
      );
      expect(createCall).toBeDefined();
      if (!createCall) throw new Error("no create call");
      console.log("CREATE_CALL:", JSON.stringify(createCall[1]?.body));
      const body = JSON.parse(String(createCall[1]?.body)) as {
        title: string;
        is_public: boolean;
      };
      expect(body.title).toBe("Nuevo problema");
      expect(body.is_public).toBe(false);

      const linkCall = calls.find(([input]) =>
        String(input).includes("/api/contests/1/contest-problems"),
      );
      expect(linkCall).toBeDefined();
      const linkBody = JSON.parse(String(linkCall?.[1]?.body)) as {
        problem_id: number;
      };
      expect(linkBody.problem_id).toBe(99);
    });
  });

  it("refreshes the contest problem list after a successful create", async () => {
    mockFetch({
      ...baseHandlers(),
      "POST /api/problems": CREATED_PROBLEM,
      "POST /api/problems/99/cases": CREATED_CASE,
      "POST /api/contests/1/contest-problems": LINK_RESULT,
      // Updated list returned on refetch after creation
      "GET /api/contests/1/contest-problems-2": contestProblems,
    });

    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(
      async (input, init) => {
        const url =
          typeof input === "string"
            ? input
            : input instanceof URL
              ? input.toString()
              : input.url;
        const method = (init?.method ?? "GET").toUpperCase();
        const path = url.replace(/^https?:\/\/[^/]+/, "");
        if (method === "GET" && path === "/api/contests/1/contest-problems") {
          // First GET (initial render): original list. Any later GET: updated.
          if (!fetchMock.mock.calls.some(([i]) =>
            String(i).includes("/api/problems"),
          )) {
            return {
              ok: true,
              status: 200,
              json: async () => contestProblems,
            } as Response;
          }
          return {
            ok: true,
            status: 200,
            json: async () => [
              ...contestProblems,
              { contest_id: 1, problem_id: 99, order: 1, title: "Nuevo problema" },
            ],
          } as Response;
        }
        const handlers: Record<string, unknown> = {
          ...baseHandlers(),
        };
        if (method === "POST" && path === "/api/problems")
          return { ok: true, status: 201, json: async () => CREATED_PROBLEM } as Response;
        if (method === "POST" && path === "/api/problems/99/cases")
          return { ok: true, status: 201, json: async () => CREATED_CASE } as Response;
        if (method === "POST" && path === "/api/contests/1/contest-problems")
          return { ok: true, status: 201, json: async () => LINK_RESULT } as Response;
        const handler =
          handlers[`${method} ${path}`] ?? handlers[`${method} *`];
        if (handler === undefined)
          throw new Error(`No mock for ${method} ${path}`);
        const result =
          typeof handler === "function" ? handler(path, init) : handler;
        return { ok: true, status: 200, json: async () => result } as Response;
      },
    );

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/contests/1"]}>
        <Routes>
          <Route path="/admin/contests/:id" element={<AdminContestDetail />} />
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    await fillAndSubmitNewProblemForm();

    // The refetched list contains the new problem row.
    await waitFor(() => {
      expect(screen.getByText("99")).toBeInTheDocument();
    });
    expect(screen.getAllByText("Nuevo problema").length).toBeGreaterThan(0);
  });
});
