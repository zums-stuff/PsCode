# Running the Playwright E2E journeys

The 6 journeys in `../e2e/` (plan todo 42) drive the LIVE LOCAL stack —
no API mocking, no stubbed WebSocket.  Every request goes through
the seeded data (`scripts/seed.py`) on the running compose stack or
the dev server.

## Prerequisites

1. **Node 20+ and npm 10+** for the Vite dev server / Playwright
   browser binaries.  The repo's `web/frontend/` already ships with
   `node_modules/` for the unit tests, but `@playwright/test` is NOT
   yet installed.

2. **Install Playwright into the frontend** (one time):

   ```bash
   cd web/frontend
   npm install --save-dev @playwright/test@^1.63.0
   npx playwright install --with-deps chromium
   ```

   The `--with-deps` flag pulls the Linux libs Chromium needs (Ubuntu
   `libnss3`, `libxss1`, etc.).  macOS / Windows users should use
   `npx playwright install chromium` without `--with-deps`.

3. **Bring the LOCAL stack up** so the SPA + API + Postgres + Redis
   + workers + anticheat engine are all reachable.  Either:

   **Option A — full compose stack (recommended):**

   ```bash
   cd infra
   DOMAIN= docker compose up -d
   ```

   Caddy serves the SPA at http://localhost:80 and proxies /api/*,
   /ws/*, /healthz, /readyz to the api container.  *Note*: the api
   container is NOT exposed on host port 8000 by default — the
   frontend's hardcoded `VITE_API_URL` (or the default
   `http://localhost:8000` in `src/lib/api.ts`) requires the api to
   be reachable there.  Two ways to satisfy this:

   - Add a `ports:` override exposing the api on `127.0.0.1:8000:8000`
     via `infra/docker-compose.override.yml` (recommended for testing).
   - Rebuild the frontend image with `VITE_API_URL=""` so the SPA uses
     relative paths proxied by Caddy.

   **Option B — dev server + api directly (no Docker):**

   ```bash
   # Terminal 1 — api + worker (uses local Postgres at :5432)
   pip install -e web/api engine judge
   DATABASE_URL=postgresql+psycopg://pseint:pseint@localhost:5432/pseint \
       uvicorn pseint_api.main:app --host 0.0.0.0 --port 8000

   # Terminal 2 — vite dev server (port 5173, hardcoded API at 8000)
   cd web/frontend
   npm run dev
   ```

   `playwright.config.ts` defaults to `http://localhost:5173`
   (vite) — matches this setup out of the box.

4. **Seed the database** (idempotent — re-runs are no-ops):

   ```bash
   python scripts/seed.py
   ```

   Expect the final line `[22, 1, 4, 1]` (users, classes, problems,
   contests).

## Running the suites

From the repo root:

```bash
npx playwright test                # all 6 journeys
npx playwright test e2e/register-and-solve.spec.ts
npx playwright test --project=mobile
```

Or via the npm script (from `web/frontend/`):

```bash
npm run test:e2e
```

The CI invocation should pass `--reporter=dot` or `--reporter=html`
for compact output and write the report under `playwright-report/`.

## What the suites cover

| File                                  | Journey                                          |
| ------------------------------------- | ------------------------------------------------ |
| `e2e/register-and-solve.spec.ts`      | (a) register → solve → submit, inline errors      |
| `e2e/assignment-best.spec.ts`         | (b) assignment best-count badge                   |
| `e2e/contest-scoreboard.spec.ts`      | (c) contest registration → submit → live scoreboard |
| `e2e/forum-locking.spec.ts`           | (d) forum post + contest lock + teacher pin       |
| `e2e/anticheat-diff.spec.ts`          | (e) teacher anticheat report + diff viewer        |
| `e2e/mobile-solve.spec.ts`            | (f) mobile (Pixel 5, 393px) solve layout          |

Each test cleans up after itself where feasible (unique usernames via
the worker pid + epoch suffix).  Tests that mutate state (assignment
submissions, forum threads, anticheat pins) are tolerant of repeated
runs — the seed makes the assertions idempotent.

## Troubleshooting

- **All tests fail with "ERR_CONNECTION_REFUSED" at localhost:5173**
  — the vite dev server didn't start.  Check the `webServer` block
  in `playwright.config.ts`; the `reuseExistingServer: true` flag
  expects something already on the port.

- **`@playwright/test` not found** — re-run step 2 of the
  prerequisites; the package isn't in `web/frontend/package.json`
  yet (added in todo 42 commit, requires `npm install`).

- **Tests that need `student01..student20` fail with 401** — the
  seed didn't run against this database.  Re-run `python
  scripts/seed.py`.

- **Contest journey shows "Finalizado" instead of "En curso"** — the
  seeded contest window (now-1h → now+2h) elapsed.  Re-run the seed
  to reset `start_at` / `end_at`.
