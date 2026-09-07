import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for the pseint-judge E2E journeys (plan todo 42).
 *
 * Runs against the LOCAL compose stack — DOMAIN unset, http://localhost
 * (Caddy at :80 serving the SPA, the api container reachable on the
 * compose internal network).  Tests are REAL end-to-end: no API
 * mocking, no stubbed WebSocket — every request goes through the live
 * stack and the seeded data (scripts/seed.py) drives the deterministic
 * fixtures the assertions pin.
 *
 * Prerequisites:
 *   1. `docker compose up -d` (infra/docker-compose.yml) with DOMAIN
 *      unset so Caddy serves plain HTTP at http://localhost.
 *   2. `python scripts/seed.py` to load the demo accounts, the 4
 *      problems, the seeded contest, and the planted anticheat pair.
 *   3. `npx playwright install --with-deps chromium` (one-time;
 *      downloads the browser binaries).
 *
 * The webServer block below assumes the compose stack is already up
 * (per the task brief: "or assume already up").  If you'd rather have
 * Playwright wait for the SPA to be reachable on its own, replace
 * `reuseExistingServer: true` + `command` with a no-op and rely on the
 * environment being prepared manually.
 *
 * baseURL is http://localhost (the Caddy port).  Tests that need the
 * raw API can hit it via `http://localhost:8000` through the same
 * origin if the frontend was built with VITE_API_URL=""; otherwise the
 * production image bakes http://localhost:8000 as the API origin and
 * tests run against the dev server instead (`npm run dev` -> 5173).
 */

const PORT = process.env.E2E_PORT ?? "5173";
const BASE_URL = process.env.E2E_BASE_URL ?? `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: 10_000,
    navigationTimeout: 20_000,
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1280, height: 800 },
      },
    },
    {
      name: "mobile",
      use: {
        ...devices["Pixel 5"],
      },
      testMatch: /mobile-solve\.spec\.ts/,
    },
  ],
  webServer: {
    command: `cd web/frontend && E2E_PORT=${PORT} npx vite --port ${PORT} --strictPort`,
    url: `${BASE_URL}`,
    reuseExistingServer: true,
    timeout: 60_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});
