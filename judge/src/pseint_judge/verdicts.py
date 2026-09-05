"""Verdict classification for the judge (todo 12).

Maps a runner ``CaseResult`` (engine error dict + output + steps + wall_ms)
plus the expected output, compare mode and wall-clock limit to the final
per-case verdict.  The taxonomy is EXACTLY {AC, WA, TLE, RE, CE} — no other
verdicts are ever emitted (plan §12 MUST NOT).

Priority table (highest wins)
-----------------------------
1. CE        — parse failure; produced by the runner's parse-once
               short-circuit (draft M1) and passed through unchanged.
2. TLE(step) — engine error ``ERR_STEP_LIMIT``: the program exceeded the
               problem's step budget.  Wins over comparison: a program that
               hits the step budget is TLE even if its partial output matches
               the expected output.
3. TLE(wall) — worker-side measured ``wall_ms`` exceeds the wall-clock limit.
               Wins over RE: a run that overran the wall clock is TLE even if
               it also raised a runtime error (DOMjudge wall-vs-cpu practice:
               the wall cap is a hard safety bound).
4. RE(code)  — any other engine runtime error (SPEC §(i) taxonomy:
               ERR_DIV0, ERR_TYPE, ERR_BOUNDS, ERR_DIM, ERR_RECURSION,
               ERR_EOF_INPUT, ERR_OUTPUT_CAP), carrying the error code.
               Wins over WA: an errored run is RE even if its partial output
               differs from expected.
5. WA        — output comparison mismatch (compare_outputs).
6. AC        — correct output, no error, within both budgets.

The per-case verdict record carries ``verdict``, ``steps`` and — when
relevant — the engine ``error_code`` (RE, TLE(step), CE) and the measured
``wall_ms`` (TLE(wall)).
"""

from __future__ import annotations

from dataclasses import dataclass

from pseint_judge.compare import compare_outputs
from pseint_judge.runner import CaseResult

VERDICTS = frozenset({"AC", "WA", "TLE", "RE", "CE"})


@dataclass(frozen=True)
class VerdictRecord:
    """Final per-case verdict (todo 12 contract, consumed by todo 14)."""

    verdict: str
    steps: int
    error_code: str | None = None
    wall_ms: int | None = None


def classify_case(
    case: CaseResult,
    expected: str,
    compare_mode: str = "exact",
    wall_limit_ms: int | None = None,
) -> VerdictRecord:
    """Classify one engine run into the final verdict taxonomy.

    ``wall_limit_ms=None`` disables the wall-clock check (the caller — todo 15
    wiring — supplies the problem's limit).  Wall-clock TLE fires on
    strictly-greater ``wall_ms > wall_limit_ms``, matching the engine's
    strictly-greater step-budget convention.
    """
    # 1. CE passthrough (runner parse-once short-circuit, draft M1).
    if case.verdict == "CE" or (case.error and case.error["code"] == "CE"):
        return VerdictRecord(verdict="CE", steps=case.steps, error_code="CE")

    # 2. TLE(step): engine step budget exceeded.
    if case.error and case.error["code"] == "ERR_STEP_LIMIT":
        return VerdictRecord(
            verdict="TLE", steps=case.steps, error_code="ERR_STEP_LIMIT"
        )

    # 3. TLE(wall): worker-side wall clock over the limit.
    if wall_limit_ms is not None and case.wall_ms > wall_limit_ms:
        return VerdictRecord(verdict="TLE", steps=case.steps, wall_ms=case.wall_ms)

    # 4. RE: any other engine runtime error, carrying its code.
    if case.error is not None:
        return VerdictRecord(
            verdict="RE", steps=case.steps, error_code=case.error["code"]
        )

    # 5/6. WA vs AC: output comparison.
    if compare_outputs(expected, case.output, mode=compare_mode)["equal"]:
        return VerdictRecord(verdict="AC", steps=case.steps)
    return VerdictRecord(verdict="WA", steps=case.steps)
