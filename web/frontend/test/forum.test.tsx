/**
 * Forum page tests (plan todo 33 acceptance).
 *
 * Covers: non-contest thread flows freely; new thread form posts to the API;
 * opening a thread loads posts + reply box; nested reply with parent_id;
 * pagination of thread list; contest-phase lock (student reply returns 403
 * → inline error + toast); teacher pins a thread (PATCH); teacher edits a
 * post (PATCH); teacher deletes a post (DELETE).
 *
 * fetch is mocked globally (vi.spyOn); no network, no MSW. AuthProvider is
 * driven from localStorage so the moderator-only branches exercise the real
 * gating.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Forum from "../src/routes/Forum";
import { AuthProvider, type AuthUser } from "../src/lib/auth";

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

function renderForum(initialEntry: string, user: AuthUser | null = null) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  if (user !== null) {
    localStorage.setItem("pseint:token", "test-token");
    localStorage.setItem("pseint:user", JSON.stringify(user));
  }
  const ui: ReactElement = (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <Routes>
            <Route path="/forum/problem/:id" element={<Forum />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
  return render(ui);
}

const studentUser: AuthUser = {
  id: 3,
  username: "alumno",
  display_name: "Alumno Uno",
  role: "student",
};

const teacherUser: AuthUser = {
  id: 1,
  username: "profe",
  display_name: "Profesora",
  role: "teacher",
};

const problem = {
  id: 42,
  title: "Suma de dos números",
  statement: "# Suma",
  expected_complexity: "O(1)",
  step_budget: null,
  compare_mode: "exact",
  author_id: 1,
  created_at: "2026-09-06T00:00:00Z",
};

const threadPinned = {
  id: 1,
  problem_id: 42,
  contest_id: null,
  title: "Cómo sumar",
  created_by: 3,
  pinned: true,
  created_at: "2026-09-06T00:00:00Z",
};

const threadNormal = {
  id: 2,
  problem_id: 42,
  contest_id: null,
  title: "Otra pregunta",
  created_by: 4,
  pinned: false,
  created_at: "2026-09-05T12:00:00Z",
};

const manyThreads = Array.from({ length: 12 }, (_, i) => ({
  id: i + 1,
  problem_id: 42,
  contest_id: null,
  title: `Hilo ${i + 1}`,
  created_by: 3,
  pinned: false,
  created_at: `2026-09-${String(i + 1).padStart(2, "0")}T00:00:00Z`,
}));

const post = (overrides: Partial<typeof basePost> & { id: number }) => ({
  ...basePost,
  ...overrides,
});

const basePost = {
  thread_id: 2,
  parent_id: null as number | null,
  author_id: 3,
  body: "Mensaje inicial",
  created_at: "2026-09-05T12:00:00Z",
};

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("Forum page — thread list", () => {
  it("renders the problem title + thread list", async () => {
    mockFetch({
      "GET /api/problems/42": problem,
      "GET /api/problems/42/threads": [threadPinned, threadNormal],
      "GET /api/threads/2/posts": [],
    });

    renderForum("/forum/problem/42", studentUser);

    expect(
      await screen.findByText(/Foro del problema.*Suma de dos números/),
    ).toBeInTheDocument();
    // pinned threads render first
    const pinnedBtn = screen.getByTestId("thread-1");
    expect(pinnedBtn).toBeInTheDocument();
    expect(pinnedBtn.textContent).toContain("Fijado");
    expect(screen.getByTestId("thread-2")).toBeInTheDocument();
  });

  it("paginates the thread list with Next/Prev buttons", async () => {
    mockFetch({
      "GET /api/problems/42": problem,
      "GET /api/problems/42/threads": manyThreads,
    });

    renderForum("/forum/problem/42", studentUser);

    // first page shows the newest 10 (sorted by created_at desc): 12..3
    await screen.findByTestId("thread-12");
    expect(screen.getByTestId("thread-3")).toBeInTheDocument();
    expect(screen.queryByTestId("thread-2")).not.toBeInTheDocument();
    expect(screen.queryByTestId("thread-1")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("thread-next"));
    expect(await screen.findByTestId("thread-2")).toBeInTheDocument();
    expect(screen.getByTestId("thread-1")).toBeInTheDocument();
    expect(screen.queryByTestId("thread-3")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("thread-prev"));
    await waitFor(() => {
      expect(screen.getByTestId("thread-12")).toBeInTheDocument();
    });
  });
});

describe("Forum page — new thread", () => {
  it("posts a new thread via the form and opens it", async () => {
    const createSpy = vi.fn(() => ({
      id: 99,
      problem_id: 42,
      contest_id: null,
      title: "Nuevo hilo",
      created_by: 3,
      pinned: false,
      created_at: "2026-09-06T12:00:00Z",
    }));
    mockFetch({
      "GET /api/problems/42": problem,
      "GET /api/problems/42/threads": [],
      "POST /api/problems/42/threads": createSpy,
      "GET /api/threads/99/posts": [],
    });

    renderForum("/forum/problem/42", studentUser);
    await screen.findByTestId("forum-page");

    fireEvent.click(screen.getByTestId("new-thread-toggle"));
    const titleInput = screen.getByLabelText("Título del hilo");
    const bodyInput = screen.getByLabelText("Contenido");
    fireEvent.change(titleInput, { target: { value: "Nuevo hilo" } });
    fireEvent.change(bodyInput, { target: { value: "Contenido del hilo" } });
    fireEvent.click(screen.getByTestId("new-thread-submit"));

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalled();
    });
    const [, init] = createSpy.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init!.body))).toEqual({
      title: "Nuevo hilo",
      body: "Contenido del hilo",
    });

    // opens the detail page for the new thread
    expect(await screen.findByTestId("thread-detail")).toBeInTheDocument();
  });
});

describe("Forum page — reply flow (non-contest)", () => {
  it("opens the thread detail with reply box and posts top-level + nested replies", async () => {
    const replySpy = vi.fn((path: string, init?: RequestInit) => {
      const body = JSON.parse(String(init!.body)) as {
        body: string;
        parent_id?: number | null;
      };
      return {
        id: 100 + replySpy.mock.calls.length,
        thread_id: 2,
        parent_id: body.parent_id ?? null,
        author_id: 3,
        body: body.body,
        created_at: "2026-09-06T13:00:00Z",
      };
    });
    const initialPosts = [post({ id: 10 })];
    mockFetch({
      "GET /api/problems/42": problem,
      "GET /api/problems/42/threads": [threadNormal],
      "GET /api/threads/2/posts": initialPosts,
      "POST /api/threads/2/posts": replySpy,
    });

    renderForum("/forum/problem/42", studentUser);
    await screen.findByTestId("forum-page");
    fireEvent.click(screen.getByTestId("thread-2"));
    expect(
      await screen.findByTestId("thread-detail", {}, { timeout: 3000 }),
    ).toBeInTheDocument();
    // initial post rendered
    expect(screen.getByTestId("post-10")).toBeInTheDocument();
    expect(screen.getByText("Mensaje inicial")).toBeInTheDocument();

    // top-level reply
    fireEvent.change(screen.getByLabelText("Responder"), {
      target: { value: "Mi respuesta" },
    });
    fireEvent.click(screen.getByTestId("top-reply-submit"));
    await waitFor(() => {
      expect(replySpy).toHaveBeenCalled();
    });
    expect(JSON.parse(String(replySpy.mock.calls[0]![1]!.body))).toEqual({
      body: "Mi respuesta",
      parent_id: null,
    });

    // nested reply via reply button
    fireEvent.click(screen.getByTestId("reply-to-10"));
    fireEvent.change(screen.getByLabelText("Respondiendo a #10"), {
      target: { value: "Respuesta anidada" },
    });
    fireEvent.click(screen.getByTestId("reply-submit-10"));
    await waitFor(() => {
      expect(replySpy.mock.calls.length).toBeGreaterThanOrEqual(2);
    });
    expect(JSON.parse(String(replySpy.mock.calls[1]![1]!.body))).toEqual({
      body: "Respuesta anidada",
      parent_id: 10,
    });
  });
});

describe("Forum page — contest-phase lock", () => {
  it("shows an inline error + toast when a student reply hits a live contest window", async () => {
    mockFetch({
      "GET /api/problems/42": problem,
      "GET /api/problems/42/threads": [threadNormal],
      "GET /api/threads/2/posts": [post({ id: 10 })],
      "POST /api/threads/2/posts": {
        __error: {
          status: 403,
          detail: "Contest in progress: only teachers can post",
        },
      },
    });

    renderForum("/forum/problem/42", studentUser);
    await screen.findByTestId("forum-page");
    fireEvent.click(screen.getByTestId("thread-2"));
    await screen.findByTestId("thread-detail");

    fireEvent.change(screen.getByLabelText("Responder"), {
      target: { value: "Intento bloqueado" },
    });
    fireEvent.click(screen.getByTestId("top-reply-submit"));

    expect(
      await screen.findByTestId("reply-error"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("reply-error").textContent).toContain(
      "Concurso en curso",
    );
    expect(await screen.findByTestId("forum-toast")).toBeInTheDocument();
    expect(screen.getByTestId("forum-toast").textContent).toContain(
      "Concurso en curso",
    );
  });
});

describe("Forum page — teacher moderation", () => {
  it("teacher can pin a thread (PATCH)", async () => {
    const pinSpy = vi.fn(() => ({ ...threadNormal, pinned: true }));
    mockFetch({
      "GET /api/problems/42": problem,
      "GET /api/problems/42/threads": [threadNormal],
      "GET /api/threads/2/posts": [post({ id: 10 })],
      "PATCH /api/threads/2": pinSpy,
    });

    renderForum("/forum/problem/42", teacherUser);
    await screen.findByTestId("forum-page");
    fireEvent.click(screen.getByTestId("thread-2"));
    await screen.findByTestId("thread-detail");

    fireEvent.click(screen.getByTestId("thread-pin"));

    await waitFor(() => {
      expect(pinSpy).toHaveBeenCalled();
    });
    const [, init] = pinSpy.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init!.body))).toEqual({ pinned: true });
  });

  it("teacher can edit a post body (PATCH) and the in-place editor roundtrips", async () => {
    const editSpy = vi.fn((path: string, init?: RequestInit) => ({
      id: 10,
      thread_id: 2,
      parent_id: null,
      author_id: 3,
      body: JSON.parse(String(init!.body)).body as string,
      created_at: "2026-09-05T12:00:00Z",
    }));
    mockFetch({
      "GET /api/problems/42": problem,
      "GET /api/problems/42/threads": [threadNormal],
      "GET /api/threads/2/posts": [post({ id: 10 })],
      "PATCH /api/posts/10": editSpy,
    });

    renderForum("/forum/problem/42", teacherUser);
    await screen.findByTestId("forum-page");
    fireEvent.click(screen.getByTestId("thread-2"));
    await screen.findByTestId("thread-detail");

    fireEvent.click(screen.getByTestId("edit-button-10"));
    const editArea = screen.getByTestId("edit-body-10");
    fireEvent.change(editArea, { target: { value: "Texto editado" } });
    fireEvent.click(screen.getByTestId("edit-save-10"));

    await waitFor(() => {
      expect(editSpy).toHaveBeenCalled();
    });
    expect(JSON.parse(String(editSpy.mock.calls[0]![1]!.body))).toEqual({
      body: "Texto editado",
    });
  });

  it("teacher can delete a post (DELETE) after confirm", async () => {
    const deleteSpy = vi.fn(() => undefined);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    mockFetch({
      "GET /api/problems/42": problem,
      "GET /api/problems/42/threads": [threadNormal],
      "GET /api/threads/2/posts": [post({ id: 10 })],
      "DELETE /api/posts/10": deleteSpy,
    });

    renderForum("/forum/problem/42", teacherUser);
    await screen.findByTestId("forum-page");
    fireEvent.click(screen.getByTestId("thread-2"));
    await screen.findByTestId("thread-detail");

    fireEvent.click(screen.getByTestId("delete-button-10"));

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalled();
    });
    expect(confirmSpy).toHaveBeenCalled();
  });
});
