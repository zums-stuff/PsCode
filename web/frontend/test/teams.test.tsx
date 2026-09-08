/**
 * Contest teams mode tests (teams-fix).
 *
 * Covers the end-to-end team flow that was broken/missing:
 *   1. TeamsPanel renders existing teams (member count + members).
 *   2. "Crear equipo" opens the create modal, submits, new team appears.
 *   3. "Agregar miembro" opens the student picker, submits, new member appears.
 *   4. Contest.tsx renders <TeamsPanel> when teams_enabled=true.
 *   5. Contest.tsx does NOT render <TeamsPanel> when teams_enabled=false.
 *   6. ContestScoreboard renders team names (not student names) when teams.
 *
 * fetch is mocked globally; AuthProvider is driven from localStorage.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, type AuthUser } from "../src/lib/auth";
import TeamsPanel from "../src/components/TeamsPanel";
import ContestScoreboard from "../src/components/ContestScoreboard";
import Contest from "../src/routes/Contest";
import type { ContestTeam } from "../src/lib/types";

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
    const basePath = path.split("?")[0];
    const handler =
      handlers[`${method} ${path}`] ??
      handlers[`${method} ${basePath}`] ??
      handlers[`${method} *`];
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

const teacherUser: AuthUser = {
  id: 2,
  username: "prof",
  display_name: "Profesor",
  role: "teacher",
};

const studentUser: AuthUser = {
  id: 3,
  username: "student01",
  display_name: "Estudiante 01",
  role: "student",
};

function setUser(user: AuthUser | null) {
  localStorage.setItem("pseint:token", "test-token");
  if (user) localStorage.setItem("pseint:user", JSON.stringify(user));
  else localStorage.removeItem("pseint:user");
}

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderContest(initialEntry: string) {
  const queryClient = makeQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <Routes>
            <Route path="/contest/:id" element={<Contest />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

function renderTeamsPanel({
  onChanged = () => {},
}: {
  onChanged?: () => void;
}) {
  const queryClient = makeQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <TeamsPanel
          contestId={1}
          phase="running"
          teamsEnabled={true}
          onChanged={onChanged}
        />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

function renderScoreboard({
  teams,
  participants,
}: {
  teams: ContestTeam[];
  participants: { user_id: number; username: string }[];
}) {
  const queryClient = makeQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ContestScoreboard
          contestId={1}
          scoringMode="cf"
          teamsEnabled
          teams={teams}
          participants={participants}
        />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

const teamA: ContestTeam = {
  id: 1,
  contest_id: 1,
  name: "Los Rayos",
  created_at: new Date().toISOString(),
  members: [3, 4],
};

const teamB: ContestTeam = {
  id: 2,
  contest_id: 1,
  name: "Titanes",
  created_at: new Date().toISOString(),
  members: [5],
};

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

describe("TeamsPanel — teacher/admin management", () => {
  it("renders existing teams with member count and member ids", async () => {
    setUser(teacherUser);
    mockFetch({ "GET /api/contests/1/teams": [teamA, teamB] });
    renderTeamsPanel();

    expect(screen.getByTestId("teams-panel")).toBeInTheDocument();
    expect(await screen.findByText("Los Rayos")).toBeInTheDocument();
    expect(screen.getByText("Titanes")).toBeInTheDocument();
    // Member counts: 2 / 1 (singular vs plural string).
    await waitFor(() => {
      expect(screen.getByText("1 miembro")).toBeInTheDocument();
    });
    // Member ids listed per team.
    await waitFor(() => {
      expect(screen.getByTestId("team-member-3")).toBeInTheDocument();
      expect(screen.getByTestId("team-member-4")).toBeInTheDocument();
      expect(screen.getByTestId("team-member-5")).toBeInTheDocument();
    });
  });

  it("Crear equipo opens the modal, submits, and the new team appears", async () => {
    setUser(teacherUser);
    const onChanged = vi.fn();
    // After POST, refetch returns the union list.
    let teams: ContestTeam[] = [teamA];
    mockFetch({
      "GET /api/contests/1/teams": () => teams,
      "POST /api/contests/1/teams": (path, init) => {
        const body = JSON.parse(String(init?.body));
        const created: ContestTeam = {
          id: 99,
          contest_id: 1,
          name: body.name,
          created_at: new Date().toISOString(),
          members: [],
        };
        teams = [...teams, created];
        return created;
      },
    });
    renderTeamsPanel({ onChanged });

    fireEvent.click(await screen.findByTestId("open-create-team"));
    expect(screen.getByLabelText("Nombre del equipo")).toBeInTheDocument();

    fireEvent.change(screen.getByTestId("create-team-name"), {
      target: { value: "Nuevo Equipo" },
    });
    fireEvent.click(screen.getByTestId("create-team-submit"));

    // Internal refetch picks up the created team.
    expect(await screen.findByText("Nuevo Equipo")).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalled();
  });

  it("Agregar miembro opens the student picker, submits, and the member appears", async () => {
    setUser(teacherUser);
    const onChanged = vi.fn();
    let teams: ContestTeam[] = [teamA];
    const participants = [
      { user_id: 3, username: "student01" },
      { user_id: 5, username: "student02" },
    ];
    mockFetch({
      "GET /api/contests/1/teams": () => teams,
      "GET /api/contests/1/participants": participants,
      "POST /api/contests/1/teams/1/members": () => {
        teams = [{ ...teamA, members: [...teamA.members, 5] }];
        return { team_id: 1, user_id: 5 };
      },
    });
    renderTeamsPanel({ onChanged });

    fireEvent.click(await screen.findByTestId("open-add-member-1"));
    await screen.findByText("student02 (#5)");

    fireEvent.change(screen.getByTestId("member-select-1"), {
      target: { value: "5" },
    });
    fireEvent.click(screen.getByTestId("add-member-1"));

    // Member #5 appears after the internal refetch.
    expect(await screen.findByTestId("team-member-5")).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalled();
  });
});

describe("TeamsPanel — student view", () => {
  it("shows Mi equipo when the student is a member of a team", async () => {
    setUser(studentUser); // id 3, member of teamA
    mockFetch({ "GET /api/contests/1/teams": [teamA, teamB] });
    renderTeamsPanel();

    expect(await screen.findByTestId("my-team")).toHaveTextContent(
      "Mi equipo: Los Rayos",
    );
    // No management controls for a student.
    expect(screen.queryByTestId("open-create-team")).not.toBeInTheDocument();
    expect(screen.queryByTestId("teams-panel")).not.toBeInTheDocument();
  });

  it("shows No estás en un equipo todavía for a student not in a team", async () => {
    const outsider: AuthUser = { ...studentUser, id: 99 };
    setUser(outsider);
    mockFetch({ "GET /api/contests/1/teams": [teamA, teamB] });
    renderTeamsPanel();

    expect(await screen.findByTestId("no-team")).toHaveTextContent(
      "No estás en un equipo todavía.",
    );
  });

  it("renders nothing when teams_enabled is false", () => {
    setUser(teacherUser);
    const { container } = render(
      <QueryClientProvider client={makeQueryClient()}>
        <AuthProvider>
          <TeamsPanel contestId={1} phase="running" teamsEnabled={false} />
        </AuthProvider>
      </QueryClientProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("Contest page — teams mode wiring", () => {
  const now = Date.now();

  it("renders <TeamsPanel> when teams_enabled=true", async () => {
    setUser(teacherUser);
    const contestRunning = {
      id: 1,
      title: "Concurso por equipos",
      start_at: new Date(now - 3600_000).toISOString(),
      end_at: new Date(now + 3600_000).toISOString(),
      scoring_mode: "cf",
      teams_enabled: true,
      created_by: 2,
    };
    mockFetch({
      "GET /api/contests/1": contestRunning,
      "GET /api/contests/1/contest-problems": [],
      "GET /api/contests/1/scoreboard": { mode: "cf", rows: [] },
      "GET /api/contests/1/teams": [teamA],
      "GET /api/runs": { items: [], page: 1, size: 100, total: 0 },
    });

    renderContest("/contest/1");

    expect(await screen.findByText("Concurso por equipos")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("teams-panel")).toBeInTheDocument();
    });
    expect(screen.getByText("Los Rayos")).toBeInTheDocument();
  });

  it("does NOT render <TeamsPanel> when teams_enabled=false", async () => {
    setUser(teacherUser);
    const contestRunning = {
      id: 1,
      title: "Concurso individual",
      start_at: new Date(now - 3600_000).toISOString(),
      end_at: new Date(now + 3600_000).toISOString(),
      scoring_mode: "cf",
      teams_enabled: false,
      created_by: 2,
    };
    mockFetch({
      "GET /api/contests/1": contestRunning,
      "GET /api/contests/1/contest-problems": [],
      "GET /api/contests/1/scoreboard": { mode: "cf", rows: [] },
      "GET /api/runs": { items: [], page: 1, size: 100, total: 0 },
    });

    renderContest("/contest/1");

    await screen.findByText("Concurso individual");
    await waitFor(() => {
      // No "Equipos" section was rendered at all.
      expect(screen.queryByTestId("teams-panel")).not.toBeInTheDocument();
      expect(screen.queryByText("Equipos")).not.toBeInTheDocument();
    });
  });
});

describe("ContestScoreboard — team rows", () => {
  it("renders team names (not student names) when teams_enabled", async () => {
    mockFetch({
      "GET /api/contests/1/scoreboard": {
        mode: "cf",
        rows: [
          {
            participant_id: "1",
            rank: 1,
            solves: 1,
            penalty: 10,
            points: 0,
            total_ac_cases: 0,
            problems: {},
          },
        ],
      },
    });

    renderScoreboard({
      teams: [
        { id: 1, contest_id: 1, name: "Los Rayos", created_at: "", members: [3] },
      ],
      participants: [{ user_id: 3, username: "student01" }],
    });

    // The team name is shown, not any student username.
    expect(await screen.findByText("Los Rayos")).toBeInTheDocument();
    expect(screen.queryByText("student01")).not.toBeInTheDocument();
  });
});
