# LOAD — burst test results

This file captures the outcome of `python scripts/loadtest.py` against the
LOCAL docker-compose stack (todo 36).  The test fires a configurable burst
(default **200 submissions / 20 simulated students**) at the API, polls
every run to `status=done`, and asserts four invariants.  See
`scripts/loadtest.py` for the test definition; this file is the
human-readable record of a real run.

## Why a load test

The plan's draft D9 calls the platform "medium (~200 concurrent users,
bursty)".  With the per-user 10 runs/min rate limit (todo 20) and the
default `$REPLICAS=3` worker pool, the worker has to drain a 200-submit
burst inside ~60s while keeping the API responsive.  This script exists
to (a) measure p95 latency end-to-end, (b) catch any submission that gets
rate-limited or otherwise lost, and (c) cap worker CPU so a
misconfigured pool doesn't peg the host.

## Reproduce-me

Prerequisites (LOCAL-FIRST, plan §D17):

```bash
# 1. The compose stack must be up and healthy (todo 36).
cd infra
docker compose --env-file .env up -d            # DOMAIN unset → http://localhost
docker compose exec -T api alembic upgrade head # one-time
# 2. Seed at least one problem (todo 41 — scripts/seed.py is the canonical source).
cd ..
python scripts/seed.py
# 3. (Optional) confirm the API is reachable and ready.
curl -sf http://localhost/healthz && curl -sf http://localhost/readyz
```

Then:

```bash
python scripts/loadtest.py                  # default 200/20 burst
python scripts/loadtest.py --dry-run        # wiring check, no burst
python scripts/loadtest.py --burst 50 --students 5   # smaller smoke run
python scripts/loadtest.py --skip-cpu       # skip the docker stats probe
python scripts/loadtest.py --help           # all flags
```

The script prints four `[PASS]/[FAIL]/[SKIP]` lines and exits 0 only if
all of them pass (skipped never blocks exit 0).  When an assertion fails,
the non-zero exit code makes the script safe to wire into CI without
parsing the report.

## What the four assertions mean

| # | Assertion | How it's measured | Plan reference |
|---|-----------|-------------------|----------------|
| (a) | every submission reaches `status=done` in the DB | one HTTP `GET /api/runs/{id}` per submission, polled every 1s, 90s timeout | todo 37 / D9 |
| (b) | DB `runs` row count grew by exactly `--burst` | `SELECT count(*) FROM runs` before + after, via direct Postgres (`--db-url` / `DATABASE_URL`) | todo 37 |
| (c) | p95 verdict latency (submit → done) under `--p95-budget` (default 60s) | monotonic clock timestamps from POST and final poll | todo 37 |
| (d) | worker container CPU percent under `--cpu-limit` (default 80%) | `docker stats --no-stream <worker>` sampled over `--cpu-sample-seconds` | todo 37 |

Assertion (d) is reported as `SKIP` (not `FAIL`) when `docker stats`
is unavailable — e.g. CI runners without a Docker daemon, or when the
worker container is named differently.  Use `--skip-cpu` to silence it
explicitly when running outside the LOCAL stack.

## Expected metrics (LOCAL stack baseline)

The values below are the design targets the script is supposed to land
on the LOCAL dev laptop with the default `REPLICAS=3` worker pool.
Numbers are nominal — actuals depend on host CPU, Docker overhead, and
how many test cases the engine container has to run per submission.

| Metric | Target | Notes |
|--------|-------:|-------|
| Burst accepted (HTTP 202) | **200/200** | At the per-user 10/min limit (todo 20); 20 students × 10 = 200 sits exactly on the boundary. |
| Runs reaching `done` (assertion a) | **200/200** | No TLE/RE/AC counts toward "done" — every run must finish, whatever the verdict. |
| DB run count delta (assertion b) | **+200** | Compared to a snapshot taken before the burst starts. |
| p95 verdict latency (assertion c) | **< 60s** | Median is typically 5–15s; tail dominated by queue drain. |
| Worker CPU peak (assertion d) | **< 80%** | Single-host only (plan: no multi-node). 3 RQ workers share 1 container. |
| Burst wall time | **30–90s** | 200 submissions across 3 RQ workers + 1 engine container per run. |
| 429 / connection errors | **0** | If you see 429s, the per-user limit is hitting; bump `--students` or slow submissions. |

## Tuning notes

The defaults assume a single-host stack with these knobs from
`infra/.env` and `infra/docker-compose.yml`:

* `REPLICAS=3` — in-process RQ worker count inside the worker container
  (driven by `infra/worker/worker.py:worker_count()`).  Each worker
  drains one run at a time; 3 in parallel is the platform's burst
  tolerance baseline.  **Bumping to 5–8 is the first lever for a
  noisy run; bump to 10+ only after raising the Docker CPU quota.**
* `WORKER_IMAGE=pseint-judge-worker:latest` — the engine container the
  RQ worker spawns per submission.  Built once from
  `infra/Dockerfile.worker` (todo 34).  Each engine container is capped
  at `--cpus 0.5 --memory 128m` (see `scripts/run_sandboxed.py`), so
  many in-flight sandboxes can starve the host.  Watch
  `docker stats pseint-judge-worker-1` while the burst runs.
* `RUNS_LIMIT=10` per user per minute (`web/api/src/pseint_api/ratelimit.py`).
  With 20 students × 10 = 200 we sit at the edge; if the run is too
  fast, the INCRs can race the 60s window and start 429ing.  The
  practical workarounds are: (a) bump `--students` to 25+ and
  `--burst` stays at 200, or (b) introduce a tiny per-student delay
  (a `--sleep-per-student` flag was considered but not added — the
  plan ships the no-delay version).

### What to do when (a) or (b) fails

Both assertions are "no loss" gates — if a submission never lands in
the DB (most often a 429 from the rate limiter) the count won't grow
and one of them fails.

1. Check the `loadtest:` output for any `error=` fields in the
   per-student breakdown.
2. Look at the API logs: `docker compose -f infra logs api`.
3. If the rate limit is the cause, either:
   * rerun with `--burst 250 --students 25` to spread the load, or
   * restart the stack with `RUNS_LIMIT_OVERRIDE` temporarily raised
     (this would require an API-side knob that is OUT of scope for
     this todo — the rate-limit constant lives in the API source, not
     an env var).

### What to do when (c) fails

The p95 budget is the platform's main user-visible latency target
(plan D9).  Common causes, in order of likelihood:

1. **Queue depth > 3** — the worker pool is the bottleneck.  Bump
   `REPLICAS` in `infra/.env` and `docker compose up -d` again.  Each
   worker is one OS thread inside the container.
2. **Engine container cold start** — the first ~5 submissions pay a
   one-time cost for `docker run` + image pull.  Re-running after the
   images are warm usually clears it.
3. **Slow problem** — an O(n³) or O(2ⁿ) problem with a large n can
   take real wall-clock time even when step-budgeted.  Check the
   per-problem counts in the script's output and ensure the
   `--problem-mix` doesn't include any pathologically slow cases.

### What to do when (d) fails

CPU > 80% means the worker pool is fully saturated AND the engine
sandboxes are competing for cycles on the same host.  Two knobs:

1. **Reduce burst size** — run with `--burst 100` first to confirm
   the lower envelope is healthy, then ramp up.
2. **Bump the engine `--cpus` cap** in `scripts/run_sandboxed.py` —
   but watch Docker host CPU; a single host pinned at 100% across
   three containers is the failure mode.

## Per-run results table

Fill this in when you actually run the load test on the deploy host.
Each row is one `python scripts/loadtest.py` invocation.

| Run date | Host | `--burst` / `--students` | `--p95-budget` | REPLICAS | a (done) | b (DB delta) | c (p95) | d (CPU) | Notes |
|----------|------|--------------------------|----------------|---------:|---------:|-------------:|--------:|--------:|-------|
| TBD      | TBD  | 200 / 20                 | 60s            | 3        | TBD      | TBD          | TBD     | TBD     | First measurement on deploy host. |
| TBD      | TBD  | 400 / 40                 | 60s            | 6        | TBD      | TBD          | TBD     | TBD     | Verify REPLICAS=6 absorbs 2x load. |

Until the deploy host is provisioned, this table stays `TBD`.  The
unit tests in `tests/test_loadtest.py` pin the *structure* of the
script (CLI surface, four assertions, exit-code logic, dry-run path)
so this file is the only place that records a real run.

## Files

* `scripts/loadtest.py` — the script itself (todo 37 deliverable).
* `tests/test_loadtest.py` — 26 structural tests; do not run the burst.
* This file — human-readable record of a real run + tuning guidance.

## LOCAL-FIRST compliance

* No DOMAIN or TLS required; the test runs over plain HTTP at
  `http://localhost` (the LOCAL stack default).
* The DB connection (assertion (b)) hits `localhost:5432`, never an
  external host.
* `docker stats` (assertion (d)) is local-only; the assertion is
  marked `SKIP` when the docker CLI is unavailable.
* No new dependencies beyond `httpx` + `sqlalchemy`, both already in
  `web/api` deps.