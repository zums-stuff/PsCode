/**
 * Shared helpers for the Playwright E2E journeys (plan todo 42).
 *
 * Conventions:
 *   * The seeded credentials live here so every spec imports from one
 *     place — copy the source-of-truth from scripts/seed.py.
 *   * `uniqueUsername()` produces a fresh username per test run so the
 *     register flow can be exercised without colliding with seeded
 *     student01..student20.
 *   * Helpers that talk to the page keep waits explicit (locator-based
 *     waits instead of sleep) so failures point at the right element.
 */

import { expect, type Page, type APIRequestContext } from "@playwright/test";

export const SEED = {
  admin: { username: "admin", password: "admin" },
  teacher: { username: "profe", password: "profe" },
  student: { username: "student01", password: "student123" },
  classCode: "ABC123",
} as const;

const APP_URL = process.env.E2E_BASE_URL ?? "http://localhost:5173";
const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000";

export function appUrl(path = "/"): string {
  return `${APP_URL}${path}`;
}

export function apiUrl(path: string): string {
  return `${API_URL}${path}`;
}

/** Returns a unique username suffixed with the test worker pid + epoch ms. */
export function uniqueUsername(prefix = "e2e"): string {
  return `${prefix}_${process.pid}_${Date.now().toString(36)}`;
}

/** Returns a unique display name for the register flow. */
export function uniqueDisplayName(): string {
  return `E2E ${new Date().toISOString().slice(11, 19)}`;
}

/**
 * Logs in via the /login page (drives the real auth UI — no API shortcut).
 * Resolves once the page transitions away from /login.
 */
export async function loginViaUi(page: Page, username: string, password: string): Promise<void> {
  await page.goto(appUrl("/login"));
  await page.locator("#login-username").fill(username);
  await page.locator("#login-password").fill(password);
  await Promise.all([
    page.waitForURL((url) => !url.pathname.startsWith("/login"), {
      timeout: 15_000,
    }),
    page.locator('button[type="submit"]').click(),
  ]);
}

/** Logs in as a freshly-registered student; waits for the problems list. */
export async function registerStudent(
  page: Page,
  opts: { username: string; displayName: string; password: string; classCode?: string },
): Promise<void> {
  await page.goto(appUrl("/register"));
  await page.locator("#register-username").fill(opts.username);
  await page.locator("#register-display").fill(opts.displayName);
  await page.locator("#register-password").fill(opts.password);
  if (opts.classCode !== undefined) {
    await page.locator("#register-class").fill(opts.classCode);
  }
  await Promise.all([
    page.waitForURL((url) => url.pathname === "/", { timeout: 15_000 }),
    page.locator('button[type="submit"]').click(),
  ]);
  await expect(page.locator("h1")).toContainText(/Problemas/);
}

/**
 * Logs out via the API (best-effort) by clearing localStorage and
 * reloading.  The /logout UI is intentionally minimal — the SPA simply
 * reads pseint:token from storage; clearing it forces a redirect on
 * the next RequireAuth tick.
 */
export async function logoutViaStorage(page: Page): Promise<void> {
  await page.evaluate(() => {
    window.localStorage.removeItem("pseint:token");
    window.localStorage.removeItem("pseint:user");
  });
}

/**
 * Drives the CodeMirror editor (the only PseInt input surface) by
 * clicking into it and typing.  CodeMirror 6 doesn't react to a
 * programmatic `fill()` on the contenteditable; typing is the
 * deterministic path.
 */
export async function typeIntoEditor(page: Page, text: string): Promise<void> {
  const cm = page.locator(".solve-editor-cm .cm-content");
  await cm.waitFor({ state: "visible", timeout: 10_000 });
  await cm.click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.press("Delete");
  await page.keyboard.type(text, { delay: 4 });
}

export interface ApiCreds {
  username: string;
  password: string;
}

/**
 * Logs in via the API to grab a JWT (used by the assignment-best
 * server-side guard test; never used by the primary UI-driven test
 * body — every main assertion drives the page).
 */
export async function loginViaApi(
  request: APIRequestContext,
  creds: ApiCreds,
): Promise<string> {
  const res = await request.post(apiUrl("/api/login"), {
    data: { username: creds.username, password: creds.password },
  });
  if (!res.ok()) {
    throw new Error(`login failed for ${creds.username}: ${res.status()} ${await res.text()}`);
  }
  const body = (await res.json()) as { access_token: string };
  return body.access_token;
}

/** Returns the API origin (used for direct API calls from test setup). */
export function getApiUrl(): string {
  return API_URL;
}
