"""Tests for pseint_judge.complexity — complexity bands (todo 13).

TDD suite asserting EXACT integers from the SPEC §(k) NORMATIVE coefficient
table, band boundaries, the hard step budget, and n_estimate.  The band is a
SIGNALED metric only — it never changes the verdict (correctness first).
"""

from __future__ import annotations

import pytest

from pseint_judge.complexity import (
    band,
    expected_steps,
    hard_step_budget,
    n_estimate,
)


class TestExpectedSteps:
    """FORMULA(complexity, n) — EXACT integers from the SPEC §(k) table."""

    def test_o1_is_constant_50(self) -> None:
        assert expected_steps("O(1)", 10) == 50
        assert expected_steps("O(1)", 0) == 50

    def test_on_n10_is_250(self) -> None:
        assert expected_steps("O(n)", 10) == 250  # 20*10 + 50

    def test_on2_n10_is_550(self) -> None:
        assert expected_steps("O(n²)", 10) == 550  # 5*100 + 50

    def test_o2n_n3_is_128(self) -> None:
        assert expected_steps("O(2ⁿ)", 3) == 128  # 2^(3+4)

    def test_ologn_n6_is_150(self) -> None:
        # 50 * floor(log2(6+2)) = 50 * floor(log2(8)) = 50 * 3 = 150
        assert expected_steps("O(log n)", 6) == 150

    def test_onnlogn_n6_is_410(self) -> None:
        # 20*6*floor(log2(8)) + 50 = 20*6*3 + 50 = 410
        assert expected_steps("O(n log n)", 6) == 410

    def test_on3_n5_is_300(self) -> None:
        assert expected_steps("O(n³)", 5) == 300  # 2*125 + 50

    def test_other_without_step_budget_raises(self) -> None:
        with pytest.raises(ValueError):
            expected_steps("other", 10)


class TestBand:
    """Band classification: OK < 1.5, ALTA < 4, EXCESIVA else."""

    def test_ratio_1_is_ok(self) -> None:
        assert band(100, 100) == "OK"

    def test_ratio_1_5_is_alta_not_ok(self) -> None:
        assert band(150, 100) == "ALTA"

    def test_ratio_4_is_excesiva_not_alta(self) -> None:
        assert band(400, 100) == "EXCESIVA"

    def test_ratio_below_1_5_is_ok(self) -> None:
        assert band(149, 100) == "OK"

    def test_ratio_between_1_5_and_4_is_alta(self) -> None:
        assert band(399, 100) == "ALTA"

    def test_ratio_above_4_is_excesiva(self) -> None:
        assert band(401, 100) == "EXCESIVA"


class TestHardStepBudget:
    """2*expected + 1000 by default; problem.step_budget overrides."""

    def test_default_is_2x_plus_1000(self) -> None:
        assert hard_step_budget(100) == 1200

    def test_override_wins(self) -> None:
        assert hard_step_budget(100, problem_step_budget=500) == 500


class TestNEstimate:
    """Whitespace-token count of the input (SPEC §k)."""

    def test_counts_whitespace_tokens(self) -> None:
        assert n_estimate("1 2 3\n") == 3

    def test_empty_input_is_zero(self) -> None:
        assert n_estimate("") == 0

    def test_multiline_and_extra_whitespace(self) -> None:
        assert n_estimate("1  2\n3 4\n") == 4


class TestPlantedBubbleVsMerge:
    """Planted bubble (O(n²)) vs merge (O(n log n)) on n=500."""

    def test_expected_steps_differ_by_right_factor(self) -> None:
        n = 500
        bubble = expected_steps("O(n²)", n)  # 5*250000 + 50 = 1250050
        merge = expected_steps("O(n log n)", n)  # 20*500*floor(log2(502)) + 50
        assert bubble == 1_250_050
        assert merge == 80_050  # 20*500*8 + 50
        assert bubble / merge > 15  # ~15.6x

    def test_bubble_impl_band_separates_by_expected_complexity(self) -> None:
        # A bubble implementation running ~1.3M steps on n=500.
        steps = 1_300_000
        n = 500
        # Against O(n²) expectation it is OK (ratio ~1.04 < 1.5).
        assert band(steps, expected_steps("O(n²)", n)) == "OK"
        # Against O(n log n) expectation it is EXCESIVA (ratio ~16 > 4).
        assert band(steps, expected_steps("O(n log n)", n)) == "EXCESIVA"
