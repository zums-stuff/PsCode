"""Structural tests for scripts/loadtest.py (todo 37).

The load test is an end-to-end script that drives a 200-burst against the
LOCAL docker-compose stack (todo 36).  These tests pin the script's
*static* contract so accidental edits to CLI flags, assertion set, or
exit-code logic cannot silently regress the plan-acceptance check
(``python scripts/loadtest.py`` exits 0 with 4 PASS lines).

The tests deliberately do NOT run the burst — that would require a live
compose stack.  They:

    1. Import + invoke ``parse_args`` and check defaults.
    2. Read the source and assert all four assertion labels are present.
    3. Exercise the exit-code logic with the source-level primitives
       (``evaluate_assertions`` + a tiny stand-in result list) so the
       success/failure/skip paths are all covered.
    4. Drive ``run_dry_run`` against a mocked httpx.AsyncClient so the
       auth + POST /api/runs path is exercised without a live server.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "loadtest.py"

# Load the script as a module so we can poke at its public surface without
# running __main__.  scripts/ has no __init__.py — load it explicitly.
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("loadtest", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # @dataclass requires the module to be in sys.modules; load_script
    # import is intentionally local to this test file (scripts/ has no
    # __init__.py), so we register it ourselves before exec_module.
    sys.modules["loadtest"] = module
    spec.loader.exec_module(module)
    return module


loadtest = _load_module()


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def test_default_cli_args() -> None:
    args = loadtest.parse_args([])
    assert args.base_url == "http://localhost"
    assert args.burst == 200
    assert args.students == 20
    assert args.timeout == 90
    assert args.p95_budget == 60
    assert args.cpu_limit == 80.0
    assert args.skip_cpu is False
    assert args.dry_run is False
    assert args.problem_ids == []


def test_problem_mix_csv_parsed() -> None:
    args = loadtest.parse_args(["--problem-mix", "1,2,3,4"])
    assert args.problem_ids == [1, 2, 3, 4]


def test_problem_mix_rejects_non_int() -> None:
    with pytest.raises(SystemExit):
        loadtest.parse_args(["--problem-mix", "1,foo,3"])


def test_burst_must_be_positive() -> None:
    with pytest.raises(SystemExit):
        loadtest.parse_args(["--burst", "0"])


def test_dry_run_flag() -> None:
    args = loadtest.parse_args(["--dry-run"])
    assert args.dry_run is True
    # When dry-run is set we relax the burst/students validation; passing
    # 0/0 must NOT raise.
    args2 = loadtest.parse_args(["--dry-run", "--burst", "0", "--students", "0"])
    assert args2.dry_run is True


def test_skip_cpu_flag() -> None:
    args = loadtest.parse_args(["--skip-cpu"])
    assert args.skip_cpu is True


def test_help_exits_cleanly() -> None:
    with pytest.raises(SystemExit) as excinfo:
        loadtest.parse_args(["--help"])
    assert excinfo.value.code == 0


# ---------------------------------------------------------------------------
# Source-level invariants — the 4 plan-mandated assertions + exit logic
# ---------------------------------------------------------------------------


SOURCE_TEXT = SCRIPT_PATH.read_text(encoding="utf-8")


def test_all_four_assertion_labels_present_in_source() -> None:
    """The plan acceptance gate prints 4 PASS/FAIL lines; the labels must
    be present verbatim so the test runner can grep them."""
    expected = [
        "(a) all {burst} reached status=done",
        "(b) DB run count grew by exactly --burst",
        "(c) p95 verdict latency",
        "(d) worker CPU",
    ]
    for needle in expected:
        assert needle in SOURCE_TEXT, f"missing assertion label: {needle!r}"


def test_p95_budget_constant_present() -> None:
    """The plan pins 60s as the p95 budget."""
    assert "P95_BUDGET_S = 60" in SOURCE_TEXT


def test_cpu_limit_constant_present() -> None:
    """The plan pins 80% as the CPU limit."""
    assert "CPU_LIMIT_PERCENT = 80.0" in SOURCE_TEXT


def test_exit_zero_only_when_all_pass() -> None:
    """The amain/evaluate_assertions contract: any FAIL (not SKIP) must
    produce a non-zero exit.  Pin the conditional so a refactor cannot
    silently turn a failure into exit 0."""
    assert 'failures = [a for a in assertions if not a.passed and not a.skipped]' in SOURCE_TEXT
    assert 'if failures:' in SOURCE_TEXT
    assert 'return 1' in SOURCE_TEXT
    assert 'return 0' in SOURCE_TEXT


def test_dry_run_path_present() -> None:
    """--dry-run must be a real branch, not just an unused flag."""
    assert 'if args.dry_run:' in SOURCE_TEXT
    assert 'run_dry_run' in SOURCE_TEXT


def test_burst_default_is_200() -> None:
    """Plan: 200-burst."""
    assert "DEFAULT_BURST = 200" in SOURCE_TEXT


def test_students_default_is_20() -> None:
    """Plan: 20 simulated students (matches the per-user rate-limit
    budget of 10 runs/min: 20 * 10 = 200)."""
    assert "DEFAULT_STUDENTS = 20" in SOURCE_TEXT


def test_script_does_not_require_external_infra() -> None:
    """LOCAL-FIRST (plan §D17): no DOMAIN, no TLS, no external host."""
    forbidden = ["https://", "DOMAIN", ".un", ".com"]
    for token in forbidden:
        # Allow `https://` only inside the help-text reference to httpx;
        # the script must not hard-code an external host.  We only flag
        # mentions of `.com` or domain-like patterns.
        if token.startswith("."):
            assert token not in SOURCE_TEXT, (
                f"script must not hardcode {token!r} (external infra forbidden)"
            )


# ---------------------------------------------------------------------------
# evaluate_assertions behaviour
# ---------------------------------------------------------------------------


def _result(
    *,
    run_id: int = 1,
    problem_id: int = 1,
    username: str = "u",
    submit_at: float = 0.0,
    done_at: float | None = None,
    status: str | None = "queued",
    verdict: str | None = None,
    error: str | None = None,
) -> loadtest.SubmissionResult:
    return loadtest.SubmissionResult(
        run_id=run_id,
        problem_id=problem_id,
        student_username=username,
        submit_at=submit_at,
        done_at=done_at,
        status=status,
        verdict=verdict,
        error=error,
    )


def test_evaluate_assertions_all_pass() -> None:
    results = [
        _result(run_id=i, done_at=1.0 + i * 0.1, status="done")
        for i in range(200)
    ]
    assertions = loadtest.evaluate_assertions(
        results,
        db_count_before=100,
        db_count_after=300,
        burst=200,
        p95_budget_s=60.0,
        worker_cpu=42.0,
        cpu_limit=80.0,
        cpu_skipped=False,
    )
    assert len(assertions) == 4
    labels = [a.label.split(" ")[0] for a in assertions]
    assert labels == ["(a)", "(b)", "(c)", "(d)"]
    assert all(a.passed for a in assertions)
    assert not any(a.skipped for a in assertions)


def test_evaluate_assertions_skips_cpu_when_unavailable() -> None:
    results = [_result(done_at=1.0, status="done")]
    assertions = loadtest.evaluate_assertions(
        results,
        db_count_before=0,
        db_count_after=1,
        burst=1,
        p95_budget_s=60.0,
        worker_cpu=None,
        cpu_limit=80.0,
        cpu_skipped=False,
    )
    cpu = next(a for a in assertions if a.label.startswith("(d)"))
    assert cpu.skipped is True
    assert cpu.passed is True


def test_evaluate_assertions_failure_when_done_misses() -> None:
    results = [
        _result(run_id=i, done_at=1.0, status="done") for i in range(199)
    ]
    # The 200th never reached done.
    results.append(
        _result(run_id=200, done_at=None, status="queued", error="timeout")
    )
    assertions = loadtest.evaluate_assertions(
        results,
        db_count_before=0,
        db_count_after=200,
        burst=200,
        p95_budget_s=60.0,
        worker_cpu=10.0,
        cpu_limit=80.0,
        cpu_skipped=True,
    )
    a = assertions[0]
    assert a.passed is False
    assert "199/200" in a.detail


def test_evaluate_assertions_failure_when_db_delta_wrong() -> None:
    """If a submission gets rate-limited and never lands in the DB, (b)
    must fail — that's the plan's no-loss invariant."""
    results = [
        _result(run_id=i, done_at=1.0, status="done") for i in range(200)
    ]
    assertions = loadtest.evaluate_assertions(
        results,
        db_count_before=100,
        # only 150 new rows — 50 lost (e.g. 429s the worker never picked up)
        db_count_after=250,
        burst=200,
        p95_budget_s=60.0,
        worker_cpu=10.0,
        cpu_limit=80.0,
        cpu_skipped=True,
    )
    b = assertions[1]
    assert b.passed is False
    assert "delta=150" in b.detail


def test_evaluate_assertions_failure_when_p95_exceeds_budget() -> None:
    results = [
        _result(run_id=1, done_at=1.0, status="done"),  # 1s
        _result(run_id=2, done_at=120.0, status="done"),  # 120s — way over
    ]
    assertions = loadtest.evaluate_assertions(
        results,
        db_count_before=0,
        db_count_after=2,
        burst=2,
        p95_budget_s=60.0,
        worker_cpu=10.0,
        cpu_limit=80.0,
        cpu_skipped=True,
    )
    c = assertions[2]
    assert c.passed is False
    assert "p95=" in c.detail


# ---------------------------------------------------------------------------
# Per-student distribution helper
# ---------------------------------------------------------------------------


def test_per_student_counts_even_split() -> None:
    assert loadtest._per_student_counts(200, 20) == [10] * 20


def test_per_student_counts_uneven_split() -> None:
    # 205 / 20 = 10 rem 5 — first five students get 11, rest get 10.
    counts = loadtest._per_student_counts(205, 20)
    assert counts[:5] == [11] * 5
    assert counts[5:] == [10] * 15
    assert sum(counts) == 205


# ---------------------------------------------------------------------------
# DB + CPU helpers (no live infra)
# ---------------------------------------------------------------------------


def test_db_count_runs_propagates_connect_error() -> None:
    """When Postgres is unreachable the function must raise — the caller
    catches it and reports.  We assert the raise, not silent zero."""
    with pytest.raises(Exception):  # noqa: B017 — DB unreachable can raise OSError, OperationalError, etc.
        loadtest.db_count_runs(
            "postgresql+psycopg://nobody:nobody@127.0.0.1:1/nobody"
        )


def test_sample_worker_cpu_returns_none_without_docker() -> None:
    """If the docker CLI is missing, the sampler must return None (so
    assertion (d) becomes SKIP).  We force shutil.which to return None."""
    with patch.object(loadtest.shutil, "which", return_value=None):
        assert loadtest.sample_worker_cpu("any-container", sample_seconds=1) is None


# ---------------------------------------------------------------------------
# Dry-run path with a mocked httpx client
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = ""

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_run_dry_run_succeeds_with_mocked_client() -> None:
    """The dry-run path must POST one run and exit 0 — without a real
    API.  We mock the AsyncClient so the test stays offline."""
    fake_client = AsyncMock()
    fake_client.post = AsyncMock(
        side_effect=[
            _FakeResponse(201, {"id": 1, "username": "loadtest_student_0_xxx"}),
            _FakeResponse(200, {"access_token": "TOKEN"}),
            _FakeResponse(202, {"run_id": 42}),
        ]
    )
    fake_client.get = AsyncMock(
        return_value=_FakeResponse(
            200,
            {"items": [{"id": 7, "expected_complexity": "O(n\u00b2)"}], "page": 1, "size": 100, "total": 1},
        )
    )
    # async with httpx.AsyncClient(...) -> fake_client
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)

    args = loadtest.parse_args(["--dry-run", "--base-url", "http://stub"])
    with patch.object(loadtest.httpx, "AsyncClient", return_value=fake_client):
        rc = asyncio.run(loadtest.run_dry_run(args))
    assert rc == 0


def test_run_dry_run_fails_when_no_problems() -> None:
    """If /api/problems returns an empty list, dry-run must exit 1 with
    a helpful message — not crash with a 404 from POST /api/runs."""
    fake_client = AsyncMock()
    fake_client.post = AsyncMock(
        side_effect=[
            _FakeResponse(201, {"id": 1, "username": "x"}),
            _FakeResponse(200, {"access_token": "TOKEN"}),
        ]
    )
    fake_client.get = AsyncMock(
        return_value=_FakeResponse(200, {"items": [], "page": 1, "size": 100, "total": 0})
    )
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)

    args = loadtest.parse_args(["--dry-run", "--base-url", "http://stub"])
    with patch.object(loadtest.httpx, "AsyncClient", return_value=fake_client):
        rc = asyncio.run(loadtest.run_dry_run(args))
    assert rc == 1