"""Output comparison for the judge (todo 11).

Exact mode (default): split on ``\\n``, strip ``\\r`` from each line,
``rstrip()`` each line, compare element-wise.  Leading whitespace and
blank lines are SIGNIFICANT.  A trailing ``\\n`` from the last
``Escribir`` is part of the output (SPEC §comparison, draft M5).

Token mode: split the full text on ``\\s+``, compare token sequences.
"""

from __future__ import annotations


def compare_outputs(
    expected: str, got: str, mode: str = "exact"
) -> dict:
    """Compare expected vs actual output.

    Returns a dict with keys:
    - ``equal`` (bool): True if outputs match.
    - ``first_diff_line`` (int | None): 1-based line/token index of first
      difference, or None if equal.
    - ``expected_line`` (str | None): expected content at the diff point,
      or ``""`` if expected is shorter.
    - ``got_line`` (str | None): actual content at the diff point,
      or ``""`` if got is shorter.
    """
    if mode == "token":
        return _compare_token(expected, got)
    return _compare_exact(expected, got)


def _normalize_lines(text: str) -> list[str]:
    """Split on \\n, strip \\r from each line, rstrip each line.

    Trailing blank elements from a final ``\\n`` are preserved — they are
    part of the program output (draft M5, plan §11 MUST NOT trim).
    """
    return [line.replace("\r", "").rstrip() for line in text.split("\n")]


def _compare_exact(expected: str, got: str) -> dict:
    exp_lines = _normalize_lines(expected)
    got_lines = _normalize_lines(got)

    for i in range(max(len(exp_lines), len(got_lines))):
        exp_line = exp_lines[i] if i < len(exp_lines) else None
        got_line = got_lines[i] if i < len(got_lines) else None

        if exp_line != got_line:
            return {
                "equal": False,
                "first_diff_line": i + 1,
                "expected_line": exp_line if exp_line is not None else "",
                "got_line": got_line if got_line is not None else "",
            }

    return {
        "equal": True,
        "first_diff_line": None,
        "expected_line": None,
        "got_line": None,
    }


def _compare_token(expected: str, got: str) -> dict:
    exp_tokens = expected.split()
    got_tokens = got.split()

    for i in range(max(len(exp_tokens), len(got_tokens))):
        exp_token = exp_tokens[i] if i < len(exp_tokens) else None
        got_token = got_tokens[i] if i < len(got_tokens) else None

        if exp_token != got_token:
            return {
                "equal": False,
                "first_diff_line": i + 1,
                "expected_line": exp_token if exp_token is not None else "",
                "got_line": got_token if got_token is not None else "",
            }

    return {
        "equal": True,
        "first_diff_line": None,
        "expected_line": None,
        "got_line": None,
    }
