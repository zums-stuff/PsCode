"""Complexity bands for the judge (todo 13).

Computes, per test case, the expected step count from the SPEC §(k) NORMATIVE
coefficient table, classifies the measured steps into a band (OK/ALTA/EXCESIVA),
and derives the hard step budget that feeds the TLE(step) path (todo 12's
``ERR_STEP_LIMIT``).

The band is a SIGNALED metric only — it NEVER changes the verdict.  Correctness
comes first: a submission with a high band (e.g. EXCESIVA) still gets AC if its
output is correct and it stays within the hard step budget.  The band is
consumed by todo 14 (scoring) as a quality signal, not by the verdict classifier.

COEFFICIENT TABLE (NORMATIVE — single source of truth, SPEC §(k))
------------------------------------------------------------------
| Complexity | Formula                    | Example (n=10) |
|------------|----------------------------|----------------|
| O(1)       | 50                         | 50             |
| O(log n)   | 50 · log2(n + 2)           | ≈ 195          |
| O(n)       | 20n + 50                   | 250            |
| O(n log n) | 20n · log2(n + 2) + 50     | ≈ 2050         |
| O(n²)      | 5n² + 50                   | 550            |
| O(n³)      | 2n³ + 50                   | 2050           |
| O(2ⁿ)      | 2^(n+4)                    | 16384          |
| other      | step_budget REQUIRED       | —              |

Notes:
- ``log2`` is base-2, FLOORED to an integer (math.floor).
- ``other`` has NO auto formula: the caller MUST supply ``problem.step_budget``.
  ``expected_steps`` raises ``ValueError`` for ``other``; the caller (todo 15
  wiring) is responsible for supplying the override in that case.
- Band: OK if steps/expected < 1.5; ALTA if < 4.0; EXCESIVA otherwise.
- Hard step budget: 2*expected + 1000 by default, or ``problem.step_budget``
  override.  This is the TLE(step) threshold (SPEC §(i) ERR_STEP_LIMIT).
"""

from __future__ import annotations

import math

# NORMATIVE coefficient table (SPEC §(k)).  Keys are the exact enum values.
_COMPLEXITY_FORMULAS = frozenset(
    {"O(1)", "O(log n)", "O(n)", "O(n log n)", "O(n²)", "O(n³)", "O(2ⁿ)", "other"}
)

# Band thresholds (SPEC §(k)).
_OK_RATIO = 1.5
_ALTA_RATIO = 4.0

# Hard step budget default (SPEC §(k)): 2*expected + 1000.
_BUDGET_MULTIPLIER = 2
_BUDGET_PADDING = 1000


def expected_steps(complexity: str, n_estimate: int) -> int:
    """Expected step count for ``complexity`` at input size ``n_estimate``.

    Uses the NORMATIVE SPEC §(k) coefficient table with EXACT integer results.
    Logs are floored to an integer (``math.floor``).

    Raises ``ValueError`` for ``"other"`` — that complexity has no auto formula
    and the caller MUST supply ``problem.step_budget`` instead.
    """
    if complexity == "O(1)":
        return 50
    if complexity == "O(log n)":
        return 50 * math.floor(math.log2(n_estimate + 2))
    if complexity == "O(n)":
        return 20 * n_estimate + 50
    if complexity == "O(n log n)":
        return 20 * n_estimate * math.floor(math.log2(n_estimate + 2)) + 50
    if complexity == "O(n²)":
        return 5 * n_estimate * n_estimate + 50
    if complexity == "O(n³)":
        return 2 * n_estimate**3 + 50
    if complexity == "O(2ⁿ)":
        return 2 ** (n_estimate + 4)
    if complexity == "other":
        raise ValueError(
            "complexity 'other' has no auto formula: problem.step_budget is "
            "REQUIRED"
        )
    raise ValueError(f"unknown complexity: {complexity!r}")


def band(steps: int, expected: int) -> str:
    """Classify ``steps`` against ``expected`` into OK/ALTA/EXCESIVA.

    ratio = steps / expected
    - OK       if ratio < 1.5
    - ALTA     if 1.5 <= ratio < 4.0
    - EXCESIVA otherwise (ratio >= 4.0)

    The band is a SIGNALED metric only — it never changes the verdict.
    """
    ratio = steps / expected
    if ratio < _OK_RATIO:
        return "OK"
    if ratio < _ALTA_RATIO:
        return "ALTA"
    return "EXCESIVA"


def hard_step_budget(
    expected: int, problem_step_budget: int | None = None
) -> int:
    """Hard TLE(step) threshold for a case with ``expected`` steps.

    Default: 2*expected + 1000 (SPEC §(k)).  When ``problem_step_budget`` is
    provided it overrides the formula entirely.  This is the cap that feeds
    todo 12's ``ERR_STEP_LIMIT`` path — exceeding it is TLE regardless of band.
    """
    if problem_step_budget is not None:
        return problem_step_budget
    return _BUDGET_MULTIPLIER * expected + _BUDGET_PADDING


def n_estimate(input_text: str) -> int:
    """Estimate the input size as its whitespace-token count (SPEC §k).

    ``len(input_text.split())`` — empty input yields 0.
    """
    return len(input_text.split())
