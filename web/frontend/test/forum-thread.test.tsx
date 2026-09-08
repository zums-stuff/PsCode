/**
 * Nested reply tree tests (forum thread detail).
 *
 * Covers: top-level post has no indent; a reply to a top-level post renders
 * with depth=1 and the accent border; a reply to a reply renders with depth=2
 * (translucent border); the "+ N more" collapse button appears when a post has
 * >3 direct children and expanding shows all; the inline ReplyBox appears at
 * every post; posts with no children do not render a wrapper div.
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

const thread = {
  id: 2,
  problem_id: 42,
  contest_id: null,
  title: "Cómo sumar",
  created_by: 3,
  pinned: false,
  created_at: "2026-09-05T12:00:00Z",
};

interface PostOverrides {
  id: number;
  thread_id?: number;
  parent_id?: number | null;
  author_id?: number;
  body?: string;
  created_at?: string;
}

function post(o: PostOverrides) {
  return {
    thread_id: 2,
    parent_id: null,
    author_id: 3,
    body: "Mensaje",
    created_at: "2026-09-05T12:00:00Z",
    ...o,
  };
}

async function openThread(posts: unknown[], user: AuthUser | null = studentUser) {
  mockFetch({
    "GET /api/problems/42": problem,
    "GET /api/problems/42/threads": [thread],
    "GET /api/threads/2/posts": posts,
  });
  renderForum("/forum/problem/42", user);
  await screen.findByTestId("forum-page");
  fireEvent.click(screen.getByTestId("thread-2"));
  // The detail page renders while posts are still loading; wait for a
  // postnode (a root is always present for every non-empty thread) so the
  // recursion tree is fully mounted before asserting.
  await waitFor(
    () => {
      const nodes = document.querySelectorAll(".post-node");
      expect(nodes.length).toBeGreaterThanOrEqual(posts.length ? 1 : 0);
    },
    { timeout: 3000 },
  );
  expect(screen.getByTestId("thread-detail")).toBeInTheDocument();
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("ThreadDetail — nested reply tree", () => {
  it("renders a top-level post without depth indent (data-depth=0)", async () => {
    await openThread([post({ id: 10, body: "Mensaje raíz" })]);
    const node = screen.getByTestId("postnode-10");
    expect(node).toHaveAttribute("data-depth", "0");
    expect(node.classList.contains("post-node")).toBe(true);
  });

  it("renders a reply to a top-level post at depth=1 with the accent border", async () => {
    await openThread([
      post({ id: 10, body: "Raíz" }),
      post({ id: 11, parent_id: 10, body: "Respuesta nivel 1" }),
    ]);
    const reply = screen.getByTestId("postnode-11");
    expect(reply).toHaveAttribute("data-depth", "1");
  });

  it("renders a reply to a reply at depth=2 (translucent border)", async () => {
    await openThread([
      post({ id: 10, body: "Raíz" }),
      post({ id: 11, parent_id: 10, body: "Nivel 1" }),
      post({ id: 12, parent_id: 11, body: "Nivel 2" }),
    ]);
    expect(screen.getByTestId("postnode-10")).toHaveAttribute("data-depth", "0");
    expect(screen.getByTestId("postnode-11")).toHaveAttribute("data-depth", "1");
    expect(screen.getByTestId("postnode-12")).toHaveAttribute("data-depth", "2");
  });

  it("shows a '+ N more' button when a post has more than 3 direct children", async () => {
    await openThread([
      post({ id: 10, body: "Raíz" }),
      post({ id: 11, parent_id: 10, body: "r1" }),
      post({ id: 12, parent_id: 10, body: "r2" }),
      post({ id: 13, parent_id: 10, body: "r3" }),
      post({ id: 14, parent_id: 10, body: "r4" }),
    ]);
    const showMore = screen.getByTestId("show-more-10");
    expect(showMore).toBeInTheDocument();
    expect(showMore.textContent).toContain("+ 1");
  });

  it("clicking '+ N more' expands to show all the replies", async () => {
    await openThread([
      post({ id: 10, body: "Raíz" }),
      post({ id: 11, parent_id: 10, body: "r1" }),
      post({ id: 12, parent_id: 10, body: "r2" }),
      post({ id: 13, parent_id: 10, body: "r3" }),
      post({ id: 14, parent_id: 10, body: "r4" }),
    ]);
    // Only the first 3 are visible initially; the 4th is not rendered.
    expect(screen.getByTestId("postnode-11")).toBeInTheDocument();
    expect(screen.getByTestId("postnode-12")).toBeInTheDocument();
    expect(screen.getByTestId("postnode-13")).toBeInTheDocument();
    expect(screen.queryByTestId("postnode-14")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("show-more-10"));

    expect(await screen.findByTestId("postnode-14")).toBeInTheDocument();
    expect(screen.queryByTestId("show-more-10")).not.toBeInTheDocument();
  });

  it("renders an inline ReplyBox at every post, not just the root", async () => {
    await openThread([
      post({ id: 10, body: "Raíz" }),
      post({ id: 11, parent_id: 10, body: "Respuesta nivel 1" }),
    ]);
    expect(screen.getByTestId("reply-to-10")).toBeInTheDocument();
    expect(screen.getByTestId("reply-to-11")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("reply-to-11"));
    expect(screen.getByTestId("reply-form-11")).toBeInTheDocument();
  });

  it("does not render a children wrapper when a post has no children", async () => {
    await openThread([post({ id: 10, body: "Solo" })]);
    expect(screen.queryByTestId("children-10")).not.toBeInTheDocument();
  });

  it("treats an orphaned parent_id (missing parent) as top-level", async () => {
    await openThread([
      post({ id: 10, body: "Raíz" }),
      // 11 references parent 999 which does not exist in the thread.
      post({ id: 11, parent_id: 999, body: "Huérfano" }),
    ]);
    // Since 999 is never a top-level post, 11 bubbles up as its own root node.
    const orphan = screen.getByTestId("postnode-11");
    expect(orphan).toHaveAttribute("data-depth", "0");
    expect(screen.getByTestId("post-11")).toBeInTheDocument();
  });
});
