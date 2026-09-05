"""Determinism + budgets end-to-end tests (todo 15).

Proves rejudge stability: an identical submission judged twice produces
byte-identical outputs, identical verdicts and identical step counts, for
five golden corpus programs (SPEC §(h) determinism).  Also pins the budget
constants module (source/input/output caps, wall/cpu/mem limits, practice
quota) and the per-run seed plumbing (test_case.seed -> engine --seed,
default 0).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pseint_judge.budgets import (
    CPU_LIMIT_MS,
    DEFAULT_SEED,
    MAX_INPUT_BYTES,
    MAX_OUTPUT_BYTES,
    MAX_SOURCE_BYTES,
    MEM_LIMIT_MB,
    PRACTICE_RUNS_PER_MIN,
    WALL_LIMIT_MS,
    Limits,
    effective_limits,
)
from pseint_judge.runner import SubmissionResult, judge_submission
from pseint_judge.verdicts import classify_case

CORPUS_DIR = Path(__file__).resolve().parents[2] / "engine" / "tests" / "corpus"

# Five golden corpus programs spanning the deterministic-runtime surface:
# AZAR pinning, FechaActual/HoraActual stubs, control flow, recursion and
# the Esperar/Limpiar Pantalla no-ops.
CORPUS_PROGRAMS = [
    ("azar_pinned", "azar_pinned.out", "azar_pinned.json"),
    ("rc_fecha_hora", "rc_fecha_hora.out", "rc_fecha_hora.json"),
    ("si_basico", "si_basico.out", "si_basico.json"),
    ("factorial_5", "factorial_5.out", "factorial_5.json"),
    ("esperar_limpiar", "esperar_limpiar.out", "esperar_limpiar.json"),
]

AZAR_SOURCE = """\
Proceso Aleatorio
    Escribir AZAR(100)
FinProceso
"""


def _corpus_source(name: str) -> str:
    return (CORPUS_DIR / f"{name}.psc").read_text(encoding="utf-8")


def _corpus_input(name: str) -> str:
    path = CORPUS_DIR / f"{name}.in"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _corpus_expected(out_file: str) -> str:
    return (CORPUS_DIR / out_file).read_text(encoding="utf-8")


def _corpus_steps(json_file: str) -> int:
    meta = json.loads((CORPUS_DIR / json_file).read_text(encoding="utf-8"))
    return meta["steps"]


def _fingerprint(result: SubmissionResult) -> tuple:
    """Deterministic projection of a submission result.

    wall_ms/cpu_ms are wall-clock measurements and legitimately differ
    between runs; everything else must be byte-identical on rejudge.
    """
    return (
        result.verdict,
        result.error,
        tuple(
            (case.verdict, case.steps, case.output, case.error)
            for case in result.cases
        ),
    )


class TestRejudgeStability:
    """Identical submission twice -> byte-identical outputs/verdicts/steps."""

    @pytest.mark.parametrize(
        ("name", "out_file", "json_file"), CORPUS_PROGRAMS
    )
    def test_double_run_is_byte_identical(
        self, name: str, out_file: str, json_file: str
    ) -> None:
        source = _corpus_source(name)
        test_cases = [{"input": _corpus_input(name), "seed": 0}]
        first = judge_submission(source, {}, test_cases, "ioi")
        second = judge_submission(source, {}, test_cases, "ioi")

        assert _fingerprint(first) == _fingerprint(second)
        # The judge path reproduces the corpus golden output byte-for-byte.
        assert first.cases[0].output == _corpus_expected(out_file)
        assert first.cases[0].steps == _corpus_steps(json_file)
        # Full taxonomy: correct output + no error -> AC.
        record = classify_case(first.cases[0], expected=_corpus_expected(out_file))
        assert record.verdict == "AC"
        assert record.steps == _corpus_steps(json_file)

    def test_fecha_actual_renders_fixed_stub(self) -> None:
        source = _corpus_source("rc_fecha_hora")
        result = judge_submission(
            source, {}, [{"input": "", "seed": 0}], "ioi"
        )
        output = result.cases[0].output
        assert "2026-01-01" in output
        assert "12:00:00" in output
        assert output == "m\n2026-01-01\n12:00:00\n"


class TestSeedPlumbing:
    """SPEC §(h): AZAR seeded per run via test_case.seed (default 0)."""

    def test_azar_same_seed_twice_is_identical(self) -> None:
        cases = [{"input": "", "seed": 0}]
        first = judge_submission(AZAR_SOURCE, {}, cases, "ioi")
        second = judge_submission(AZAR_SOURCE, {}, cases, "ioi")
        assert first.cases[0].output == "49\n"
        assert first.cases[0].output == second.cases[0].output

    def test_azar_different_seeds_differ(self) -> None:
        seed0 = judge_submission(
            AZAR_SOURCE, {}, [{"input": "", "seed": 0}], "ioi"
        )
        seed1 = judge_submission(
            AZAR_SOURCE, {}, [{"input": "", "seed": 1}], "ioi"
        )
        assert seed0.cases[0].output == "49\n"
        assert seed1.cases[0].output == "17\n"
        assert seed0.cases[0].output != seed1.cases[0].output

    def test_missing_seed_defaults_to_zero(self) -> None:
        # Contest/assignment runs default to seed 0 (runner: tc.get("seed", 0));
        # a test case without a seed key behaves exactly like seed=0.
        no_seed = judge_submission(AZAR_SOURCE, {}, [{"input": ""}], "ioi")
        seed0 = judge_submission(
            AZAR_SOURCE, {}, [{"input": "", "seed": 0}], "ioi"
        )
        assert no_seed.cases[0].output == seed0.cases[0].output == "49\n"
        assert DEFAULT_SEED == 0


class TestBudgetConstants:
    """budgets module: defaults, per-problem overrides, practice quota."""

    def test_effective_limits_defaults(self) -> None:
        limits = effective_limits()
        assert limits.max_source_bytes == 65_536
        assert limits.max_input_bytes == 65_536
        assert limits.max_output_bytes == 1_048_576
        assert limits.wall_limit_ms == 5_000
        assert limits.cpu_limit_ms == 3_000
        assert limits.mem_limit_mb == 128

    def test_module_constants_match_defaults(self) -> None:
        assert MAX_SOURCE_BYTES == 65_536
        assert MAX_INPUT_BYTES == 65_536
        assert MAX_OUTPUT_BYTES == 1_048_576
        assert WALL_LIMIT_MS == 5_000
        assert CPU_LIMIT_MS == 3_000
        assert MEM_LIMIT_MB == 128

    def test_effective_limits_none_and_empty_are_defaults(self) -> None:
        assert effective_limits(None) == Limits()
        assert effective_limits({}) == Limits()

    def test_per_problem_override_wins(self) -> None:
        limits = effective_limits(
            {"max_output_bytes": 2_097_152, "wall_limit_ms": 10_000}
        )
        assert limits.max_output_bytes == 2_097_152
        assert limits.wall_limit_ms == 10_000
        # Unoverridden fields keep their defaults.
        assert limits.max_source_bytes == MAX_SOURCE_BYTES
        assert limits.max_input_bytes == MAX_INPUT_BYTES
        assert limits.cpu_limit_ms == CPU_LIMIT_MS
        assert limits.mem_limit_mb == MEM_LIMIT_MB

    def test_unknown_problem_keys_are_ignored(self) -> None:
        # step_budget is handled by the runner/complexity modules, not Limits.
        limits = effective_limits({"step_budget": 500, "bogus": 1})
        assert limits == Limits()

    def test_practice_quota_constant(self) -> None:
        assert PRACTICE_RUNS_PER_MIN == 10
