"""Golden corpus harness (todo 8).

Discovers ``engine/tests/corpus/*.psc``, runs each case through the engine
via :func:`pseint_engine.evaluator.evaluate`, and asserts:

- stdout is **byte-exact** vs the ``.out`` file (a single trailing space
  mutation fails the case — this is the byte-exactness QA scenario), and
- the report matches the ``.json`` file: ``steps`` (exact int or a
  ``{"min": X, "max": Y}`` range) and ``error`` (``null`` or
  ``{"code": "ERR_..."}``).

The corpus is the TDD-lock anchor (SPEC.md): any dialect change requires a
golden corpus case first, and the corpus must stay green. Every case's
``.psc`` carries a one-line comment linking it to its SPEC section.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pseint_engine.evaluator import evaluate
from pseint_engine.parser import parse

CORPUS_DIR = Path(__file__).parent / "corpus"

# Per-case engine kwargs (hard limits for the negative cases).
CASE_KWARGS: dict[str, dict] = {
    "neg_step_limit": {"step_budget": 5},
    "neg_output_cap": {"output_cap": 100},
}

# Category classification for the coverage summary. A case may belong to
# multiple categories; the summary counts per category.
CATEGORIES: dict[str, set[str]] = {
    "control-structures": {
        "si_basico",
        "si_sino",
        "segun_default",
        "mientras_basico",
        "repetir_basico",
        "para_basico",
        "para_con_paso",
        "hacer_mientras",
    },
    "arrays": {"dimension_1d", "matriz_2d", "redimensionar_ok"},
    "recursion": {"factorial_5"},
    "builtins": {
        "azar_pinned",
        "rc_fecha_hora",
        "abs_ln_exp",
        "sen_cos_atan",
        "trunc_redon_largo",
        "subcadena_concat",
    },
    "formatting": {
        "formato_int_real",
        "formato_saltar",
        "formato_bool_str",
        "formato_multiarg_nosep",
    },
    "synonyms": {
        "synonym_sino",
        "synonym_hacer_mientras",
        "synonym_dimensionar",
    },
    "negative": {
        "neg_div0",
        "neg_type_error",
        "neg_bounds",
        "neg_eof_input",
        "neg_recursion_cap",
        "neg_step_limit",
        "neg_output_cap",
    },
}


def _discover_cases() -> list[str]:
    """Return sorted case names (deterministic order)."""
    return sorted(p.stem for p in CORPUS_DIR.glob("*.psc"))


def _load_case(name: str) -> tuple[str, str, str, dict]:
    psc = (CORPUS_DIR / f"{name}.psc").read_text()
    input_text = (CORPUS_DIR / f"{name}.in").read_text()
    expected_out = (CORPUS_DIR / f"{name}.out").read_text()
    expected_report = json.loads((CORPUS_DIR / f"{name}.json").read_text())
    return psc, input_text, expected_out, expected_report


def _check_report(actual, expected: dict, name: str) -> None:
    """Assert the report fields match: steps exact-or-range, error code."""
    exp_steps = expected["steps"]
    if isinstance(exp_steps, int):
        assert actual.steps == exp_steps, (
            f"[{name}] steps: expected {exp_steps}, got {actual.steps}"
        )
    else:
        assert exp_steps["min"] <= actual.steps <= exp_steps["max"], (
            f"[{name}] steps: expected in [{exp_steps['min']}, "
            f"{exp_steps['max']}], got {actual.steps}"
        )
    exp_err = expected["error"]
    if exp_err is None:
        assert actual.error is None, (
            f"[{name}] expected no error, got {actual.error.code}: "
            f"{actual.error.message}"
        )
    else:
        assert actual.error is not None, (
            f"[{name}] expected error {exp_err['code']}, got none"
        )
        assert actual.error.code == exp_err["code"], (
            f"[{name}] error code: expected {exp_err['code']}, "
            f"got {actual.error.code}"
        )


@pytest.mark.parametrize("name", _discover_cases())
def test_corpus_case(name: str) -> None:
    """Run one corpus case: byte-exact stdout + report fields."""
    psc, input_text, expected_out, expected_report = _load_case(name)
    program = parse(psc)
    result = evaluate(
        program, input_text=input_text, seed=0, **CASE_KWARGS.get(name, {})
    )
    # Byte-exact stdout: a single trailing-space mutation must fail loudly.
    assert result.output == expected_out, (
        f"[{name}] stdout mismatch:\n"
        f"  expected: {expected_out!r}\n"
        f"  actual:   {result.output!r}"
    )
    _check_report(result, expected_report, name)


def test_corpus_coverage_counts() -> None:
    """Print the coverage summary and assert the corpus minimums."""
    cases = set(_discover_cases())
    assert len(cases) >= 25, f"corpus has {len(cases)} cases, need >= 25"
    neg = CATEGORIES["negative"]
    assert len(neg) >= 5, f"corpus has {len(neg)} negative cases, need >= 5"
    missing = neg - cases
    assert not missing, f"negative cases missing from corpus: {sorted(missing)}"

    lines = [f"corpus: {len(cases)} cases"]
    for cat in sorted(CATEGORIES):
        present = sorted(CATEGORIES[cat] & cases)
        lines.append(f"  {cat}: {len(present)} ({', '.join(present)})")
    print("\n".join(lines))