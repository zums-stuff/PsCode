"""Submission runner: parse-once, run-N (todo 10).

Consumes the engine CLI contract (todo 7)::

    python -m pseint_engine.cli run <source.psc> [--input FILE] [--seed N]
        [--step-budget N] [--max-output-bytes N] [--max-array-elements N]
        [--report FILE]

Exit codes 0/1/2/3/4; report JSON ``{steps, error: {code,message,line,col}|null,
exit_ok, output_bytes}``.

Design (M1/M2 from the draft):

* Parse ONCE via ``pseint_engine.parser.parse``. On LexError/ParseError the
  submission is a CE and ZERO test cases run (M1) — no subprocess is spawned.
* Each test case runs in its own engine subprocess with a per-case seed and
  the problem's budgets (M2 lazy rules enforced in-container).
* Provisional verdicts are error-based only (the full comparison-based
  taxonomy lands in todo 12): no error -> "OK", ERR_STEP_LIMIT -> "TLE",
  any other error -> "RE".
* Lazy rules (M2): mode "cf" stops at the first non-OK case; modes "ioi" and
  "assignment" run ALL cases; mode "practice" is a single run with the user's
  input and no grading.
"""

from __future__ import annotations

import json
import os
import resource
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field

from pseint_engine.lexer import LexError
from pseint_engine.parser import ParseError, parse

_DEFAULT_OUTPUT_CAP = 1_048_576  # 1 MB — matches the engine CLI default (M13)

_MODES = ("cf", "ioi", "assignment", "practice")


@dataclass
class CaseResult:
    """Raw outcome of one engine subprocess run (provisional verdict)."""

    verdict: str
    steps: int
    wall_ms: int
    cpu_ms: int
    output: str
    error: dict | None = None


@dataclass
class SubmissionResult:
    """Outcome of judging one submission (provisional overall verdict)."""

    verdict: str
    cases: list[CaseResult] = field(default_factory=list)
    error: dict | None = None
    output: str | None = None


def _ce_record(err: LexError | ParseError) -> dict:
    return {
        "code": "CE",
        "message": err.message,
        "line": err.line,
        "col": err.col,
    }


def _provisional_verdict(error: dict | None) -> str:
    if error is None:
        return "OK"
    if error["code"] == "ERR_STEP_LIMIT":
        return "TLE"
    return "RE"


def _run_case(
    source_path: str,
    input_text: str,
    *,
    seed: int,
    step_budget: int | None,
    max_output_bytes: int,
    max_array_elements: int | None,
) -> CaseResult:
    """Run one test case in an engine subprocess and collect raw data."""
    with tempfile.NamedTemporaryFile(
        "w", suffix=".txt", encoding="utf-8", delete=False
    ) as f:
        f.write(input_text)
        input_path = f.name
    report_fd, report_path = tempfile.mkstemp(suffix=".json")
    os.close(report_fd)
    try:
        cmd = [
            sys.executable,
            "-m",
            "pseint_engine.cli",
            "run",
            source_path,
            "--input",
            input_path,
            "--seed",
            str(seed),
            "--report",
            report_path,
        ]
        if step_budget is not None:
            cmd += ["--step-budget", str(step_budget)]
        cmd += ["--max-output-bytes", str(max_output_bytes)]
        if max_array_elements is not None:
            cmd += ["--max-array-elements", str(max_array_elements)]

        cpu_before = resource.getrusage(resource.RUSAGE_CHILDREN)
        wall_start = time.monotonic()
        proc = subprocess.run(cmd, capture_output=True, text=True)
        wall_ms = int((time.monotonic() - wall_start) * 1000)
        cpu_after = resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu_ms = int(
            (
                cpu_after.ru_utime
                + cpu_after.ru_stime
                - cpu_before.ru_utime
                - cpu_before.ru_stime
            )
            * 1000
        )

        try:
            with open(report_path, encoding="utf-8") as f:
                report = json.load(f)
        except (OSError, json.JSONDecodeError):
            report = {
                "steps": 0,
                "error": {
                    "code": "ERR_INTERNAL",
                    "message": "engine subprocess crashed without a report",
                    "line": None,
                    "col": None,
                },
                "exit_ok": False,
                "output_bytes": 0,
            }

        error = report.get("error")
        return CaseResult(
            verdict=_provisional_verdict(error),
            steps=report.get("steps", 0),
            wall_ms=wall_ms,
            cpu_ms=cpu_ms,
            output=proc.stdout,
            error=error,
        )
    finally:
        os.unlink(input_path)
        os.unlink(report_path)


def judge_submission(
    source: str,
    problem: dict,
    test_cases: list[dict],
    mode: str,
) -> SubmissionResult:
    """Judge one submission: parse once, then run each test case.

    ``problem`` may carry ``step_budget``, ``max_output_bytes`` and
    ``max_array_elements``; a test case may override ``step_budget`` per case.
    Each test case carries ``input`` (str) and ``seed`` (int, default 0).
    In practice mode the user input comes from ``problem["input"]``.
    """
    if mode not in _MODES:
        raise ValueError(f"unknown mode {mode!r}; expected one of {_MODES}")

    try:
        parse(source)
    except (LexError, ParseError) as e:
        return SubmissionResult(verdict="CE", error=_ce_record(e))

    step_budget = problem.get("step_budget")
    max_output_bytes = problem.get("max_output_bytes", _DEFAULT_OUTPUT_CAP)
    max_array_elements = problem.get("max_array_elements")

    with tempfile.NamedTemporaryFile(
        "w", suffix=".psc", encoding="utf-8", delete=False
    ) as f:
        f.write(source)
        source_path = f.name
    try:
        if mode == "practice":
            result = _run_case(
                source_path,
                problem.get("input", ""),
                seed=problem.get("seed", 0),
                step_budget=step_budget,
                max_output_bytes=max_output_bytes,
                max_array_elements=max_array_elements,
            )
            return SubmissionResult(
                verdict=result.verdict, output=result.output, error=result.error
            )

        cases: list[CaseResult] = []
        for tc in test_cases:
            result = _run_case(
                source_path,
                tc.get("input", ""),
                seed=tc.get("seed", 0),
                step_budget=tc.get("step_budget", step_budget),
                max_output_bytes=max_output_bytes,
                max_array_elements=max_array_elements,
            )
            cases.append(result)
            if mode == "cf" and result.verdict != "OK":
                break
    finally:
        os.unlink(source_path)

    non_ok = [c.verdict for c in cases if c.verdict != "OK"]
    overall = "OK" if not non_ok else non_ok[0]
    return SubmissionResult(verdict=overall, cases=cases)
