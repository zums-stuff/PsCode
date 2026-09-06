/**
 * Admin contests UI tests (plan todo 24 acceptance).
 *
 * Covers: contest list rendering, status badge (running), contest detail with
 * teams_enabled=true renders TeamsPanel, teams_enabled=false hides it (plan
 * QA), PhaseAwareActions disables add-participant before start, CF scoreboard
 * sorts solves desc/penalty asc, IOI scoreboard sorts total desc, and the
 * student / non-owner-teacher /403 guard.
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
import AdminContests from "../src/routes/admin/AdminContests";
import AdminContestDetail from "../src/routes/admin/AdminContestDetail";
import ContestStatusBadge from "../src/components/ContestStatusBadge";
import ContestScoreboard from "../src/components/ContestScoreboard";
import PhaseAwareActions from "../src/components/PhaseAwareActions";

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

const now = new Date();
const contestOne = {
  id: 1,
  title: "Concurso de prueba",
  start_at: new Date(now.getTime() - 3600_000).toISOString(),
  end_at: new Date(now.getTime() + 3600_000).toISOString(),
  status: "running",
  scoring_mode: "cf",
  teams_enabled: false,
  is_registered: false,
};

const contestTwo = {
  id: 2,
  title: "Concurso IOI",
  start_at: new Date(now.getTime() + 3600_000).toISOString(),
  end_at: new Date(now.getTime() + 7200_000).toISOString(),
  status: "upcoming",
  scoring_mode: "ioi",
  teams_enabled: true,
  is_registered: false,
};

const contestDetail = {
  id: 1,
  title: "Concurso de prueba",
  start_at: new Date(now.getTime() - 3600_000).toISOString(),
  end_at: new Date(now.getTime() + 3600_000).toISOString(),
  scoring_mode: "cf",
  teams_enabled: false,
  created_by: 1,
};

const contestDetailTeams = {
  ...contestDetail,
  teams_enabled: true,
};

const contestProblems = [
  { contest_id: 1, problem_id: 10, order: 0, title: "Suma" },
  { contest_id: 1, problem_id: 11, order: 1, title: "Resta" },
];

const participants = [
  { user_id: 20, username: "alice" },
  { user_id: 21, username: "bob" },
];

const teams = [
  { id: 5, contest_id: 1, name: "Equipo A", created_at: now.toISOString() },
];

const cfScoreboard = {
  mode: "cf",
  rows: [
    {
      participant_id: "20",
      rank: 1,
      solves: 2,
      penalty: 40,
      points: 0,
      total_ac_cases: 0,
      problems: {},
    },
    {
      participant_id: "21",
      rank: 2,
      solves: 1,
      penalty: 5,
      points: 0,
      total_ac_cases: 0,
      problems: {},
    },
  ],
};

const ioiScoreboard = {
  mode: "ioi",
  rows: [
    {
      participant_id: "20",
      rank: 1,
      solves: 0,
      penalty: 0,
      points: 5,
      total_ac_cases: 2,
      problems: {},
    },
    {
      participant_id: "21",
      rank: 2,
      solves: 0,
      penalty: 0,
      points: 2,
      total_ac_cases: 1,
      problems: {},
    },
  ],
};

function detailHandlers(overrides: Record<string, unknown> = {}) {
  return {
    "GET /api/contests/1": overrides.contest ?? contestDetail,
    "GET /api/contests/1/contest-problems": overrides.problems ?? contestProblems,
    "GET /api/contests/1/participants": overrides.participants ?? participants,
    "GET /api/contests/1/teams": overrides.teams ?? teams,
    "GET /api/contests/1/scoreboard": overrides.scoreboard ?? cfScoreboard,
  };
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("admin contests", () => {
  it("renders contest rows from the mocked list endpoint", async () => {
    mockFetch({
      "GET /api/contests?page=1&size=100": {
        items: [contestOne, contestTwo],
        page: 1,
        size: 100,
        total: 2,
      },
    });

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/contests"]}>
        <Routes>
          <Route path="/admin/contests" element={<AdminContests />} />
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    expect(await screen.findByText("Concurso de prueba")).toBeInTheDocument();
    expect(screen.getByText("Concurso IOI")).toBeInTheDocument();
    // status badges
    expect(screen.getAllByTestId("contest-status")).toHaveLength(2);
    expect(screen.getByText("En curso")).toBeInTheDocument();
    expect(screen.getByText("Próximo")).toBeInTheDocument();
    // scoring modes
    expect(screen.getByText("Codeforces")).toBeInTheDocument();
    expect(screen.getByText("IOI")).toBeInTheDocument();
    // teams flags
    expect(screen.getByText("No")).toBeInTheDocument();
    expect(screen.getByText("Sí")).toBeInTheDocument();
    // open links + new button
    expect(screen.getAllByRole("link", { name: "Abrir" })).toHaveLength(2);
    expect(screen.getByRole("link", { name: "Nuevo concurso" })).toHaveAttribute(
      "href",
      "/admin/contests/new",
    );
  });

  it("renders the running badge when now is between start and end", () => {
    renderWithProviders(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route
            path="/"
            element={
              <ContestStatusBadge
                startAt={contestOne.start_at}
                endAt={contestOne.end_at}
                now={now}
              />
            }
          />
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    expect(screen.getByText("En curso")).toBeInTheDocument();
    expect(screen.getByTestId("contest-status")).toHaveClass("status-green");
  });

  it("renders TeamsPanel when teams_enabled=true", async () => {
    mockFetch(detailHandlers({ contest: contestDetailTeams }));

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/contests/1"]}>
        <Routes>
          <Route path="/admin/contests/:id" element={<AdminContestDetail />} />
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    expect(await screen.findByText("Concurso de prueba")).toBeInTheDocument();
    // teams panel visible: team list + create form
    expect((await screen.findAllByText("Equipo A")).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Crear equipo" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Agregar miembro" })).toBeInTheDocument();
  });

  it("hides TeamsPanel when teams_enabled=false", async () => {
    mockFetch(detailHandlers());

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/contests/1"]}>
        <Routes>
          <Route path="/admin/contests/:id" element={<AdminContestDetail />} />
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    expect(await screen.findByText("Concurso de prueba")).toBeInTheDocument();
    // hidden-state text shown, no team CRUD
    expect(
      screen.getByText("El modo de equipos está deshabilitado."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Crear equipo" })).not.toBeInTheDocument();
    expect(screen.queryByText("Equipo A")).not.toBeInTheDocument();
  });

  it("disables add-participant when upcoming, enables when running", async () => {
    const { rerender } = renderWithProviders(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route
            path="/"
            element={
              <PhaseAwareActions phase="upcoming">
                <button type="button">Agregar clase</button>
                <button type="button">Agregar individual</button>
              </PhaseAwareActions>
            }
          />
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    expect(screen.getByRole("button", { name: "Agregar clase" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Agregar individual" })).toBeDisabled();

    rerender(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <AuthProvider>
          <MemoryRouter initialEntries={["/"]}>
            <Routes>
              <Route
                path="/"
                element={
                  <PhaseAwareActions phase="running">
                    <button type="button">Agregar clase</button>
                    <button type="button">Agregar individual</button>
                  </PhaseAwareActions>
                }
              />
            </Routes>
          </MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByRole("button", { name: "Agregar clase" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Agregar individual" })).toBeEnabled();
  });

  it("renders CF scoreboard rows sorted solves desc, penalty asc", async () => {
    mockFetch({
      "GET /api/contests/1/scoreboard": cfScoreboard,
    });

    renderWithProviders(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route
            path="/"
            element={
              <ContestScoreboard
                contestId={1}
                scoringMode="cf"
                teamsEnabled={false}
                teams={[]}
                participants={participants}
              />
            }
          />
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    expect(await screen.findByText("alice")).toBeInTheDocument();
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0].textContent).toContain("alice");
    expect(rows[0].textContent).toContain("2");
    expect(rows[0].textContent).toContain("40");
    expect(rows[1].textContent).toContain("bob");
    expect(rows[1].textContent).toContain("1");
    expect(rows[1].textContent).toContain("5");
  });

  it("renders IOI scoreboard rows sorted total_score desc", async () => {
    mockFetch({
      "GET /api/contests/1/scoreboard": ioiScoreboard,
    });

    renderWithProviders(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route
            path="/"
            element={
              <ContestScoreboard
                contestId={1}
                scoringMode="ioi"
                teamsEnabled={false}
                teams={[]}
                participants={participants}
              />
            }
          />
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    expect(await screen.findByText("alice")).toBeInTheDocument();
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0].textContent).toContain("alice");
    expect(rows[0].textContent).toContain("5");
    expect(rows[1].textContent).toContain("bob");
    expect(rows[1].textContent).toContain("2");
  });

  it("redirects a student to /403 on the contest detail", async () => {
    mockFetch({});

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/contests/1"]}>
        <Routes>
          <Route path="/403" element={<div>acceso denegado</div>} />
          <Route path="/admin/contests/:id" element={<AdminContestDetail />} />
        </Routes>
      </MemoryRouter>,
      studentUser,
    );

    expect(await screen.findByText("acceso denegado")).toBeInTheDocument();
  });

  it("redirects a non-owner teacher to /403 on the contest detail", async () => {
    mockFetch({
      "GET /api/contests/1": contestDetail,
    });

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/contests/1"]}>
        <Routes>
          <Route path="/403" element={<div>acceso denegado</div>} />
          <Route path="/admin/contests/:id" element={<AdminContestDetail />} />
        </Routes>
      </MemoryRouter>,
      otherTeacherUser,
    );

    expect(await screen.findByText("acceso denegado")).toBeInTheDocument();
  });
});