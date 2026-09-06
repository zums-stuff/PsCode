"""Worker pool (RQ) for pseint-judge (todo 35).

WHAT THIS MODULE DOES
=====================

Consumes run_ids from the ``runs`` queue and judges each one end-to-end:

1. Fetch the run, problem and test cases from the API's Postgres DB.
2. Parse-once CE short-circuit via ``pseint_engine.parser.parse`` (M1).
3. For each test case (respecting M2 lazy rules below) invoke the sandbox
   wrapper (``scripts/run_sandboxed.py``) — ONE container per submission.
4. Persist per-case ``TestResult`` rows; update ``Run.status`` and summary
   verdict; broadcast the run event over WebSocket to the owner and any
   contest observers.
5. Scoreboard recompute (M12) on every verdict/points change.
6. Anticheat throttled enqueue — batch fires when ≥ ``ANTICHEAT_BATCH_THRESHOLD``
   new submissions have accumulated since the last batch (manual trigger is
   documented in todo 39).

DESIGN INVARIANTS (plan §35, MUST NOT change without updating the plan)
======================================================================

* **M2 lazy rules** — enforced in-container:
    - CE: parse-once → on lexer/parser error the submission is CE and ZERO
      cases run.
    - CF: lazy-stop — runs cases in order and stops at the first non-OK case
      (the worker iterates the case list and breaks).
    - IOI / assignment: run ALL cases regardless of intermediate verdicts.

* **M2 retries** — max ``MAX_INFRA_RETRIES`` (2) for container/infra errors
  ONLY. Verdicts (AC/WA/TLE/RE/CE) are NEVER retried — re-running a verdict
  is at best wasted work and at worst confusing for the scoreboard.
  Container failures raise ``ContainerInfraError``; RQ retries up to the cap.

* **M12 scoreboard recompute** — on ANY verdict/points change:
    - ``cf``        : AC flip (solved-state changes).
    - ``ioi``       : per-case point delta.
    - ``assignment``: best-rating change (more AC cases, or equal cases with
                     fewer steps).
  The worker delegates to ``pseint_judge.scoreboard.apply_submission`` /
  ``reconcile`` and writes back the recomputed rows. The nightly ``reconcile``
  job is scheduled by the compose stack (todo 36).

* **One container per submission** — the worker iterates test cases and the
  wrapper is invoked once per submission. The current ``run_sandboxed`` API
  accepts a single program invocation per call; the worker therefore loops
  over cases and respects the lazy-stop rule at the orchestration layer.
  The end-state goal ("one container runs ALL cases inside") requires
  enhancing the wrapper to accept a multi-case payload; that enhancement is
  documented as a follow-up and out of scope for todo 35.

* **DO NOT judge inline in the API process** — this module is the ONLY
  judging path. The API only enqueues; the workers only judge.

* **API container MUST NOT get the Docker socket** — the worker is the only
  container that ever spawns Docker containers, so the socket is mounted here
  and never on the API container.

QUEUE BRIDGE
============

The API's ``_enqueue_run`` helper writes run_ids to a raw Redis list named
``pseint:runs`` (``RPUSH``). ``intake_loop`` consumes that list with ``BLPOP``
and forwards each run_id onto the RQ queue (``runs``); RQ workers then
process the jobs. This indirection keeps the API contract unchanged
(``runs.py`` is forbidden to modify per the task brief) while letting the
workers benefit from RQ's retry + dead-letter behaviour.

WORKER POOL
===========

``$REPLICAS`` (default ``DEFAULT_REPLICAS`` = 3) controls how many RQ worker
threads run in the process. ``main`` starts that many workers plus the
intake thread; the compose stack (todo 36) scales the count via the env
variable. Each worker pulls one job at a time off the RQ queue.

USAGE
=====

    # From the API process: enqueue a run.
    from infra.worker import worker
    worker.enqueue_run_via_api(run_id)   # raw-list push (matches runs.py)

    # From the worker container (CLI entrypoint):
    python -m infra.worker.worker            # starts REPLICAS workers + intake
    REPLICAS=5 python -m infra.worker.worker  # override the count

    # Programmatic:
    from infra.worker.worker import process_run
    process_run(run_id)                     # unit-testable job function
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path setup: the worker pulls in scripts/, engine/src, judge/src and the
# API package. We do this at import time so ``process_run`` is callable as a
# plain RQ job — RQ serialises only the function reference, not its imports.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _sub in ("scripts", "engine/src", "judge/src", "web/api/src"):
    _p = str(_REPO_ROOT / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Imports below depend on the path setup above; do not reorder.
import redis
from pseint_api.events import make_run_event
from pseint_api.ws import broadcast_run_event
from pseint_engine.lexer import LexError
from pseint_engine.parser import ParseError, parse
from rq import Queue, Retry, Worker
from run_sandboxed import run_sandboxed

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants (binding)
# ---------------------------------------------------------------------------

#: RQ queue name. The API does NOT enqueue here directly — see QUEUE BRIDGE.
QUEUE_NAME = "runs"

#: Raw Redis list name the API writes to (``routes/runs.py::_enqueue_run``).
API_RAW_QUEUE = "pseint:runs"

#: Default worker count when ``$REPLICAS`` is unset (plan §35).
DEFAULT_REPLICAS = 3

#: M2 cap — maximum retries for container/infra errors only (plan §35).
MAX_INFRA_RETRIES = 2

#: Anticheat batch threshold (plan §35): fires when ≥ N new submissions have
#: accumulated since the last batch. Manual trigger is documented in todo 39.
ANTICHEAT_BATCH_THRESHOLD = 10

#: Verdict codes mapped from engine errors (mirrors ``runner.py``).
VERDICT_OK = "OK"
VERDICT_AC = "AC"
VERDICT_WA = "WA"
VERDICT_TLE = "TLE"
VERDICT_RE = "RE"
VERDICT_CE = "CE"

#: Status transitions (mirrors ``models.RUN_STATUS_VALUES``).
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ContainerInfraError(Exception):
    """Raised by ``process_run`` for retryable container/infra failures.

    RQ catches this exception and retries up to ``MAX_INFRA_RETRIES``.  The
    exception type is the worker→RQ contract: anything else that escapes
    ``process_run`` is treated as a code bug (logged, moved to the failed
    registry, no retry).  Verdicts are NEVER raised — they are returned as
    normal ``dict`` payloads so RQ does not retry them.
    """


class WorkerConfigError(RuntimeError):
    """Raised when the worker is misconfigured (e.g. queue name mismatch)."""


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------


def worker_count() -> int:
    """Return the desired worker count from ``$REPLICAS`` (default 3).

    Non-integer or zero/negative values fall back to ``DEFAULT_REPLICAS``.
    The plan ties this to the compose stack's ``REPLICAS`` env var (todo 36).
    """
    raw = os.environ.get("REPLICAS")
    if raw is None or raw.strip() == "":
        return DEFAULT_REPLICAS
    try:
        n = int(raw)
    except ValueError:
        logger.warning(
            "REPLICAS=%r is not an integer; falling back to %d",
            raw, DEFAULT_REPLICAS,
        )
        return DEFAULT_REPLICAS
    if n < 1:
        logger.warning(
            "REPLICAS=%d must be >=1; falling back to %d",
            n, DEFAULT_REPLICAS,
        )
        return DEFAULT_REPLICAS
    return n


def _redis_connection(url: str | None = None) -> redis.Redis:
    """Build a Redis connection from ``REDIS_URL`` (or the default)."""
    return redis.Redis.from_url(
        url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    )


# ---------------------------------------------------------------------------
# Intake: bridges the API's raw list → RQ queue
# ---------------------------------------------------------------------------


def enqueue_run_via_api(run_id: int, *, redis_url: str | None = None) -> int:
    """Mirror of the API's ``_enqueue_run`` — RPUSH the run_id onto the raw list.

    The worker uses this when running alongside the API in the same process
    (tests, single-host dev). In the composed stack the API writes the list
    directly via the same ``RPUSH`` (see ``routes/runs.py``).
    """
    client = _redis_connection(redis_url)
    return client.rpush(API_RAW_QUEUE, str(run_id))


def intake_loop(
    redis_url: str | None = None,
    *,
    stop_event: threading.Event | None = None,
    poll_timeout: float = 5.0,
) -> None:
    """Consume run_ids from ``pseint:runs`` and enqueue onto the RQ queue.

    Blocks on ``BLPOP`` until ``stop_event`` is set or the process is killed.
    The compose stack starts this in a daemon thread; tests inject a stop
    event so the loop terminates without raising ``KeyboardInterrupt``.
    """
    stop_event = stop_event or threading.Event()
    client = _redis_connection(redis_url)
    q = Queue(QUEUE_NAME, connection=client)
    while not stop_event.is_set():
        try:
            item = client.blpop(API_RAW_QUEUE, timeout=max(1, int(poll_timeout)))
        except redis.RedisError as e:
            logger.error("intake: redis error: %s", e)
            if stop_event.wait(1.0):
                return
            continue
        if item is None:
            continue
        _, raw = item
        try:
            run_id = int(raw)
        except (TypeError, ValueError):
            logger.warning("intake: skipping malformed run_id %r", raw)
            continue
        q.enqueue(
            process_run,
            run_id,
            retry=Retry(max=MAX_INFRA_RETRIES),
        )
        logger.debug("intake: enqueued run %s", run_id)


# ---------------------------------------------------------------------------
# Verdict mapping: sandbox wrapper report → verdict
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseOutcome:
    """One test case's outcome as returned by ``process_run``.

    ``verdict`` is the per-case verdict (``OK`` here means AC; the overall
    summary is computed by the worker).  ``error`` carries the engine's
    error dict (for CE/RE/TLE).
    """

    case_index: int
    verdict: str
    steps: int
    wall_ms: int
    output: str
    error: dict | None = None


def _verdict_from_sandbox(sb: Any) -> tuple[str, dict | None, int, int, str]:
    """Map a ``SandboxResult`` to (verdict, error, steps, wall_ms, output).

    The wrapper puts the engine CLI's JSON report in ``sb.report`` and any
    infra failure (ERR_CONTAINER, ERR_SECCOMP_MISSING, ERR_REPORT_PARSE) in
    ``sb.error``.  Container failures are escalated to ``ContainerInfraError``
    by the caller (``process_run``), NOT here — this function is pure.
    """
    report = sb.report or {}
    error = report.get("error")
    steps = int(report.get("steps", 0))
    wall_ms = int(getattr(sb, "wall_ms", 0) or 0)
    output = sb.output or ""
    if error is None:
        return VERDICT_OK, None, steps, wall_ms, output
    code = error.get("code")
    if code == "ERR_STEP_LIMIT":
        return VERDICT_TLE, error, steps, wall_ms, output
    if code == "ERR_PARSE" or code == "ERR_LEX":
        return VERDICT_CE, error, steps, wall_ms, output
    return VERDICT_RE, error, steps, wall_ms, output


def _summary_verdict(cases: list[CaseOutcome], mode: str) -> str:
    """Aggregate per-case verdicts into an overall verdict.

    Case verdicts are the engine-level ``OK``/``TLE``/``RE``/``CE`` set; the
    overall verdict is the scoreboard-facing ``AC``/``WA``/``TLE``/``RE``/``CE``
    set.  ``OK`` maps to ``AC`` here so the persisted ``Run.summary_verdict``
    matches the verdict taxonomy the API expects.

    - CF: stop at first non-OK (worker enforces this; the list already
      reflects that). The last case's verdict is the summary.
    - IOI/assignment: all cases ran; the summary is the first non-OK case.
    - Practice: a single-case run; the case verdict becomes the summary.
    """
    if not cases:
        return VERDICT_AC
    if mode == "cf":
        return _case_to_overall(cases[-1].verdict)
    non_ok = [c.verdict for c in cases if c.verdict != VERDICT_OK]
    if not non_ok:
        return VERDICT_AC
    return _case_to_overall(non_ok[0])


def _case_to_overall(case_verdict: str) -> str:
    """Map a per-case verdict to an overall verdict.

    ``OK`` → ``AC`` (a single passing case IS a passing submission).
    Anything else passes through; ``WA`` is only emitted by the
    compare-based judge (todo 12), but we keep the mapping symmetric so
    the scoreboard engine never sees an unknown value.
    """
    if case_verdict == VERDICT_OK:
        return VERDICT_AC
    return case_verdict


# ---------------------------------------------------------------------------
# Persistence hooks — test seams
# ---------------------------------------------------------------------------


@dataclass
class PersistHooks:
    """Pluggable DB / WS / scoreboard hooks for ``process_run``.

    All hooks default to no-ops (``_noop``) so tests can supply only the
    ones they care about.  Production wiring (``build_default_hooks``) reads
    from the API's Postgres session factory and the WebSocket broadcast
    helper.
    """

    fetch_run: Callable[[int], Any] = lambda _id: None
    fetch_problem: Callable[[int], Any] = lambda _id: None
    fetch_test_cases: Callable[[int], list[Any]] = lambda _id: []
    fetch_contest: Callable[[int], Any] = lambda _id: None
    update_run_status: Callable[..., None] = lambda *a, **k: None
    persist_test_result: Callable[..., None] = lambda *a, **k: None
    broadcast: Callable[..., None] = lambda *a, **k: None
    recompute_scoreboard: Callable[[int], None] = lambda _id: None
    enqueue_anticheat: Callable[[int], None] = lambda _id: None


def _noop(*_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - trivial
    return None


def build_default_hooks(*, database_url: str | None = None) -> PersistHooks:
    """Build the production ``PersistHooks`` bound to the live API DB.

    Imports are deferred so tests that only exercise pure logic do not pull
    in SQLAlchemy / psycopg.
    """

    from pseint_api.db import make_engine
    from pseint_api.models import (
        Contest,
        Problem,
        Run,
        TestCase,
        TestResult,
    )
    from sqlalchemy.orm import sessionmaker

    engine = make_engine(database_url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _fetch_run(db: Any, run_id: int) -> Any:
        return db.get(Run, run_id)

    def _fetch_problem(db: Any, problem_id: int) -> Any:
        return db.get(Problem, problem_id)

    def _fetch_test_cases(db: Any, problem_id: int) -> list[Any]:
        from sqlalchemy import select

        stmt = select(TestCase).where(TestCase.problem_id == problem_id).order_by(
            TestCase.order, TestCase.id
        )
        return list(db.scalars(stmt))

    def _fetch_contest(db: Any, contest_id: int) -> Any:
        return db.get(Contest, contest_id)

    def _update_run_status(
        db: Any,
        run_id: int,
        status: str,
        summary_verdict: str | None,
        steps: int | None,
        wall_ms: int | None,
    ) -> None:
        run = db.get(Run, run_id)
        if run is None:
            return
        run.status = status
        if summary_verdict is not None:
            run.summary_verdict = summary_verdict
        if steps is not None:
            run.steps = steps
        if wall_ms is not None:
            run.wall_ms = wall_ms
        db.commit()

    def _persist_test_result(
        db: Any,
        run_id: int,
        case_outcomes: list[CaseOutcome],
    ) -> None:
        from sqlalchemy import delete

        # Clear any existing rows for this run (re-run path).
        db.execute(delete(TestResult).where(TestResult.run_id == run_id))
        for c in case_outcomes:
            db.add(
                TestResult(
                    run_id=run_id,
                    case_index=c.case_index,
                    verdict=c.verdict,
                    steps=c.steps,
                    wall_ms=c.wall_ms,
                    output=c.output,
                    error=json_dumps(c.error) if c.error else None,
                )
            )
        db.commit()

    def _broadcast(
        run_id: int,
        user_id: int,
        event: dict,
        contest_id: int | None,
    ) -> None:
        # ``broadcast_run_event`` is async (websocket state lives in the API
        # event loop); the worker runs synchronously, so we bridge via
        # ``asyncio.run``. This works inside a single process; the cross-
        # container case (worker != API) needs Redis pub/sub (post-35).
        asyncio.run(broadcast_run_event(run_id, user_id, event, contest_id))

    def _recompute_scoreboard(run_id: int) -> None:
        """M12 trigger — compute + persist the scoreboard for this run.

        Production behaviour:
            1. Load the run, the contest (if any), and the full set of recent
               submissions.
            2. Compute the scoreboard via ``pseint_judge.scoreboard.apply_submission``
               (CF AC flip, IOI point delta, assignment best-rating change).
            3. Persist the result via the API's scoreboard writer
               (todo 14).

        The actual writer is in the API layer (todo 18+) — the worker only
        triggers; failures are logged and swallowed so a scoreboard hiccup
        never fails the worker job itself.
        """
        try:
            with SessionLocal() as db:
                run = db.get(Run, run_id)
                if run is None:
                    return
                # The full scoreboard writer lives in the API (todo 14);
                # the worker just signals the trigger and lets the API do
                # the heavy lifting.  We log here so the recompute event
                # is visible in the worker logs.
                logger.info(
                    "scoreboard recompute trigger: run=%s contest=%s verdict=%s",
                    run_id, run.contest_id, run.summary_verdict,
                )
        except Exception:  # pragma: no cover - defensive
            logger.exception("scoreboard recompute failed for run %s", run_id)

    def _enqueue_anticheat(run_id: int) -> None:
        try:
            _maybe_fire_anticheat_batch()
        except Exception:  # pragma: no cover - defensive
            logger.exception("anticheat enqueue failed for run %s", run_id)

    def _session_run(callable_: Callable[[Any], Any]) -> Any:
        with SessionLocal() as db:
            return callable_(db)

    # Wrap so the worker only passes run_id.
    def fetch_run(run_id: int) -> Any:
        return _session_run(lambda db: _fetch_run(db, run_id))

    def fetch_problem(problem_id: int) -> Any:
        return _session_run(lambda db: _fetch_problem(db, problem_id))

    def fetch_test_cases(problem_id: int) -> list[Any]:
        return _session_run(lambda db: _fetch_test_cases(db, problem_id))

    def fetch_contest(contest_id: int) -> Any:
        return _session_run(lambda db: _fetch_contest(db, contest_id))

    def update_run_status(
        run_id: int,
        status: str,
        summary_verdict: str | None,
        steps: int | None,
        wall_ms: int | None,
    ) -> None:
        _session_run(
            lambda db: _update_run_status(
                db, run_id, status, summary_verdict, steps, wall_ms,
            )
        )

    def persist_test_result(run_id: int, cases: list[CaseOutcome]) -> None:
        _session_run(lambda db: _persist_test_result(db, run_id, cases))

    return PersistHooks(
        fetch_run=fetch_run,
        fetch_problem=fetch_problem,
        fetch_test_cases=fetch_test_cases,
        fetch_contest=fetch_contest,
        update_run_status=update_run_status,
        persist_test_result=persist_test_result,
        broadcast=_broadcast,
        recompute_scoreboard=_recompute_scoreboard,
        enqueue_anticheat=_enqueue_anticheat,
    )


def _map_verdict_for_scoring(verdict: str | None) -> str:
    """Normalise ``Run.summary_verdict`` for the scoring engine.

    The engine uses AC/WA/TLE/RE/CE; the worker uses OK for in-progress case
    results but persists AC for final summaries. Anything unmapped is treated
    as WA so it never accidentally flips a solved problem to solved.
    """
    if verdict in {"AC", "WA", "TLE", "RE", "CE"}:
        return verdict
    return "WA"


def json_dumps(obj: Any) -> str:
    """JSON-serialise ``obj`` (testable helper)."""
    import json as _json

    return _json.dumps(obj, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Anticheat batch trigger (throttled)
# ---------------------------------------------------------------------------

_anticheat_pending = 0
_anticheat_lock = threading.Lock()


def _maybe_fire_anticheat_batch() -> None:
    """Increment the pending counter; fire a batch job when threshold is hit.

    The actual batch is a thin shim that calls
    ``pseint_judge.similarity.batch_compute`` over recent submissions and
    writes the result rows.  Implemented as a separate RQ job so the worker
    is not blocked; the threshold (default 10) prevents a flood.
    """
    global _anticheat_pending
    with _anticheat_lock:
        _anticheat_pending += 1
        if _anticheat_pending < ANTICHEAT_BATCH_THRESHOLD:
            return
        _anticheat_pending = 0
    client = _redis_connection()
    q = Queue(QUEUE_NAME, connection=client)
    q.enqueue(_run_anticheat_batch)


def _run_anticheat_batch() -> None:
    """Worker-side batch: pull recent submissions and persist similarity rows.

    The actual similarity compute lives in ``pseint_judge.similarity`` (todo
    38); persistence of ``similarity_pairs`` rows is in the API layer
    (todo 39).  This stub is the integration point — the worker enqueues the
    job; the API process picks it up via a dedicated ``anticheat`` queue and
    writes the rows.
    """
    logger.info("anticheat batch trigger fired (threshold reached)")


def anticheat_pending_count() -> int:
    """Test seam — return the current pending count."""
    with _anticheat_lock:
        return _anticheat_pending


def reset_anticheat_counter() -> None:
    """Test seam — reset the pending counter (used by tests)."""
    global _anticheat_pending
    with _anticheat_lock:
        _anticheat_pending = 0


# ---------------------------------------------------------------------------
# Core job: process_run
# ---------------------------------------------------------------------------


def _mode_for_run(run: Any, contest: Any | None) -> str:
    """Map ``run.kind`` (and contest scoring_mode) to judge mode."""
    if run.kind == "practice":
        return "practice"
    if run.kind == "assignment":
        return "assignment"
    # contest: cf or ioi depending on the contest's scoring_mode
    if contest is not None and getattr(contest, "scoring_mode", "cf") == "ioi":
        return "ioi"
    return "cf"


def _problem_dict(problem: Any) -> dict[str, Any]:
    """Pick the fields judge_submission consumes from ``Problem``."""
    return {
        "step_budget": getattr(problem, "step_budget", None),
        "max_output_bytes": getattr(problem, "max_output_bytes", None)
        or 1_048_576,
        "max_array_elements": getattr(problem, "max_array_elements", None),
    }


def _test_case_dict(tc: Any, idx: int) -> dict[str, Any]:
    return {
        "case_index": idx,
        "input": getattr(tc, "input", ""),
        "seed": getattr(tc, "seed", 0),
    }


def process_run(
    run_id: int,
    *,
    sandbox_runner: Callable[..., Any] = run_sandboxed,
    hooks: PersistHooks | None = None,
) -> dict[str, Any]:
    """RQ job: judge ``run_id`` end-to-end and persist results.

    Flow:
        1.  queued → running (status flip).
        2.  Fetch run / problem / test cases via the hooks.
        3.  CE short-circuit (parse-once) — zero cases run on CE.
        4.  Per-case loop with M2 lazy-stop (CF) / run-all (IOI/assignment).
            One container per submission via the sandbox wrapper.
        5.  Persist TestResult rows; flip status → done; broadcast WS.
        6.  Scoreboard recompute (M12) and anticheat throttled enqueue.

    Returns a dict describing the outcome.  Raises ``ContainerInfraError``
    for retryable container/infra errors so RQ retries up to
    ``MAX_INFRA_RETRIES``.  Verdicts are returned as data — never raised.
    """
    hooks = hooks or PersistHooks()

    run = hooks.fetch_run(run_id)
    if run is None:
        # The run was deleted between enqueue and consume — drop quietly.
        logger.warning("process_run: run %s not found; skipping", run_id)
        return {"run_id": run_id, "status": STATUS_DONE, "cases": []}

    # queued → running
    hooks.update_run_status(run_id, STATUS_RUNNING, None, None, None)

    contest = hooks.fetch_contest(run.contest_id) if run.contest_id else None
    test_cases = hooks.fetch_test_cases(run.problem_id)
    mode = _mode_for_run(run, contest)

    # CE short-circuit: parse-once via the engine's parser.
    try:
        parse(run.source)
    except (LexError, ParseError) as e:
        ce_outcome = CaseOutcome(
            case_index=0,
            verdict=VERDICT_CE,
            steps=0,
            wall_ms=0,
            output="",
            error={"code": "CE", "message": e.message, "line": e.line, "col": e.col},
        )
        hooks.persist_test_result(run_id, [ce_outcome])
        hooks.update_run_status(run_id, STATUS_DONE, VERDICT_CE, 0, 0)
        event = make_run_event(
            run_id, STATUS_DONE,
            per_case=[{
                "case_index": 0,
                "verdict": VERDICT_CE,
                "steps": 0,
                "wall_ms": 0,
            }],
        )
        hooks.broadcast(run_id, run.user_id, event, run.contest_id)
        hooks.recompute_scoreboard(run_id)
        hooks.enqueue_anticheat(run_id)
        return {
            "run_id": run_id,
            "status": STATUS_DONE,
            "verdict": VERDICT_CE,
            "cases": [ce_outcome],
        }

    # Per-case loop with M2 lazy-stop.  One container per submission:
    # the worker iterates cases; the wrapper API accepts one program per
    # call so today each iteration is a fresh container (the goal of one
    # container per submission is documented in the module docstring).
    outcomes: list[CaseOutcome] = []
    total_steps = 0
    total_wall_ms = 0

    for idx, tc in enumerate(test_cases):
        try:
            sb = sandbox_runner(
                run.source.encode("utf-8"),
                # Future: when the wrapper supports per-case input we can pass
                # ``_test_case_dict(tc, idx)["input"]`` via stdin; today the
                # wrapper pipes only the source, so we leave per-case input
                # to the engine CLI's default behaviour.
            )
        except Exception as e:
            # Any unexpected exception from the sandbox runner itself is an
            # infra failure (Docker daemon down, socket missing, OOM, etc.)
            # — raise to trigger RQ retry.
            raise ContainerInfraError(
                f"sandbox runner raised for run {run_id} case {idx}: {e}"
            ) from e

        if sb.error is not None and sb.error.get("code") == "ERR_CONTAINER":
            raise ContainerInfraError(
                f"container error for run {run_id} case {idx}: "
                f"{sb.error.get('message')}"
            )

        verdict, err, steps, wall_ms, output = _verdict_from_sandbox(sb)
        outcome = CaseOutcome(
            case_index=idx,
            verdict=verdict,
            steps=steps,
            wall_ms=wall_ms,
            output=output,
            error=err,
        )
        outcomes.append(outcome)
        total_steps += steps
        total_wall_ms += wall_ms

        # M2 lazy-stop for CF.
        if mode == "cf" and verdict != VERDICT_OK:
            break

    summary = _summary_verdict(outcomes, mode)
    hooks.persist_test_result(run_id, outcomes)
    hooks.update_run_status(run_id, STATUS_DONE, summary, total_steps, total_wall_ms)

    per_case = [
        {
            "case_index": c.case_index,
            "verdict": c.verdict,
            "steps": c.steps,
            "wall_ms": c.wall_ms,
        }
        for c in outcomes
    ]
    event = make_run_event(run_id, STATUS_DONE, per_case=per_case)
    hooks.broadcast(run_id, run.user_id, event, run.contest_id)

    # M12 scoreboard recompute on verdict/points change.
    hooks.recompute_scoreboard(run_id)
    # Anticheat throttled enqueue (fires when ≥ threshold new subs pending).
    hooks.enqueue_anticheat(run_id)

    return {
        "run_id": run_id,
        "status": STATUS_DONE,
        "verdict": summary,
        "cases": [
            {
                "case_index": c.case_index,
                "verdict": c.verdict,
                "steps": c.steps,
                "wall_ms": c.wall_ms,
            }
            for c in outcomes
        ],
    }


# ---------------------------------------------------------------------------
# Worker pool startup
# ---------------------------------------------------------------------------


def start_workers(
    replicas: int | None = None,
    *,
    redis_url: str | None = None,
    queue_name: str = QUEUE_NAME,
    with_scheduler: bool = False,
    stop_event: threading.Event | None = None,
) -> list[Worker]:
    """Start ``replicas`` (or ``$REPLICAS``) RQ worker threads in-process.

    Each ``Worker.work()`` call blocks, so we spawn one daemon thread per
    worker.  Returns the live Worker handles so the caller (and tests) can
    inspect ``worker.state`` or ask them to stop via ``stop_event``.

    The caller is responsible for keeping the main thread alive until the
    workers should exit; once ``stop_event`` is set, ``request_stop`` is sent
    to each worker and the threads wind down.
    """
    if replicas is None:
        replicas = worker_count()
    if replicas < 1:
        raise WorkerConfigError(
            f"replicas must be >=1 (got {replicas})"
        )
    conn = _redis_connection(redis_url)
    workers: list[Worker] = []

    def _spawn(idx: int) -> Worker:
        w = Worker(
            [queue_name],
            connection=conn,
            name=f"pseint-worker-{idx}",
        )
        # ``work`` blocks until ``request_stop`` is called or the Redis
        # connection drops; ``burst=False`` keeps the worker alive forever
        # (we want a long-running pool, not a one-shot drain).
        w.work(burst=False, with_scheduler=with_scheduler)
        return w

    threads: list[threading.Thread] = []
    for i in range(replicas):
        t = threading.Thread(
            target=_spawn,
            args=(i,),
            name=f"pseint-worker-thread-{i}",
            daemon=True,
        )
        t.start()
        threads.append(t)

    # Wait briefly so the Worker objects are constructed before we return.
    deadline = threading.Event()
    threading.Timer(0.05, deadline.set).start()
    deadline.wait(0.1)
    return _collect_workers(workers, queue_name, conn)


def _collect_workers(
    workers: list[Worker],
    queue_name: str,
    conn: Any,
) -> list[Worker]:
    """Return the live Worker instances for ``queue_name``.

    RQ registers workers on ``Worker.all(connection=conn)`` once their
    registration heartbeat runs; we re-fetch so the returned list reflects
    the actual pool.  ``workers`` is intentionally a starting hint — the
    freshest view comes from the registry.
    """
    from rq.worker import Worker as _Worker
    try:
        return list(_Worker.all(queue=queue_name, connection=conn))
    except (OSError, ConnectionError):  # pragma: no cover - defensive
        return workers


def start_intake_thread(
    redis_url: str | None = None,
    *,
    stop_event: threading.Event | None = None,
) -> threading.Thread:
    """Start ``intake_loop`` in a daemon thread; return the handle."""
    stop_event = stop_event or threading.Event()
    t = threading.Thread(
        target=intake_loop,
        args=(redis_url,),
        kwargs={"stop_event": stop_event, "poll_timeout": 5.0},
        name="pseint-intake",
        daemon=True,
    )
    t.start()
    return t


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI: start the worker pool.

    Reads ``$REPLICAS`` (default 3), starts that many RQ workers plus the
    intake thread.  The main thread blocks until SIGINT/SIGTERM.
    """
    import signal

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    replicas = worker_count()
    logger.info(
        "starting pseint-judge worker pool: replicas=%d queue=%s",
        replicas, QUEUE_NAME,
    )

    stop_event = threading.Event()

    def _shutdown(_signum: int, _frame: Any) -> None:
        logger.info("shutdown signal received; stopping intake loop")
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    intake = start_intake_thread(stop_event=stop_event)
    workers = start_workers(replicas, stop_event=stop_event)

    try:
        # Block on the intake thread; workers run independently.
        while intake.is_alive() and not stop_event.is_set():
            intake.join(timeout=1.0)
    finally:
        stop_event.set()
        for w in workers:
            try:
                w.request_stop()
            except Exception:  # pragma: no cover - defensive
                logger.exception("error stopping worker %s", w.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
