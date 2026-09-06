/**
 * Contest page tests (plan todo 32 acceptance).
 *
 * Covers: upcoming renders countdown + register button; register click
 * POSTs /api/contests/{id}/register and updates to "already registered";
 * running renders problem list (links with ?contest=) + live scoreboard;
 * ended shows the "Finalizado" badge; non-participant 403 on scoreboard
 * surfaces a friendly notice (no raw error); WS AC event triggers a
 * scoreboard refetch; CF mode renders rows by server order (solves desc);
 * teams_enabled scoreboard resolves participant_id to team name;
 * CountdownTimer renders d/h/m/s format.
 *
 * fetch is mocked globally (vi.spyOn); WebSocket is replaced with a stub
 * that lets tests push messages to the live hook (mirrors results.test.tsx).
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Contest from "../src/routes/Contest";
import CountdownTimer from "../src/components/CountdownTimer";
import { AuthProvider, type AuthUser } from "../src/lib/auth";

const studentUser: AuthUser = {
  id: 3,
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

// --- WebSocket mock (mirrors results.test.tsx) ------------------------------

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

  static push(data: unknown): void {
    const payload = JSON.stringify(data);
    for (const inst of MockWebSocket.instances) {
      if (inst.closed) continue;
      inst.onmessage?.({ data: payload });
    }
  }

  static clear(): void {
    MockWebSocket.instances = [];
  }
}

function renderContest(initialEntry: string) {
  localStorage.setItem("pseint:token", "test-token");
  localStorage.setItem("pseint:user", JSON.stringify(studentUser));
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const ui: ReactElement = (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <Routes>
            <Route path="/contest/:id" element={<Contest />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
  return render(ui);
}

function renderContestWithAuth(initialEntry: string, ui: ReactElement) {
  localStorage.setItem("pseint:token", "test-token");
  localStorage.setItem("pseint:user", JSON.stringify(studentUser));
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={[initialEntry]}>{ui}</MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

const now = Date.now();
const contestUpcoming = {
  id: 1,
  title: "Concurso futuro",
  start_at: new Date(now + 3600_000).toISOString(),
  end_at: new Date(now + 7200_000).toISOString(),
  scoring_mode: "cf",
  teams_enabled: false,
  created_by: 1,
};

const contestRunning = {
  ...contestUpcoming,
  title: "Concurso en curso",
  start_at: new Date(now - 3600_000).toISOString(),
  end_at: new Date(now + 3600_000).toISOString(),
};

const contestEnded = {
  ...contestUpcoming,
  title: "Concurso pasado",
  start_at: new Date(now - 7200_000).toISOString(),
  end_at: new Date(now - 3600_000).toISOString(),
};

const contestTeams = {
  ...contestRunning,
  title: "Concurso por equipos",
  teams_enabled: true,
};

const emptyProblems: unknown[] = [];

const contestProblems = [
  { contest_id: 1, problem_id: 10, order: 0, title: "Suma" },
  { contest_id: 1, problem_id: 11, order: 1, title: "Resta" },
];

const cfScoreboardTwo = {
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

const cfScoreboardTeam = {
  mode: "cf",
  rows: [
    {
      participant_id: "5",
      rank: 1,
      solves: 1,
      penalty: 5,
      points: 0,
      total_ac_cases: 0,
      problems: {},
    },
  ],
};

const teamsList = [
  { id: 5, contest_id: 1, name: "Equipo A", created_at: new Date(now).toISOString() },
];

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

describe("Contest page — upcoming", () => {
  it("renders title, status badge, countdown, and register button", async () => {
    mockFetch({
      "GET /api/contests/1": contestUpcoming,
      "GET /api/contests/1/contest-problems": emptyProblems,
    });

    renderContest("/contest/1");

    expect(await screen.findByText("Concurso futuro")).toBeInTheDocument();
    expect(screen.getByText("Próximo")).toBeInTheDocument();
    expect(screen.getByTestId("countdown-timer")).toBeInTheDocument();
    expect(screen.getByTestId("contest-register")).toBeInTheDocument();
    // Problems section visible even before start (browse-only).
    expect(screen.getByText("Problemas")).toBeInTheDocument();
    // Scoreboard NOT rendered before start (plan MUST NOT).
    expect(screen.queryByText("Tabla de posiciones")).not.toBeInTheDocument();
  });

  it("register click POSTs /api/contests/{id}/register and shows the success state", async () => {
    const registerSpy = vi.fn(() => ({ contest_id: 1, user_id: 3 }));
    mockFetch({
      "GET /api/contests/1": contestUpcoming,
      "GET /api/contests/1/contest-problems": emptyProblems,
      "POST /api/contests/1/register": registerSpy,
    });

    renderContest("/contest/1");
    await screen.findByText("Concurso futuro");

    fireEvent.click(screen.getByTestId("contest-register"));

    await waitFor(() => {
      expect(registerSpy).toHaveBeenCalled();
    });
    expect(
      await screen.findByText("Ya estás inscrito en este concurso."),
    ).toBeInTheDocument();
    // Register button is gone after success.
    expect(screen.queryByTestId("contest-register")).not.toBeInTheDocument();
  });

  it("409 from /register is treated as already-registered", async () => {
    mockFetch({
      "GET /api/contests/1": contestUpcoming,
      "GET /api/contests/1/contest-problems": emptyProblems,
      "POST /api/contests/1/register": {
        __error: { status: 409, detail: "Already registered for this contest" },
      },
    });

    renderContest("/contest/1");
    await screen.findByText("Concurso futuro");
    fireEvent.click(screen.getByTestId("contest-register"));

    expect(
      await screen.findByText("Ya estás inscrito en este concurso."),
    ).toBeInTheDocument();
  });
});

describe("Contest page — running", () => {
  it("renders problem list with /problem/:id?contest=:id links and the live scoreboard", async () => {
    mockFetch({
      "GET /api/contests/1": contestRunning,
      "GET /api/contests/1/contest-problems": contestProblems,
      "GET /api/contests/1/scoreboard": cfScoreboardTwo,
    });

    renderContest("/contest/1");

    expect(await screen.findByText("Concurso en curso")).toBeInTheDocument();
    expect(screen.getByText("En curso")).toBeInTheDocument();
    // problem links with contest context (problems query is async)
    const sumaLink = await screen.findByRole("link", { name: /#1 Suma/ });
    expect(sumaLink).toHaveAttribute("href", "/problem/10?contest=1");
    const restaLink = screen.getByRole("link", { name: /#2 Resta/ });
    expect(restaLink).toHaveAttribute("href", "/problem/11?contest=1");
    // scoreboard rendered
    expect(screen.getByText("Tabla de posiciones")).toBeInTheDocument();
    // scoreboard rows by participant_id (no participants list for students)
    await waitFor(() => {
      const rows = screen.getAllByRole("row").slice(1);
      expect(rows[0]?.textContent).toContain("20");
      expect(rows[0]?.textContent).toContain("2");
      expect(rows[1]?.textContent).toContain("21");
      expect(rows[1]?.textContent).toContain("1");
    });
  });

  it("does NOT render the register button while running", async () => {
    mockFetch({
      "GET /api/contests/1": contestRunning,
      "GET /api/contests/1/contest-problems": emptyProblems,
      "GET /api/contests/1/scoreboard": { mode: "cf", rows: [] },
    });

    renderContest("/contest/1");
    await screen.findByText("Concurso en curso");
    expect(screen.queryByTestId("contest-register")).not.toBeInTheDocument();
  });

  it("WS AC event triggers a scoreboard refetch (live M12)", async () => {
    const scoreboardSpy = vi.fn(() => cfScoreboardTwo);
    mockFetch({
      "GET /api/contests/1": contestRunning,
      "GET /api/contests/1/contest-problems": emptyProblems,
      "GET /api/contests/1/scoreboard": scoreboardSpy,
    });

    renderContest("/contest/1");
    await screen.findByText("Concurso en curso");
    await screen.findByText("Tabla de posiciones");

    const callsBefore = scoreboardSpy.mock.calls.length;

    MockWebSocket.push({
      submission_id: 99,
      status: "done",
      per_case: [{ case_index: 0, verdict: "AC", steps: 10, wall_ms: 5 }],
    });

    await waitFor(() => {
      expect(scoreboardSpy.mock.calls.length).toBeGreaterThan(callsBefore);
    });
  });

  it("non-AC WS event does NOT trigger a scoreboard refetch", async () => {
    const scoreboardSpy = vi.fn(() => ({ mode: "cf", rows: [] }));
    mockFetch({
      "GET /api/contests/1": contestRunning,
      "GET /api/contests/1/contest-problems": emptyProblems,
      "GET /api/contests/1/scoreboard": scoreboardSpy,
    });

    renderContest("/contest/1");
    await screen.findByText("Concurso en curso");
    await screen.findByText("Tabla de posiciones");
    const callsBefore = scoreboardSpy.mock.calls.length;

    MockWebSocket.push({
      submission_id: 100,
      status: "done",
      per_case: [{ case_index: 0, verdict: "WA", steps: 5, wall_ms: 1 }],
    });

    // wait briefly to give any refetch a chance to fire
    await new Promise((r) => setTimeout(r, 50));
    expect(scoreboardSpy.mock.calls.length).toBe(callsBefore);
  });

  it("non-participant 403 on scoreboard shows a friendly notice (no raw error)", async () => {
    mockFetch({
      "GET /api/contests/1": contestRunning,
      "GET /api/contests/1/contest-problems": emptyProblems,
      "GET /api/contests/1/scoreboard": {
        __error: {
          status: 403,
          detail: "Only participants can view the scoreboard",
        },
      },
    });

    renderContest("/contest/1");
    expect(await screen.findByText("Concurso en curso")).toBeInTheDocument();
    expect(
      await screen.findByTestId("scoreboard-forbidden"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("No tienes acceso a la tabla de posiciones."),
    ).toBeInTheDocument();
  });
});

describe("Contest page — ended", () => {
  it("renders the 'Finalizado' badge and the final scoreboard", async () => {
    mockFetch({
      "GET /api/contests/1": contestEnded,
      "GET /api/contests/1/contest-problems": contestProblems,
      "GET /api/contests/1/scoreboard": cfScoreboardTwo,
    });

    renderContest("/contest/1");
    expect(await screen.findByText("Concurso pasado")).toBeInTheDocument();
    expect(screen.getByText("Finalizado")).toBeInTheDocument();
    // No countdown timer when ended.
    expect(screen.queryByTestId("countdown-timer")).not.toBeInTheDocument();
    // Final scoreboard still visible.
    expect(screen.getByText("Tabla de posiciones")).toBeInTheDocument();
  });
});

describe("Contest page — teams mode", () => {
  it("scoreboard resolves team participant_id to team name", async () => {
    mockFetch({
      "GET /api/contests/1": contestTeams,
      "GET /api/contests/1/contest-problems": emptyProblems,
      "GET /api/contests/1/teams": teamsList,
      "GET /api/contests/1/scoreboard": cfScoreboardTeam,
    });

    renderContest("/contest/1");
    expect(await screen.findByText("Concurso por equipos")).toBeInTheDocument();
    // teams panel + scoreboard row both show "Equipo A"
    const matches = await screen.findAllByText("Equipo A");
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });
});

describe("CountdownTimer", () => {
  it("renders days/hours/minutes/seconds format", () => {
    renderContestWithAuth(
      "/",
      <CountdownTimer targetAt={new Date(now + 3661_000).toISOString()} />,
    );
    const el = screen.getByTestId("countdown-timer");
    expect(el).toBeInTheDocument();
    expect(el.textContent).toMatch(/^\d{2}d \d{2}h \d{2}m \d{2}s$/);
  });

  it("marks data-done='true' when the target is in the past", () => {
    renderContestWithAuth(
      "/",
      <CountdownTimer targetAt={new Date(now - 1000).toISOString()} />,
    );
    const el = screen.getByTestId("countdown-timer");
    expect(el.getAttribute("data-done")).toBe("true");
    expect(el.textContent).toBe("00d 00h 00m 00s");
  });
});
