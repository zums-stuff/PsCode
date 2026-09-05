"""Tests for pseint_judge.verdicts — verdict classification (todo 12).

TDD suite: one test per taxonomy row plus priority conflicts, per the plan
acceptance criteria.  The taxonomy is EXACTLY {AC, WA, TLE, RE, CE} and the
priority table (highest wins) is CE > TLE(step) > TLE(wall) > RE > WA > AC.
"""

from __future__ import annotations

from pseint_judge.runner import CaseResult
from pseint_judge.verdicts import VERDICTS, VerdictRecord, classify_case


def _case(
    *,
    verdict: str = "OK",
    steps: int = 10,
    wall_ms: int = 5,
    output: str = "",
    error: dict | None = None,
) -> CaseResult:
    return CaseResult(
        verdict=verdict,
        steps=steps,
        wall_ms=wall_ms,
        cpu_ms=0,
        output=output,
        error=error,
    )


def _err(code: str) -> dict:
    return {"code": code, "message": "boom", "line": 3, "col": 7}


class TestTaxonomyRows:
    """One test per taxonomy row."""

    def test_correct_output_no_error_is_ac_with_steps(self) -> None:
        case = _case(steps=42, output="5\n")
        rec = classify_case(case, expected="5\n")
        assert rec.verdict == "AC"
        assert rec.steps == 42
        assert rec.error_code is None
        assert rec.wall_ms is None

    def test_wrong_output_no_error_is_wa(self) -> None:
        case = _case(steps=7, output="6\n")
        rec = classify_case(case, expected="5\n")
        assert rec.verdict == "WA"
        assert rec.steps == 7

    def test_step_limit_is_tle_even_when_output_matches(self) -> None:
        case = _case(steps=1001, output="5\n", error=_err("ERR_STEP_LIMIT"))
        rec = classify_case(case, expected="5\n")
        assert rec.verdict == "TLE"
        assert rec.error_code == "ERR_STEP_LIMIT"
        assert rec.steps == 1001

    def test_wall_clock_over_limit_is_tle_even_when_output_correct(self) -> None:
        case = _case(steps=3, wall_ms=6000, output="5\n")
        rec = classify_case(case, expected="5\n", wall_limit_ms=5000)
        assert rec.verdict == "TLE"
        assert rec.wall_ms == 6000

    def test_div0_with_wrong_output_is_re_not_wa(self) -> None:
        case = _case(steps=4, output="6\n", error=_err("ERR_DIV0"))
        rec = classify_case(case, expected="5\n")
        assert rec.verdict == "RE"
        assert rec.error_code == "ERR_DIV0"

    def test_type_error_is_re_with_code(self) -> None:
        case = _case(steps=2, output="", error=_err("ERR_TYPE"))
        rec = classify_case(case, expected="")
        assert rec.verdict == "RE"
        assert rec.error_code == "ERR_TYPE"

    def test_ce_passthrough_from_runner(self) -> None:
        case = _case(
            verdict="CE",
            steps=0,
            error={"code": "CE", "message": "syntax", "line": 1, "col": 1},
        )
        rec = classify_case(case, expected="")
        assert rec.verdict == "CE"
        assert rec.error_code == "CE"


class TestPriorityConflicts:
    """Priority table: CE > TLE(step) > TLE(wall) > RE > WA > AC."""

    def test_step_limit_beats_comparison(self) -> None:
        case = _case(steps=1001, output="5\n", error=_err("ERR_STEP_LIMIT"))
        rec = classify_case(case, expected="5\n")
        assert rec.verdict == "TLE"  # not AC despite matching output

    def test_re_beats_wa(self) -> None:
        case = _case(steps=4, output="6\n", error=_err("ERR_DIV0"))
        rec = classify_case(case, expected="5\n")
        assert rec.verdict == "RE"  # not WA despite wrong output

    def test_wall_tle_beats_re(self) -> None:
        case = _case(steps=4, wall_ms=6000, output="", error=_err("ERR_DIV0"))
        rec = classify_case(case, expected="", wall_limit_ms=5000)
        assert rec.verdict == "TLE"
        assert rec.wall_ms == 6000

    def test_step_tle_beats_wall_tle(self) -> None:
        case = _case(steps=1001, wall_ms=6000, error=_err("ERR_STEP_LIMIT"))
        rec = classify_case(case, expected="", wall_limit_ms=5000)
        assert rec.verdict == "TLE"
        assert rec.error_code == "ERR_STEP_LIMIT"


class TestTaxonomyClosed:
    """No verdicts outside {AC, WA, TLE, RE, CE}."""

    def test_verdict_set_is_exactly_the_taxonomy(self) -> None:
        assert VERDICTS == {"AC", "WA", "TLE", "RE", "CE"}

    def test_wall_limit_none_means_no_wall_check(self) -> None:
        case = _case(steps=3, wall_ms=6000, output="5\n")
        rec = classify_case(case, expected="5\n")  # no wall_limit_ms passed
        assert rec.verdict == "AC"