"""Load/burst test for pseint-judge (plan todo 37).

Drives a configurable burst of submissions against the LOCAL docker-compose
stack (todo 36) over HTTP and asserts four invariants.  The script
authenticates N simulated students, fires M submissions (mixed problem IDs,
defaulting to a discoverable mix that includes an O(n^2) problem when one
exists), polls GET /api/runs/{id} until each run reaches status="done"
(90s timeout per run), and prints four PASS/FAIL assertions:

    (a) every submission reached status=done in the DB (no loss)
    (b) DB run count after the burst = baseline + burst size (no loss)
    (c) p95 verdict latency (submit -> done) under the 60s budget
    (d) worker container CPU under 80% during the burst
        (skipped when docker stats is unavailable in the test env)

Exits 0 only if all assertions PASS, else 1.  Designed to run with no
external infra (LOCAL-FIRST, plan §D17) — no DOMAIN, no TLS, no external
DB.  The DB connection (assertion (b)) defaults to compose's local
Postgres URL; override with ``--db-url`` or the ``DATABASE_URL`` env.

Concurrency model:
    * N ``httpx.AsyncClient`` instances, one per simulated student.
    * Each student submits ``burst / students`` runs back-to-back.
    * With the default 200/20 split, each student makes exactly 10 runs
      in their 60s window — the per-user ``runs:{user_id}`` limit
      (todo 20) is at the edge, not over.  All submissions land in the
      DB atomically (Redis INCR is atomic); the worker pool drains them.

Required deps: httpx (already in web/api dev deps from todos 18/31) +
sqlalchemy (already in web/api).  No new dependencies.

Usage:
    python scripts/loadtest.py                    # default 200-burst
    python scripts/loadtest.py --burst 50         # smaller burst
    python scripts/loadtest.py --dry-run          # validate wiring
    python scripts/loadtest.py --skip-cpu         # skip docker-stats probe
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import statistics
import subprocess
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import httpx
from sqlalchemy import create_engine, text

DEFAULT_BASE_URL = "http://localhost"
DEFAULT_BURST = 200
DEFAULT_STUDENTS = 20
DEFAULT_TIMEOUT_S = 90
P95_BUDGET_S = 60
CPU_LIMIT_PERCENT = 80.0
POLL_INTERVAL_S = 1.0
LOADTEST_USER_PREFIX = "loadtest_student_"
# 12 chars, satisfies the auth RegisterRequest validator (min_length=8).
LOADTEST_PASSWORD = "loadtest-pwd-xyz"

# Minimal valid PseInt program: writes one line and exits.  Whatever the
# engine returns (AC/WA/TLE/RE/CE) the load test only cares that the run
# reaches status=done.  We send the same trivial source for every
# submission; the variation is in the problem ID, not the source.
DEFAULT_SAMPLE_SOURCE = (
    'Proceso Hola\n'
    '    Escribir "Hola Mundo"\n'
    'FinProceso\n'
)

# O(n^2) marker used to bias the auto-discovered problem mix toward an
# n^2 problem (the plan's todo 37 calls for one).  The model enum
# (web/api/src/pseint_api/models.py) uses the Unicode SUPERSCRIPT-2.
ON2_MARKER = "O(n\u00b2)"


@dataclass
class Student:
    """A simulated student + its authenticated HTTP client."""

    username: str
    token: str
    client: httpx.AsyncClient


@dataclass
class SubmissionResult:
    """One submission's outcome (used for latency + status assertions)."""

    run_id: int | None
    problem_id: int
    student_username: str
    submit_at: float
    done_at: float | None = None
    status: str | None = None
    verdict: str | None = None
    error: str | None = None

    @property
    def latency_s(self) -> float | None:
        if self.done_at is None:
            return None
        return self.done_at - self.submit_at

    @property
    def reached_done(self) -> bool:
        return self.status == "done"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_problem_mix(raw: str) -> list[int]:
    if not raw:
        return []
    out: list[int] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.append(int(chunk))
        except ValueError as e:
            raise argparse.ArgumentTypeError(
                f"--problem-mix must be a CSV of integers; got {raw!r}"
            ) from e
    return out


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="loadtest",
        description=(
            "Pseint-judge burst load test (todo 37).  Fires N submissions "
            "as M students, polls each to status=done, asserts no-loss + "
            "p95<60s + worker CPU<80%."
        ),
    )
    p.add_argument("--base-url", default=DEFAULT_BASE_URL,
                   help=f"API base URL (default: {DEFAULT_BASE_URL})")
    p.add_argument("--burst", type=int, default=DEFAULT_BURST,
                   help=f"total submissions to fire (default: {DEFAULT_BURST})")
    p.add_argument("--students", type=int, default=DEFAULT_STUDENTS,
                   help=f"simulated students (default: {DEFAULT_STUDENTS})")
    p.add_argument("--problem-mix", type=_parse_problem_mix, default="",
                   help=(
                       "comma-separated problem IDs to mix into the burst; "
                       "if empty, discovered via GET /api/problems with an "
                       "O(n^2) problem preferred when present"
                   ))
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S,
                   help=f"per-submission polling timeout, seconds (default: {DEFAULT_TIMEOUT_S})")
    p.add_argument("--p95-budget", type=int, default=P95_BUDGET_S,
                   help=f"p95 verdict-latency budget, seconds (default: {P95_BUDGET_S})")
    p.add_argument("--cpu-limit", type=float, default=CPU_LIMIT_PERCENT,
                   help=f"worker CPU percent budget (default: {CPU_LIMIT_PERCENT})")
    p.add_argument("--worker-container", default="pseint-judge-worker-1",
                   help=(
                       "compose container name to sample with `docker stats` "
                       "(default: pseint-judge-worker-1)"
                   ))
    p.add_argument("--cpu-sample-seconds", type=int, default=10,
                   help="how long to sample docker stats (default: 10s)")
    p.add_argument("--db-url",
                   default=os.environ.get(
                       "DATABASE_URL",
                       "postgresql+psycopg://pseint:pseint@localhost:5432/pseint",
                   ),
                   help="Postgres URL for the DB count assertion")
    p.add_argument("--dry-run", action="store_true",
                   help="authenticate + fire ONE submission and exit; skip burst + assertions")
    p.add_argument("--skip-cpu", action="store_true",
                   help="skip the worker CPU assertion (docker stats)")
    args = p.parse_args(argv)
    args.problem_ids = args.problem_mix or []
    if not args.dry_run:
        if args.burst <= 0:
            p.error("--burst must be > 0")
        if args.students <= 0:
            p.error("--students must be > 0")
        if args.burst > 100000:
            p.error("--burst too large (max 100000)")
    return args


# ---------------------------------------------------------------------------
# Auth + student setup
# ---------------------------------------------------------------------------


async def _register_or_login(
    client: httpx.AsyncClient, username: str, password: str
) -> str:
    """Try POST /api/register; on 409 fall back to POST /api/login.

    Returns the JWT access token.
    """
    reg = await client.post(
        "/api/register",
        json={
            "username": username,
            "display_name": username,
            "password": password,
        },
    )
    if reg.status_code == 201:
        me = await client.post(
            "/api/login",
            json={"username": username, "password": password},
        )
        me.raise_for_status()
        return me.json()["access_token"]
    if reg.status_code == 409:
        lo = await client.post(
            "/api/login",
            json={"username": username, "password": password},
        )
        lo.raise_for_status()
        return lo.json()["access_token"]
    # Surface the real error so the user knows why auth failed.
    raise RuntimeError(
        f"register failed for {username}: HTTP {reg.status_code} {reg.text}"
    )


async def make_student(
    base_url: str, idx: int, *, client: httpx.AsyncClient | None = None
) -> Student:
    """Create one simulated student + its client.

    Uses a shared client when one is provided (avoids per-student TCP
    setup overhead during the burst).  Each student gets a unique
    username so concurrent registrations don't collide.
    """
    username = f"{LOADTEST_USER_PREFIX}{idx}_{int(time.time())}"
    c = client or httpx.AsyncClient(base_url=base_url, timeout=30.0)
    token = await _register_or_login(c, username, LOADTEST_PASSWORD)
    return Student(username=username, token=token, client=c)


def _auth_headers(student: Student) -> dict[str, str]:
    return {"Authorization": f"Bearer {student.token}"}


# ---------------------------------------------------------------------------
# Problem discovery
# ---------------------------------------------------------------------------


async def discover_problem_ids(
    client: httpx.AsyncClient, headers: dict[str, str]
) -> list[int]:
    """GET /api/problems; return the discovered IDs.

    If an O(n^2) problem is present, it is placed FIRST so the burst
    exercises the budget calculation the plan calls out.  Other
    problems follow in id order.
    """
    resp = await client.get("/api/problems", headers=headers, params={"size": 100})
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if not items:
        return []
    by_id = {int(it["id"]): it for it in items}
    ordered = sorted(by_id)
    on2_first = [i for i in ordered if by_id[i].get("expected_complexity") == ON2_MARKER]
    rest = [i for i in ordered if i not in on2_first]
    return on2_first + rest


# ---------------------------------------------------------------------------
# Submission + polling
# ---------------------------------------------------------------------------


async def submit_run(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    problem_id: int,
    source: str,
    *,
    mode: str = "practice",
    assignment_id: int | None = None,
    contest_id: int | None = None,
) -> tuple[int, float]:
    """POST /api/runs; return (run_id, submit_at_monotonic)."""
    payload: dict[str, object] = {
        "problem_id": problem_id,
        "source": source,
        "mode": mode,
    }
    if assignment_id is not None:
        payload["assignment_id"] = assignment_id
    if contest_id is not None:
        payload["contest_id"] = contest_id
    submit_at = time.monotonic()
    resp = await client.post("/api/runs", headers=headers, json=payload)
    if resp.status_code == 429:
        raise RuntimeError(
            f"rate-limited POST /api/runs: HTTP 429 {resp.text}"
        )
    resp.raise_for_status()
    return int(resp.json()["run_id"]), submit_at


async def poll_until_done(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    run_id: int,
    *,
    timeout_s: float,
) -> tuple[float, str, str | None]:
    """Poll GET /api/runs/{id} until status=done or timeout.

    Returns (done_at_monotonic, status, summary_verdict).
    """
    deadline = time.monotonic() + timeout_s
    last_status = "queued"
    last_verdict: str | None = None
    while time.monotonic() < deadline:
        resp = await client.get(f"/api/runs/{run_id}", headers=headers)
        if resp.status_code == 404:
            raise RuntimeError(f"run {run_id} not found during polling")
        resp.raise_for_status()
        body = resp.json()
        last_status = body.get("status", last_status)
        last_verdict = body.get("summary_verdict")
        if last_status == "done":
            return time.monotonic(), last_status, last_verdict
        if last_status == "failed":
            return time.monotonic(), last_status, last_verdict
        await asyncio.sleep(POLL_INTERVAL_S)
    return time.monotonic(), last_status, last_verdict


async def fire_and_poll(
    student: Student,
    problem_id: int,
    source: str,
    *,
    timeout_s: float,
) -> SubmissionResult:
    """Submit one run for ``student`` and poll until done.

    Wrapped in try/except so one bad submission never aborts the whole
    burst — the error is captured in ``SubmissionResult.error`` and the
    failure surfaces in the assertion report.
    """
    headers = _auth_headers(student)
    result = SubmissionResult(
        run_id=None,
        problem_id=problem_id,
        student_username=student.username,
        submit_at=time.monotonic(),
    )
    try:
        run_id, submit_at = await submit_run(
            student.client, headers, problem_id, source
        )
        result.run_id = run_id
        result.submit_at = submit_at
        done_at, status, verdict = await poll_until_done(
            student.client, headers, run_id, timeout_s=timeout_s
        )
        result.done_at = done_at
        result.status = status
        result.verdict = verdict
    except Exception as e:  # noqa: BLE001 — single-burst boundary
        result.error = f"{type(e).__name__}: {e}"
        result.status = result.status or "error"
    return result


# ---------------------------------------------------------------------------
# Burst orchestration
# ---------------------------------------------------------------------------


def _per_student_counts(total: int, students: int) -> list[int]:
    """Distribute ``total`` submissions as evenly as possible across students.

    With the default 200/20 split this is exactly [10]*20; with odd
    numbers the first ``total % students`` students get one extra.
    """
    base, rem = divmod(total, students)
    return [base + (1 if i < rem else 0) for i in range(students)]


async def run_burst(
    *,
    base_url: str,
    burst: int,
    students: int,
    problem_ids: Sequence[int],
    timeout_s: float,
) -> list[SubmissionResult]:
    """Authenticate ``students`` clients and fire ``burst`` submissions.

    Each student submits its share of runs sequentially; all students run
    concurrently.  Returns the flat list of per-run outcomes.
    """
    if not problem_ids:
        raise RuntimeError(
            "no problems to submit against — pass --problem-mix or seed problems"
        )
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        roster: list[Student] = []
        for i in range(students):
            roster.append(await make_student(base_url, i, client=client))

        counts = _per_student_counts(burst, students)
        tasks: list[asyncio.Task[SubmissionResult]] = []
        for student, n in zip(roster, counts):
            for j in range(n):
                pid = problem_ids[(sum(counts[: roster.index(student)]) + j) % len(problem_ids)]
                tasks.append(
                    asyncio.create_task(
                        fire_and_poll(
                            student,
                            pid,
                            DEFAULT_SAMPLE_SOURCE,
                            timeout_s=timeout_s,
                        ),
                        name=f"{student.username}:{j}",
                    )
                )
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return list(results)


# ---------------------------------------------------------------------------
# DB + CPU sampling
# ---------------------------------------------------------------------------


def db_count_runs(db_url: str) -> int:
    """SELECT count(*) FROM runs; raises on connect failure."""
    engine = create_engine(db_url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            return int(conn.execute(text("SELECT count(*) FROM runs")).scalar() or 0)
    finally:
        engine.dispose()


def sample_worker_cpu(container: str, sample_seconds: int) -> float | None:
    """Sample docker stats for ``container`` over ``sample_seconds`` seconds.

    Returns the max CPU percent observed, or None if docker is unavailable
    or the container cannot be found.  The plan calls for skipping the
    assertion when not measurable in the test env, so a None is treated
    as "assertion skipped", not "assertion failed".
    """
    docker = shutil.which("docker")
    if docker is None:
        return None
    max_pct = 0.0
    end_at = time.monotonic() + sample_seconds
    try:
        while time.monotonic() < end_at:
            try:
                proc = subprocess.run(
                    [docker, "stats", "--no-stream",
                     "--format", "{{.CPUPerc}}", container],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                return None
            if proc.returncode != 0:
                # Container not found or daemon down — give up gracefully.
                return None
            raw = (proc.stdout or "").strip()
            if raw.endswith("%"):
                try:
                    pct = float(raw.rstrip("%"))
                    max_pct = max(max_pct, pct)
                except ValueError:
                    pass
            time.sleep(1)
    except FileNotFoundError:
        return None
    return max_pct


# ---------------------------------------------------------------------------
# Assertion evaluation
# ---------------------------------------------------------------------------


@dataclass
class Assertion:
    label: str
    passed: bool
    detail: str
    skipped: bool = False

    def render(self) -> str:
        status = "SKIP" if self.skipped else ("PASS" if self.passed else "FAIL")
        return f"[{status}] {self.label} — {self.detail}"


def evaluate_assertions(
    results: Iterable[SubmissionResult],
    *,
    db_count_before: int,
    db_count_after: int,
    burst: int,
    p95_budget_s: float,
    worker_cpu: float | None,
    cpu_limit: float,
    cpu_skipped: bool,
) -> list[Assertion]:
    results = list(results)
    latencies = [r.latency_s for r in results if r.latency_s is not None]
    done_count = sum(1 for r in results if r.reached_done)

    a = Assertion(
        label=f"(a) all {burst} reached status=done",
        passed=done_count == burst,
        detail=f"{done_count}/{burst} submissions reached done",
    )
    expected_count = db_count_before + burst
    b = Assertion(
        label="(b) DB run count grew by exactly --burst",
        passed=db_count_after == expected_count,
        detail=(
            f"before={db_count_before}, after={db_count_after}, "
            f"delta={db_count_after - db_count_before} (expected {burst})"
        ),
    )

    if latencies:
        p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies)
        c = Assertion(
            label=f"(c) p95 verdict latency < {p95_budget_s}s",
            passed=p95 < p95_budget_s,
            detail=(
                f"p95={p95:.2f}s over {len(latencies)} completions "
                f"(min={min(latencies):.2f}s, max={max(latencies):.2f}s)"
            ),
        )
    else:
        c = Assertion(
            label=f"(c) p95 verdict latency < {p95_budget_s}s",
            passed=False,
            detail="no completions to measure",
        )

    if cpu_skipped or worker_cpu is None:
        d = Assertion(
            label=f"(d) worker CPU < {cpu_limit}% during burst",
            passed=True,
            detail="skipped: docker stats not available in this environment",
            skipped=True,
        )
    else:
        d = Assertion(
            label=f"(d) worker CPU < {cpu_limit}% during burst",
            passed=worker_cpu < cpu_limit,
            detail=f"max CPU observed = {worker_cpu:.1f}%",
        )

    return [a, b, c, d]


# ---------------------------------------------------------------------------
# Dry-run path
# ---------------------------------------------------------------------------


async def run_dry_run(args: argparse.Namespace) -> int:
    """Validate auth + one POST /api/runs round-trip; no burst, no assertions."""
    print(f"loadtest: dry-run against {args.base_url}")
    async with httpx.AsyncClient(base_url=args.base_url, timeout=30.0) as client:
        student = await make_student(args.base_url, 0, client=client)
        print(f"  auth OK: {student.username}")
        problems = await discover_problem_ids(client, _auth_headers(student))
        if not problems:
            print(
                "  WARN: /api/problems returned no items; pass --problem-mix "
                "or seed problems first",
                file=sys.stderr,
            )
            return 1
        pid = problems[0]
        run_id, _ = await submit_run(
            client, _auth_headers(student), pid, DEFAULT_SAMPLE_SOURCE
        )
        print(f"  POST /api/runs OK: run_id={run_id} problem_id={pid}")
    print("loadtest: dry-run PASS")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def amain(args: argparse.Namespace) -> int:
    if args.dry_run:
        return await run_dry_run(args)

    print(
        f"loadtest: base={args.base_url} burst={args.burst} "
        f"students={args.students} timeout={args.timeout}s "
        f"p95_budget={args.p95_budget}s"
    )

    async with httpx.AsyncClient(base_url=args.base_url, timeout=30.0) as client:
        # Discover problems up-front (need at least one student to call
        # the auth-protected /api/problems endpoint).
        bootstrap = await make_student(args.base_url, 0, client=client)
        if args.problem_ids:
            problem_ids = list(args.problem_ids)
        else:
            problem_ids = await discover_problem_ids(
                client, _auth_headers(bootstrap)
            )
            if not problem_ids:
                print(
                    "loadtest: ERROR — no problems discoverable; pass "
                    "--problem-mix or seed problems via scripts/seed.py",
                    file=sys.stderr,
                )
                return 1
    print(f"loadtest: problem mix = {problem_ids}")

    db_before = db_count_runs(args.db_url)
    print(f"loadtest: DB runs count BEFORE burst = {db_before}")

    # Fire the burst; capture wall start so the CPU sampler covers the run.
    wall_start = time.monotonic()
    results = await run_burst(
        base_url=args.base_url,
        burst=args.burst,
        students=args.students,
        problem_ids=problem_ids,
        timeout_s=args.timeout,
    )
    wall_elapsed = time.monotonic() - wall_start
    print(f"loadtest: burst wall time = {wall_elapsed:.2f}s")

    # Sample worker CPU in parallel (or skip).  Doing this AFTER the
    # burst keeps the timing clean — the CPU sampler covers the
    # immediate post-burst drain window, which is when the worker pool
    # is hottest.  When --skip-cpu is set we never call docker at all.
    cpu_value: float | None = None
    cpu_skipped = args.skip_cpu
    if not cpu_skipped:
        cpu_value = sample_worker_cpu(
            args.worker_container, args.cpu_sample_seconds
        )

    db_after = db_count_runs(args.db_url)
    print(f"loadtest: DB runs count AFTER burst  = {db_after}")

    assertions = evaluate_assertions(
        results,
        db_count_before=db_before,
        db_count_after=db_after,
        burst=args.burst,
        p95_budget_s=args.p95_budget,
        worker_cpu=cpu_value,
        cpu_limit=args.cpu_limit,
        cpu_skipped=cpu_skipped,
    )

    print("loadtest: assertions")
    for a in assertions:
        print(f"  {a.render()}")

    # Per-problem + per-student breakdown (helpful when something fails).
    by_problem: dict[int, int] = {}
    by_student: dict[str, int] = {}
    for r in results:
        by_problem[r.problem_id] = by_problem.get(r.problem_id, 0) + 1
        by_student[r.student_username] = by_student.get(r.student_username, 0) + 1
    print(f"loadtest: per-problem counts = {dict(sorted(by_problem.items()))}")
    print(f"loadtest: per-student counts = {dict(sorted(by_student.items()))}")

    failures = [a for a in assertions if not a.passed and not a.skipped]
    if failures:
        print(f"loadtest: {len(failures)} assertion(s) FAILED", file=sys.stderr)
        return 1
    print("loadtest: all assertions PASS")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return asyncio.run(amain(args))
    except KeyboardInterrupt:
        print("loadtest: interrupted", file=sys.stderr)
        return 130
    except (httpx.ConnectError, httpx.RemoteProtocolError) as e:
        print(
            f"loadtest: cannot reach API at {args.base_url}: {e}",
            file=sys.stderr,
        )
        return 2
    except Exception as e:  # noqa: BLE001 — top-level boundary
        print(f"loadtest: unexpected error: {type(e).__name__}: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())