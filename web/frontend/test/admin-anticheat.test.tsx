/**
 * Admin anticheat report tests (plan todo 25 acceptance).
 *
 * Covers:
 *  - scope selector renders + submits (calls onApply)
 *  - threshold form rejects out-of-range input and POSTs the valid value
 *  - pair list renders rows from the mock with the score column descending
 *  - same-team exclusion indicator renders; the row stays absent (server-
 *    side exclusion)
 *  - diff viewer renders the ORIGINAL sources (no normalization internals)
 *  - CSV export triggers a download with the right content
 *  - student role on /admin/anticheat → /403 redirect
 *
 * fetch is mocked globally (vi.spyOn) — no network, no MSW.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, RequireRole, type AuthUser } from "../src/lib/auth";
import AdminAnticheat from "../src/routes/admin/AdminAnticheat";
import AnticheatScopeSelector from "../src/components/AnticheatScopeSelector";
import AnticheatThresholdForm from "../src/components/AnticheatThresholdForm";
import AnticheatPairList from "../src/components/AnticheatPairList";
import AnticheatDiffViewer from "../src/components/AnticheatDiffViewer";
import { toCSV, downloadCSV } from "../src/lib/csv";

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

const pairHigh = {
  run_a_id: 101,
  run_b_id: 102,
  user_a_id: 11,
  user_a_username: "alice",
  user_b_id: 12,
  user_b_username: "bob",
  score: 0.92,
  scope: "class" as const,
  flagged: true,
};

const pairMid = {
  run_a_id: 103,
  run_b_id: 104,
  user_a_id: 13,
  user_a_username: "carol",
  user_b_id: 14,
  user_b_username: "dave",
  score: 0.88,
  scope: "class" as const,
  flagged: true,
};

const pairLow = {
  run_a_id: 105,
  run_b_id: 106,
  user_a_id: 15,
  user_a_username: "eve",
  user_b_id: 16,
  user_b_username: "frank",
  score: 0.6,
  scope: "class" as const,
  flagged: false,
};

const pairDetail = {
  run_a: {
    id: 101,
    user_id: 11,
    username: "alice",
    problem_id: 1,
    kind: "assignment",
  },
  run_b: {
    id: 102,
    user_id: 12,
    username: "bob",
    problem_id: 1,
    kind: "assignment",
  },
  source_a: "Proceso P\n  Escribir 1\nFinProceso\n",
  source_b: "Proceso P\n  Escribir 2\nFinProceso\n",
  score: 0.92,
  flagged: true,
  threshold: 0.85,
};

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("admin anticheat - scope selector", () => {
  it("renders and submits the selected scope + scope id", () => {
    const onApply = vi.fn();
    render(
      <MemoryRouter>
        <AnticheatScopeSelector value={null} onApply={onApply} />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText("ID del alcance"), {
      target: { value: "42" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Aplicar" }));

    expect(onApply).toHaveBeenCalledWith({ scope: "class", scopeId: 42 });
  });

  it("rejects a non-numeric scope id", async () => {
    const onApply = vi.fn();
    render(
      <MemoryRouter>
        <AnticheatScopeSelector value={null} onApply={onApply} />
      </MemoryRouter>,
    );

    const input = screen.getByLabelText("ID del alcance");
    fireEvent.change(input, { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Aplicar" }));

    expect(
      await screen.findByText(
        "Ingresa un ID de alcance válido (número entero positivo).",
      ),
    ).toBeInTheDocument();
    expect(onApply).not.toHaveBeenCalled();
  });
});

describe("admin anticheat - threshold form", () => {
  it("rejects out-of-range values", async () => {
    const onSubmit = vi.fn();
    render(
      <MemoryRouter>
        <AnticheatThresholdForm
          classId={1}
          initialThreshold={0.85}
          defaultThreshold={0.85}
          onSubmit={onSubmit}
        />
      </MemoryRouter>,
    );

    const input = screen.getByLabelText("Umbral de anticheat");
    fireEvent.change(input, { target: { value: "1.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar umbral" }));

    expect(
      await screen.findByText("El umbral debe estar entre 0 y 1."),
    ).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("accepts a valid value and invokes onSubmit", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <MemoryRouter>
        <AnticheatThresholdForm
          classId={1}
          initialThreshold={0.85}
          defaultThreshold={0.85}
          onSubmit={onSubmit}
        />
      </MemoryRouter>,
    );

    const input = screen.getByLabelText("Umbral de anticheat");
    fireEvent.change(input, { target: { value: "0.92" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar umbral" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith(0.92));
  });
});

describe("admin anticheat - pair list", () => {
  it("renders rows from the mock in score-descending order", () => {
    render(
      <MemoryRouter>
        <AnticheatPairList
          pairs={[pairMid, pairHigh, pairLow]}
          threshold={0.85}
          sameTeamExclusion={false}
          loading={false}
          error={null}
          onSelectPair={() => {}}
          selectedPairKey={null}
        />
      </MemoryRouter>,
    );

    const scores = screen.getAllByText(/^\d+\.\d+$/);
    expect(scores.map((el) => el.textContent)).toEqual([
      "0.9200",
      "0.8800",
      "0.6000",
    ]);

    expect(screen.getByText(/alice/)).toBeInTheDocument();
    expect(screen.getByText(/bob/)).toBeInTheDocument();
    expect(screen.getByText(/carol/)).toBeInTheDocument();
    expect(screen.getByText(/dave/)).toBeInTheDocument();
    expect(screen.getByText(/eve/)).toBeInTheDocument();
    expect(screen.getByText(/frank/)).toBeInTheDocument();
  });

  it("renders the same-team-exclusion hint when scope=contest", () => {
    render(
      <MemoryRouter>
        <AnticheatPairList
          pairs={[pairHigh]}
          threshold={0.85}
          sameTeamExclusion
          loading={false}
          error={null}
          onSelectPair={() => {}}
          selectedPairKey={null}
        />
      </MemoryRouter>,
    );

    expect(
      screen.getByText(
        "Las entregas del mismo equipo se excluyen automáticamente.",
      ),
    ).toBeInTheDocument();
  });

  it("omits the same-team row (server already excluded it)", () => {
    // Mock returns only the cross-team pair; the same-team pair is gone.
    render(
      <MemoryRouter>
        <AnticheatPairList
          pairs={[pairHigh]}
          threshold={0.85}
          sameTeamExclusion
          loading={false}
          error={null}
          onSelectPair={() => {}}
          selectedPairKey={null}
        />
      </MemoryRouter>,
    );

    expect(screen.queryByText(/teammate/)).not.toBeInTheDocument();
    expect(screen.getByText(/alice/)).toBeInTheDocument();
  });
});

describe("admin anticheat - diff viewer", () => {
  it("renders the original sources verbatim (no normalization leak)", async () => {
    mockFetch({
      "GET /api/admin/anticheat/pair/101/102": pairDetail,
    });

    const pair = {
      ...pairHigh,
    };
    render(
      <QueryClientProvider
        client={new QueryClient({
          defaultOptions: { queries: { retry: false } },
        })}
      >
        <MemoryRouter>
          <AnticheatDiffViewer pair={pair} onClose={() => {}} />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("anticheat-diff-viewer")).toBeInTheDocument(),
    );

    // Source A and Source B both contain their distinct token ("1" vs "2")
    // and the shared boilerplate.
    const viewer = screen.getByTestId("anticheat-diff-viewer");
    expect(viewer.textContent).toContain("Proceso P");
    expect(viewer.textContent).toContain("FinProceso");
    expect(viewer.textContent).toContain("alice");
    expect(viewer.textContent).toContain("bob");
    // No D13 normalization fields leak (camelCase or snake_case variants).
    expect(viewer.textContent).not.toMatch(/normalized/);
    expect(viewer.textContent).not.toMatch(/tokens/);
  });

  it("invokes the pair detail endpoint with the canonical ordered ids", async () => {
    const fetchMock = mockFetch({
      "GET /api/admin/anticheat/pair/101/102": pairDetail,
    });

    render(
      <QueryClientProvider
        client={new QueryClient({
          defaultOptions: { queries: { retry: false } },
        })}
      >
        <MemoryRouter>
          <AnticheatDiffViewer
            pair={{ ...pairHigh, run_a_id: 102, run_b_id: 101 }}
            onClose={() => {}}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("anticheat-diff-viewer")).toBeInTheDocument(),
    );

    const pairCalls = fetchMock.mock.calls.filter(([input]) =>
      String(input).includes("/api/admin/anticheat/pair/"),
    );
    expect(pairCalls).toHaveLength(1);
    const url = String(pairCalls[0]?.[0]);
    expect(url).toContain("/api/admin/anticheat/pair/101/102");
  });
});

describe("admin anticheat - CSV export", () => {
  it("exports pairs with the correct shape", () => {
    const csv = toCSV([
      [
        "run_a_id",
        "user_a",
        "run_b_id",
        "user_b",
        "score",
        "flagged",
      ],
      [
        pairHigh.run_a_id,
        pairHigh.user_a_username,
        pairHigh.run_b_id,
        pairHigh.user_b_username,
        pairHigh.score.toFixed(4),
        "true",
      ],
    ]);

    expect(csv).toBe(
      'run_a_id,user_a,run_b_id,user_b,score,flagged\r\n101,alice,102,bob,0.9200,true',
    );
  });

  it("quotes cells containing commas, quotes, or newlines", () => {
    expect(toCSV([["plain"]])).toBe("plain");
    expect(toCSV([["a,b"]])).toBe('"a,b"');
    expect(toCSV([['a"b']])).toBe('"a""b"');
    expect(toCSV([["line1\nline2"]])).toBe('"line1\nline2"');
  });

  it("downloadCSV triggers a click on a hidden anchor", () => {
    const clickSpy = vi.fn();
    const originalCreate = document.createElement.bind(document);
    const createSpy = vi
      .spyOn(document, "createElement")
      .mockImplementation(((tag: string) => {
        const el = originalCreate(tag);
        if (tag === "a") el.click = clickSpy;
        return el;
      }) as typeof document.createElement);

    // jsdom 26: stub createObjectURL/revokeObjectURL.
    const origCreate = URL.createObjectURL;
    const origRevoke = URL.revokeObjectURL;
    URL.createObjectURL = () => "blob:stub";
    URL.revokeObjectURL = () => {};

    try {
      downloadCSV("anticheat.csv", "header\nrow1\n");
    } finally {
      URL.createObjectURL = origCreate;
      URL.revokeObjectURL = origRevoke;
      createSpy.mockRestore();
    }

    expect(clickSpy).toHaveBeenCalled();
  });
});

describe("admin anticheat - guard", () => {
  it("redirects a student to /403 when accessing /admin/anticheat", async () => {
    mockFetch({});

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/anticheat"]}>
        <Routes>
          <Route path="/403" element={<div>acceso denegado</div>} />
          <Route
            path="/admin/anticheat"
            element={
              <RequireRole roles={["teacher", "admin"]}>
                <AdminAnticheat />
              </RequireRole>
            }
          />
        </Routes>
      </MemoryRouter>,
      studentUser,
    );

    expect(await screen.findByText("acceso denegado")).toBeInTheDocument();
  });
});

describe("admin anticheat - full page", () => {
  it("renders the page header for a teacher and dispatches the pairs query", async () => {
    const fetchMock = mockFetch({
      "GET /api/admin/anticheat?scope=class&scope_id=42&threshold=0.85": [
        pairHigh,
        pairMid,
      ],
    });

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/anticheat"]}>
        <Routes>
          <Route path="/admin/anticheat" element={<AdminAnticheat />} />
        </Routes>
      </MemoryRouter>,
      teacherUser,
    );

    expect(
      await screen.findByText("Reporte de anticheat"),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("ID del alcance"), {
      target: { value: "42" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Aplicar" }));

    await waitFor(() => {
      const pairCall = fetchMock.mock.calls.find(([input]) =>
        String(input).includes("/api/admin/anticheat?"),
      );
      expect(pairCall).toBeDefined();
    });

    expect(await screen.findByText("Pares sospechosos")).toBeInTheDocument();
    expect(screen.getByText(/alice/)).toBeInTheDocument();
    expect(screen.getByText(/bob/)).toBeInTheDocument();
    expect(screen.getByText(/carol/)).toBeInTheDocument();
  });

  it("renders the page for an admin user", async () => {
    mockFetch({
      "GET /api/admin/anticheat?scope=class&scope_id=1&threshold=0.85": [],
    });

    renderWithProviders(
      <MemoryRouter initialEntries={["/admin/anticheat"]}>
        <Routes>
          <Route path="/admin/anticheat" element={<AdminAnticheat />} />
        </Routes>
      </MemoryRouter>,
      adminUser,
    );

    expect(
      await screen.findByText("Reporte de anticheat"),
    ).toBeInTheDocument();
  });
});
