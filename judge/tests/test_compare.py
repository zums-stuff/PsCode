"""Tests for pseint_judge.compare — output comparison (todo 11).

TDD suite covering exact mode (default) and token mode per SPEC §comparison
and draft M5 decision.  All 10 cases are pinned by the plan QA scenarios.
"""

from __future__ import annotations

import pytest

from pseint_judge.compare import compare_outputs


# ---------------------------------------------------------------------------
# Exact mode (default) — split \n, strip \r, rstrip, line-by-line
# ---------------------------------------------------------------------------


class TestExactMode:
    """Exact-line comparison: split \\n, strip \\r, rstrip each line."""

    def test_exact_match_passes(self) -> None:
        result = compare_outputs("hello\n", "hello\n")
        assert result["equal"] is True
        assert result["first_diff_line"] is None

    def test_trailing_newline_is_significant(self) -> None:
        """Expected '5\\n' vs got '5' → NOT equal (draft M5 pinned)."""
        result = compare_outputs("5\n", "5")
        assert result["equal"] is False
        assert result["first_diff_line"] == 2  # 1-based; extra blank line
        assert result["expected_line"] == ""  # the trailing empty element
        assert result["got_line"] == ""  # missing side → ""

    def test_crlf_stripped(self) -> None:
        """CRLF in got is normalised: \\r\\n → \\n after \\r strip."""
        result = compare_outputs("a\nb\n", "a\r\nb\r\n")
        assert result["equal"] is True

    def test_trailing_spaces_stripped(self) -> None:
        """Trailing whitespace on each line is rstripped."""
        result = compare_outputs("a  \nb\n", "a\nb\n")
        assert result["equal"] is True

    def test_leading_whitespace_significant(self) -> None:
        """Leading spaces are NOT stripped — they are significant."""
        result = compare_outputs("  a\n", "a\n")
        assert result["equal"] is False
        assert result["first_diff_line"] == 1
        assert result["expected_line"] == "  a"
        assert result["got_line"] == "a"

    def test_blank_line_significant(self) -> None:
        """A blank line in expected must match a blank line in got."""
        result = compare_outputs("a\n\nb\n", "a\nb\n")
        assert result["equal"] is False
        assert result["first_diff_line"] == 2  # the blank line is line 2

    def test_multi_line_diff_first_line(self) -> None:
        """first_diff_line points at the correct 1-based line."""
        result = compare_outputs("a\nb\nc\n", "x\nb\nc\n")
        assert result["equal"] is False
        assert result["first_diff_line"] == 1
        assert result["expected_line"] == "a"
        assert result["got_line"] == "x"

    def test_empty_expected_vs_nonempty_got(self) -> None:
        """Empty expected vs non-empty got → not equal."""
        result = compare_outputs("", "hello\n")
        assert result["equal"] is False
        assert result["first_diff_line"] == 1
        assert result["expected_line"] == ""
        assert result["got_line"] == "hello"


# ---------------------------------------------------------------------------
# Token mode — split \s+, compare token sequences
# ---------------------------------------------------------------------------


class TestTokenMode:
    """Token comparison: whitespace-split, compare sequences."""

    def test_token_mode_equal(self) -> None:
        """Whitespace variation + newlines collapse to same token list."""
        result = compare_outputs("1  2\n3\n", "1 2 3\n", mode="token")
        assert result["equal"] is True
        assert result["first_diff_line"] is None

    def test_token_mode_mismatch(self) -> None:
        """Mismatched tokens → not equal; first_diff_line = 1-based token index."""
        result = compare_outputs("1 2 3\n", "1 2 4\n", mode="token")
        assert result["equal"] is False
        assert result["first_diff_line"] == 3  # third token differs
        assert result["expected_line"] == "3"
        assert result["got_line"] == "4"
