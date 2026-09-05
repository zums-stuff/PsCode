"""Hardening and property tests for the PseInt evaluator.

Hypothesis property tests generate bounded-depth PseInt expressions and assert
the evaluator NEVER raises a Python exception: every outcome is either a clean
result or a documented RE (one of the 8 SPEC section (i) codes). Edge-case
matrix covers negative Mod, int/float division, huge string ops, deep
recursion, array bounds sweep, Leer EOF, output cap, and step budget.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st

from pseint_engine.evaluator import evaluate
from pseint_engine.lexer import LexError
from pseint_engine.parser import ParseError, parse
from pseint_engine.runtime import EvalResult, RuntimeError

# The 8 documented SPEC section (i) runtime-error codes.
DOCUMENTED_ERRORS = frozenset(
    {
        "ERR_DIV0",
        "ERR_TYPE",
        "ERR_BOUNDS",
        "ERR_DIM",
        "ERR_RECURSION",
        "ERR_EOF_INPUT",
        "ERR_STEP_LIMIT",
        "ERR_OUTPUT_CAP",
    }
)


def _safe_eval(program: str, **kwargs: object) -> EvalResult:
    """Parse + evaluate; skip CE (parser/lexer errors are not evaluator
    crashes)."""
    try:
        ast = parse(program)
    except (LexError, ParseError):
        return EvalResult(output="", steps=0, error=None)
    return evaluate(ast, **kwargs)  # type: ignore[arg-type]


def _assert_no_crash(result: EvalResult) -> None:
    """Assert the no-crash invariant: clean result or documented RE."""
    assert result.error is None or result.error.code in DOCUMENTED_ERRORS, (
        f"undocumented error or Python exception leak: {result.error}"
    )


# ---------------------------------------------------------------------------
# Hypothesis strategies — bounded-depth PseInt expression generators
# ---------------------------------------------------------------------------

_int_lit = st.integers(-100, 100).map(str)
_real_lit = (
    st.floats(
        allow_nan=False, allow_infinity=False, min_value=-100, max_value=100
    )
    .filter(lambda x: abs(x) > 0.001 and not float(x).is_integer())
    .map(repr)
)
_bool_lit = st.sampled_from(["Verdadero", "Falso"])
_str_lit = st.text(
    alphabet=st.characters(
        whitelist_categories=(),
        whitelist_characters=(
            "abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789 "
        ),
    ),
    min_size=1,
    max_size=20,
).map(lambda s: f'"{s}"')

_literal = st.one_of(_int_lit, _real_lit, _bool_lit, _str_lit)


def _num_expr(depth: int) -> st.SearchStrategy[str]:
    if depth <= 0:
        return st.one_of(_int_lit, _real_lit)
    return st.one_of(
        _int_lit,
        _real_lit,
        st.tuples(
            st.sampled_from(["+", "-"]), _num_expr(depth - 1)
        ).map(lambda t: f"{t[0]}{t[1]}"),
        st.tuples(
            _num_expr(depth - 1),
            st.sampled_from(["+", "-", "*", "/", "%", "MOD", "^"]),
            _num_expr(depth - 1),
        ).map(lambda t: f"{t[0]} {t[1]} {t[2]}"),
    )


def _bool_expr(depth: int) -> st.SearchStrategy[str]:
    if depth <= 0:
        return _bool_lit
    return st.one_of(
        _bool_lit,
        st.tuples(st.sampled_from(["~"]), _bool_expr(depth - 1)).map(
            lambda t: f"{t[0]}{t[1]}"
        ),
        st.tuples(
            _bool_expr(depth - 1),
            st.sampled_from(["&", "|"]),
            _bool_expr(depth - 1),
        ).map(lambda t: f"{t[0]} {t[1]} {t[2]}"),
    )


def _str_expr(depth: int) -> st.SearchStrategy[str]:
    if depth <= 0:
        return _str_lit
    return st.one_of(
        _str_lit,
        st.fixed_dictionaries(
            {"s": _str_lit, "i": _int_lit, "j": _int_lit}
        ).map(lambda d: f"SUBCADENA({d['s']}, {d['i']}, {d['j']})"),
        st.tuples(_str_lit, _str_lit).map(
            lambda t: f"CONCATENAR({t[0]}, {t[1]})"
        ),
    )


def _expr(depth: int) -> st.SearchStrategy[str]:
    """General expression — may mix types; ERR_TYPE is an expected RE."""
    if depth <= 0:
        return _literal
    return st.one_of(
        _literal,
        _num_expr(depth),
        _bool_expr(depth),
        _str_expr(depth),
        # Built-in numeric (type mismatches are fine — ERR_TYPE, not crash)
        st.tuples(
            st.sampled_from(["ABS", "TRUNC", "REDON"]),
            _num_expr(depth - 1),
        ).map(lambda t: f"{t[0]}({t[1]})"),
        st.tuples(
            st.sampled_from(["LN", "EXP", "SEN", "COS", "ATAN"]),
            _num_expr(depth - 1),
        ).map(lambda t: f"{t[0]}({t[1]})"),
        # Built-in string
        st.tuples(
            st.sampled_from(["LARGO", "MAYUSCULARES", "MINUSCULAS"]),
            _str_lit,
        ).map(lambda t: f"{t[0]}({t[1]})"),
        # Built-in random
        st.tuples(
            st.sampled_from(["AZAR", "RC"]),
            _int_lit,
        ).map(lambda t: f"{t[0]}({t[1]})"),
        # Binary comparison
        st.tuples(
            _num_expr(depth - 1),
            st.sampled_from(["<", ">", "=", "==", "<>", "<=", ">="]),
            _num_expr(depth - 1),
        ).map(lambda t: f"{t[0]} {t[1]} {t[2]}"),
        # Parenthesized
        st.tuples(_num_expr(depth - 1)).map(lambda t: f"({t[0]})"),
    )


@st.composite
def _programs(draw: st.DrawFn) -> str:
    expr = draw(_expr(depth=3))
    return f"Proceso P\n    Escribir {expr}\nFinProceso"


@st.composite
def _array_programs(draw: st.DrawFn) -> str:
    size = draw(st.integers(min_value=3, max_value=10))
    idx = draw(st.integers(min_value=-2, max_value=size + 1))
    return (
        f"Proceso P\n"
        f"    Dimension a[{size}]\n"
        f"    Escribir a[{idx}]\n"
        f"FinProceso"
    )


# ---------------------------------------------------------------------------
# Property tests — the no-crash invariant
# ---------------------------------------------------------------------------


@given(program=_programs())
@settings(max_examples=200)
def test_property_no_crash_expressions(program: str) -> None:
    """Every expression program either parses-and-evaluates cleanly or raises
    a documented RE — never a raw Python exception."""
    result = _safe_eval(program)
    _assert_no_crash(result)


@given(program=_array_programs())
@settings(max_examples=200)
def test_property_no_crash_array_access(program: str) -> None:
    """Array access programs either evaluate cleanly or raise documented RE."""
    result = _safe_eval(program)
    _assert_no_crash(result)


# ---------------------------------------------------------------------------
# Edge-case matrix
# ---------------------------------------------------------------------------


class TestEdgeModNegative:
    """Negative Mod operations (SPEC section (c))."""

    @pytest.mark.parametrize(
        "expr,expected",
        [
            ("-7 MOD 3", 2),
            ("7 MOD -3", -2),
            ("-7 MOD -3", -1),
        ],
    )
    def test_mod_negative(self, expr: str, expected: int) -> None:
        result = _safe_eval(f"Proceso P\n    Escribir {expr}\nFinProceso")
        assert result.error is None
        assert result.output.strip() == str(expected)


class TestEdgeDivision:
    """Int/float division edge cases."""

    def test_int_div_gives_real(self) -> None:
        result = _safe_eval(
            "Proceso P\n    Escribir 7 / 2\nFinProceso"
        )
        assert result.error is None
        assert result.output.strip() == "3.5"

    def test_div_by_zero(self) -> None:
        result = _safe_eval(
            "Proceso P\n    Escribir 7 / 0\nFinProceso"
        )
        assert result.error is not None
        assert result.error.code == "ERR_DIV0"

    def test_zero_div_zero(self) -> None:
        result = _safe_eval(
            "Proceso P\n    Escribir 0 / 0\nFinProceso"
        )
        assert result.error is not None
        assert result.error.code == "ERR_DIV0"

    def test_mod_by_zero(self) -> None:
        result = _safe_eval(
            "Proceso P\n    Escribir 7 MOD 0\nFinProceso"
        )
        assert result.error is not None
        assert result.error.code == "ERR_DIV0"


class TestEdgeStringOps:
    """Huge string operations (LARGO, SUBCADENA on long strings)."""

    def test_largo_large_string(self) -> None:
        long_str = "x" * 100_000
        result = _safe_eval(
            f'Proceso P\n    Escribir LARGO("{long_str}")\nFinProceso'
        )
        assert result.error is None
        assert result.output.strip() == "100000"

    def test_subcadena_out_of_range_low(self) -> None:
        result = _safe_eval(
            'Proceso P\n'
            '    Escribir SUBCADENA("hello", 0, 3)\n'
            "FinProceso"
        )
        assert result.error is None

    def test_subcadena_out_of_range_high(self) -> None:
        result = _safe_eval(
            'Proceso P\n'
            '    Escribir SUBCADENA("hello", 1, 100)\n'
            "FinProceso"
        )
        assert result.error is None
        assert result.output.strip() == "hello"

    def test_subcadena_negative_indices(self) -> None:
        result = _safe_eval(
            'Proceso P\n'
            '    Escribir SUBCADENA("hello", -1, 3)\n'
            "FinProceso"
        )
        assert result.error is None

    def test_concatenar_large(self) -> None:
        a = "a" * 50_000
        b = "b" * 50_000
        result = _safe_eval(
            f'Proceso P\n'
            f'    Escribir CONCATENAR("{a}", "{b}")\n'
            f"FinProceso"
        )
        assert result.error is None
        assert len(result.output.rstrip("\n")) == 100_000

    def test_mayusculares_large(self) -> None:
        s = "abc" * 33_333
        result = _safe_eval(
            f'Proceso P\n'
            f'    Escribir MAYUSCULARES("{s}")\n'
            f"FinProceso"
        )
        assert result.error is None
        assert result.output.startswith("ABC")


class TestEdgeRecursion:
    """Deep recursion — ERR_RECURSION fires at 1000 frames, not Python
    RecursionError."""

    def test_infinite_recursion_err_recursion(self) -> None:
        program = (
            "Proceso P\n"
            "    SubProceso f()\n"
            "        f()\n"
            "    FinSubProceso\n"
            "    f()\n"
            "FinProceso"
        )
        result = _safe_eval(program)
        assert result.error is not None
        assert result.error.code == "ERR_RECURSION"
        # Must NOT be a Python RecursionError
        assert isinstance(result.error, RuntimeError)

    def test_deep_recursion_within_cap(self) -> None:
        """Factorial(10) uses 10 recursive calls — well within cap."""
        program = (
            "Proceso P\n"
            "    Funcion factorial(n): Entero\n"
            "        Si n <= 1 Entonces\n"
            "            Retornar 1\n"
            "        FinSi\n"
            "        Retornar n * factorial(n - 1)\n"
            "    FinFuncion\n"
            "    Escribir factorial(10)\n"
            "FinProceso"
        )
        result = _safe_eval(program)
        assert result.error is None
        assert result.output.strip() == "3628800"


class TestEdgeArrayBounds:
    """Array bounds sweep: index 0..size, negative, size-1, size, size+1."""

    @pytest.mark.parametrize(
        "idx,expect_error",
        [
            (-2, True),
            (-1, True),
            (0, False),
            (4, False),  # size=5, size-1=4 is valid
            (5, True),  # size=5, index=size is OOB
            (6, True),  # size=5, index=size+1 is OOB
        ],
    )
    def test_array_bounds_sweep(self, idx: int, expect_error: bool) -> None:
        program = (
            f"Proceso P\n"
            f"    Dimension a[5]\n"
            f"    a[0] <- 10\n"
            f"    a[1] <- 20\n"
            f"    a[2] <- 30\n"
            f"    a[3] <- 40\n"
            f"    a[4] <- 50\n"
            f"    Escribir a[{idx}]\n"
            f"FinProceso"
        )
        result = _safe_eval(program)
        if expect_error:
            assert result.error is not None
            assert result.error.code == "ERR_BOUNDS"
        else:
            assert result.error is None


class TestEdgeLeerEof:
    """Leer with empty input → ERR_EOF_INPUT."""

    def test_leer_eof(self) -> None:
        result = _safe_eval(
            "Proceso P\n"
            "    Definir x Como Entero\n"
            "    Leer x\n"
            "FinProceso",
            input_text="",
        )
        assert result.error is not None
        assert result.error.code == "ERR_EOF_INPUT"


class TestEdgeOutputCap:
    """Output cap enforcement → ERR_OUTPUT_CAP."""

    def test_output_cap_fires(self) -> None:
        """Loop writes >100 bytes → ERR_OUTPUT_CAP fires."""
        program = (
            "Proceso P\n"
            '    Para i <- 1 Hasta 20\n'
            '        Escribir "XXXXXXXXXX"\n'
            "    FinPara\n"
            "FinProceso"
        )
        # Each iteration: 10 chars + newline = 11 bytes.
        # 10 iterations = 110 bytes > 100 cap.
        result = _safe_eval(program, output_cap=100)
        assert result.error is not None
        assert result.error.code == "ERR_OUTPUT_CAP"
        # Partial output exists (cap fires after append).
        assert len(result.output) > 0


class TestEdgeStepBudget:
    """Step budget enforcement → ERR_STEP_LIMIT."""

    def test_step_budget_fires(self) -> None:
        """Infinite Mientras loop with step_budget=1000 → ERR_STEP_LIMIT."""
        program = (
            "Proceso P\n"
            "    Mientras Verdadero Hacer\n"
            '        Escribir "x"\n'
            "    FinMientras\n"
            "FinProceso"
        )
        result = _safe_eval(program, step_budget=1000)
        assert result.error is not None
        assert result.error.code == "ERR_STEP_LIMIT"

    def test_step_budget_not_exceeded(self) -> None:
        """Program that finishes within budget → no error."""
        program = (
            "Proceso P\n"
            "    Escribir 42\n"
            "FinProceso"
        )
        result = _safe_eval(program, step_budget=1000)
        assert result.error is None
        assert result.output.strip() == "42"
