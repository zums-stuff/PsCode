"""Tests for the submission runner (todo 10).

Covers the M1 CE short-circuit (no subprocess on parse failure), the M2 lazy
rules per mode, per-case seeding, the happy path, and provisional error-based
verdicts (RE/TLE).
"""

from __future__ import annotations

import pytest

from pseint_judge.runner import CaseResult, judge_submission

DIV_SOURCE = """\
Proceso Div
    Definir n Como Entero
    Leer n
    Escribir 10 / n
FinProceso
"""

AZAR_SOURCE = """\
Proceso Aleatorio
    Escribir AZAR(100)
FinProceso
"""

SUM_SOURCE = """\
Proceso Suma
    Definir a, b Como Entero
    Leer a, b
    Escribir a + b
FinProceso
"""

INF_SOURCE = """\
Proceso Inf
    Mientras Verdadero Hacer
    FinMientras
FinProceso
"""

CE_SOURCE = 'Proceso P\n    Escribir "hola\nFinProceso\n'

DIV_CASES = [
    {"input": "2\n", "seed": 0},
    {"input": "0\n", "seed": 0},
    {"input": "5\n", "seed": 0},
]


def _spy_run_case(calls: list) -> None:
    """Monkeypatch _run_case with a recorder that never spawns a subprocess."""

    def fake_run_case(*args, **kwargs) -> CaseResult:
        calls.append((args, kwargs))
        return CaseResult(verdict="OK", steps=0, wall_ms=0, cpu_ms=0, output="")

    return fake_run_case


def test_ce_short_circuits_with_zero_subprocesses(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(
        "pseint_judge.runner._run_case", _spy_run_case(calls)
    )
    result = judge_submission(CE_SOURCE, {}, DIV_CASES, "cf")
    assert result.verdict == "CE"
    assert result.cases == []
    assert result.error is not None
    assert result.error["code"] == "CE"
    assert result.error["line"] == 2
    assert calls == []


def test_cf_mode_stops_at_first_non_ok() -> None:
    result = judge_submission(DIV_SOURCE, {}, DIV_CASES, "cf")
    assert len(result.cases) == 2
    assert [c.verdict for c in result.cases] == ["OK", "RE"]
    assert result.verdict == "RE"


def test_ioi_mode_runs_all_cases() -> None:
    result = judge_submission(DIV_SOURCE, {}, DIV_CASES, "ioi")
    assert len(result.cases) == 3
    assert [c.verdict for c in result.cases] == ["OK", "RE", "OK"]
    assert result.verdict == "RE"


def test_assignment_mode_runs_all_cases() -> None:
    result = judge_submission(DIV_SOURCE, {}, DIV_CASES, "assignment")
    assert len(result.cases) == 3
    assert [c.verdict for c in result.cases] == ["OK", "RE", "OK"]
    assert result.verdict == "RE"


def test_practice_mode_single_run_no_grading() -> None:
    result = judge_submission(DIV_SOURCE, {"input": "2\n"}, [], "practice")
    assert result.verdict == "OK"
    assert result.cases == []
    assert result.output == "5.0\n"


def test_per_case_seeding_is_visible() -> None:
    cases = [{"input": "", "seed": 0}, {"input": "", "seed": 1}]
    result = judge_submission(AZAR_SOURCE, {}, cases, "ioi")
    assert len(result.cases) == 2
    assert result.cases[0].output == "49\n"
    assert result.cases[1].output == "17\n"
    assert result.cases[0].output != result.cases[1].output


def test_happy_path_all_ok_with_timing() -> None:
    cases = [{"input": "2 3\n", "seed": 0}, {"input": "10 20\n", "seed": 0}]
    result = judge_submission(SUM_SOURCE, {}, cases, "ioi")
    assert result.verdict == "OK"
    assert len(result.cases) == 2
    for case in result.cases:
        assert case.verdict == "OK"
        assert case.steps > 0
        assert case.wall_ms > 0
        assert case.cpu_ms > 0
    assert result.cases[0].output == "5\n"
    assert result.cases[1].output == "30\n"


def test_engine_re_div0_maps_to_re_with_error_code() -> None:
    result = judge_submission(DIV_SOURCE, {}, [{"input": "0\n", "seed": 0}], "ioi")
    assert len(result.cases) == 1
    case = result.cases[0]
    assert case.verdict == "RE"
    assert case.error is not None
    assert case.error["code"] == "ERR_DIV0"
    assert result.verdict == "RE"


def test_step_limit_maps_to_tle() -> None:
    result = judge_submission(
        INF_SOURCE, {"step_budget": 1000}, [{"input": "", "seed": 0}], "ioi"
    )
    assert len(result.cases) == 1
    assert result.cases[0].verdict == "TLE"
    assert result.cases[0].error is not None
    assert result.cases[0].error["code"] == "ERR_STEP_LIMIT"
    assert result.verdict == "TLE"


def test_unknown_mode_raises_value_error() -> None:
    with pytest.raises(ValueError):
        judge_submission(DIV_SOURCE, {}, DIV_CASES, "bogus")