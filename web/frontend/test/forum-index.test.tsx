/**
 * Forums index (landing page) tests — /forum.
 *
 * Covers: rendering all threads from the mock fetch; each row showing
 * title/problem/author/reply count; empty state; "New thread" opens a modal
 * with a problem selector; submitting POSTs to /api/problems/{id}/threads and
 * refetches; loading + error states; row click navigates to /forum/problem/{id};
 * reply-count badge colour (0 grey, 1+ blue).
 *
 * fetch is mocked globally (vi.spyOn); no network, no MSW. ForumIndex does
 * not read useAuth, so a plain MemoryRouter + QueryClient wrapper suffices.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ForumIndex from "../src/routes/ForumIndex";
import type { ThreadIndexItem } from "../src/lib/types";

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
    const path = url.replace(/^https?:\/\/[^/]+/, "").split("?")[0];
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

function renderIndex(initialEntry = "/forum") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const ui: ReactElement = (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/forum" element={<ForumIndex />} />
          <Route path="/forum/problem/:id" element={<div data-testid="problem-forum-detail">problem forum</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
  return render(ui);
}

const thread = (overrides: Partial<ThreadIndexItem> & { id: number }): ThreadIndexItem => ({
  problem_id: 42,
  problem_title: "Suma de dos números",
  contest_id: null,
  title: "Cómo sumar",
  author_id: 3,
  author_username: "alumno",
  pinned: false,
  created_at: "2026-09-06T00:00:00Z",
  reply_count: 2,
  last_activity_at: "2026-09-07T00:00:00Z",
  ...overrides,
});

const problem = {
  id: 42,
  title: "Suma de dos números",
  expected_complexity: "O(1)",
  compare_mode: "exact",
  is_solved: false,
  best_verdict: null,
};

const page = (items: ThreadIndexItem[], total = items.length) => ({
  items,
  page: 1,
  size: 20,
  total,
});

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("ForumIndex — rendering", () => {
  it("renders all threads from the mock fetch", async () => {
    mockFetch({
      "GET /api/threads": page([thread({ id: 1 }), thread({ id: 2, title: "Otro", problem_title: "Ciclos" })]),
    });
    renderIndex();
    expect(await screen.findByTestId("forum-index-list")).toBeInTheDocument();
    expect(screen.getByTestId("forum-index-thread-1")).toBeInTheDocument();
    expect(screen.getByTestId("forum-index-thread-2")).toBeInTheDocument();
  });

  it("each thread row shows title, problem, author and reply count", async () => {
    mockFetch({
      "GET /api/threads": page([thread({ id: 1 })]),
    });
    renderIndex();
    await screen.findByTestId("forum-index-thread-1");
    const row = screen.getByTestId("forum-index-row-1");
    expect(row.textContent).toContain("Cómo sumar");
    expect(row.textContent).toContain("Suma de dos números");
    expect(row.textContent).toContain("alumno");
    expect(screen.getByTestId("forum-index-replies-1").textContent).toContain("2 respuestas");
  });

  it("reply count badge is grey when zero and blue when 1+", async () => {
    mockFetch({
      "GET /api/threads": page([
        thread({ id: 1, reply_count: 0 }),
        thread({ id: 2, reply_count: 3 }),
      ]),
    });
    renderIndex();
    await screen.findByTestId("forum-index-thread-1");
    expect(screen.getByTestId("forum-index-replies-1").className).not.toContain("has-replies");
    expect(screen.getByTestId("forum-index-replies-1").textContent).toContain("Sin respuestas");
    expect(screen.getByTestId("forum-index-replies-2").className).toContain("has-replies");
  });

  it("shows the empty state when there are no threads", async () => {
    mockFetch({ "GET /api/threads": page([]) });
    renderIndex();
    expect(await screen.findByTestId("forum-index-empty")).toBeInTheDocument();
    expect(screen.getByTestId("forum-index-empty").textContent).toContain(
      "Aún no hay hilos",
    );
  });

  it("shows the loading state while fetching", async () => {
    let resolveFn: (v: unknown) => void = () => {};
    mockFetch({
      "GET /api/threads": new Promise((resolve) => {
        resolveFn = resolve;
      }),
    });
    renderIndex();
    expect(screen.getByText("Cargando hilos…")).toBeInTheDocument();
    resolveFn(page([thread({ id: 1 })]));
    await screen.findByTestId("forum-index-list");
  });

  it("shows the error state when the fetch fails", async () => {
    mockFetch({
      "GET /api/threads": { __error: { status: 500, detail: "boom" } },
    });
    renderIndex();
    expect(await screen.findByText("No se pudieron cargar los hilos.")).toBeInTheDocument();
  });
});

describe("ForumIndex — new thread", () => {
  it("opens the modal with a problem selector on 'New thread'", async () => {
    mockFetch({
      "GET /api/threads": page([]),
      "GET /api/problems": { items: [problem], page: 1, size: 100, total: 1 },
    });
    renderIndex();
    await screen.findByTestId("forum-index");
    fireEvent.click(screen.getByTestId("forum-index-new"));
    await screen.findByTestId("forum-index-modal");
    const select = screen.getByTestId("forum-index-problem-select");
    expect(select).toBeInTheDocument();
    expect(await screen.findByText("#42 — Suma de dos números")).toBeInTheDocument();
  });

  it("validates empty title/body client-side before submitting", async () => {
    mockFetch({
      "GET /api/threads": page([]),
      "GET /api/problems": { items: [problem], page: 1, size: 100, total: 1 },
    });
    renderIndex();
    await screen.findByTestId("forum-index");
    fireEvent.click(screen.getByTestId("forum-index-new"));
    await screen.findByTestId("forum-index-modal");
    fireEvent.click(screen.getByTestId("forum-index-modal-submit"));
    expect(screen.getByTestId("forum-index-modal-error").textContent).toContain("obligatorio");
  });

  it("POSTs to /api/problems/{id}/threads and refetches the list", async () => {
    let listCalls = 0;
    const createSpy = vi.fn((_path: string, init?: RequestInit) => ({
      id: 99,
      problem_id: 42,
      contest_id: null,
      title: JSON.parse(String(init!.body)).title,
      created_by: 3,
      pinned: false,
      created_at: "2026-09-07T00:00:00Z",
    }));
    mockFetch({
      "GET /api/problems": { items: [problem], page: 1, size: 100, total: 1 },
      "POST /api/problems/42/threads": createSpy,
      "GET /api/threads": (_path: string) => {
        listCalls += 1;
        return page(
          listCalls === 1
            ? []
            : [thread({ id: 1 })],
        );
      },
    });
    renderIndex();
    await screen.findByTestId("forum-index-empty");
    fireEvent.click(screen.getByTestId("forum-index-new"));
    await screen.findByTestId("forum-index-modal");
    await screen.findByText("#42 — Suma de dos números");

    fireEvent.change(screen.getByTestId("forum-index-problem-select"), {
      target: { value: "42" },
    });
    fireEvent.change(screen.getByTestId("forum-index-title"), {
      target: { value: "Mi duda" },
    });
    fireEvent.change(screen.getByTestId("forum-index-body"), {
      target: { value: "Contenido" },
    });
    fireEvent.click(screen.getByTestId("forum-index-modal-submit"));

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalled();
    });
    const [, init] = createSpy.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init!.body))).toEqual({ title: "Mi duda", body: "Contenido" });

    // Modal closes and the list refetches (second GET), showing the new thread.
    await waitFor(() => {
      expect(listCalls).toBeGreaterThanOrEqual(2);
    });
    expect(screen.queryByTestId("forum-index-modal")).not.toBeInTheDocument();
    expect(await screen.findByTestId("forum-index-thread-1")).toBeInTheDocument();
  });

  it("surfaces the contest-phase 403 as an inline error", async () => {
    mockFetch({
      "GET /api/threads": page([]),
      "GET /api/problems": { items: [problem], page: 1, size: 100, total: 1 },
      "POST /api/problems/42/threads": {
        __error: { status: 403, detail: "Contest in progress: only teachers can post" },
      },
    });
    renderIndex();
    await screen.findByTestId("forum-index");
    fireEvent.click(screen.getByTestId("forum-index-new"));
    await screen.findByTestId("forum-index-modal");
    await screen.findByText("#42 — Suma de dos números");
    fireEvent.change(screen.getByTestId("forum-index-problem-select"), {
      target: { value: "42" },
    });
    fireEvent.change(screen.getByTestId("forum-index-title"), { target: { value: "T" } });
    fireEvent.change(screen.getByTestId("forum-index-body"), { target: { value: "B" } });
    fireEvent.click(screen.getByTestId("forum-index-modal-submit"));
    expect(await screen.findByTestId("forum-index-modal-error")).toHaveTextContent(
      "Concurso en curso",
    );
  });
});

describe("ForumIndex — navigation", () => {
  it("clicking a thread row navigates to /forum/problem/{id}", async () => {
    mockFetch({
      "GET /api/threads": page([thread({ id: 1, problem_id: 42 })]),
    });
    renderIndex();
    const link = await screen.findByTestId("forum-index-thread-1");
    expect(link.getAttribute("href")).toBe("/forum/problem/42");
    fireEvent.click(link);
    expect(await screen.findByTestId("problem-forum-detail")).toBeInTheDocument();
  });
});
