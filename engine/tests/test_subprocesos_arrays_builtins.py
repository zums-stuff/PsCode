"""Tests for SubProceso/Funcion, arrays, and SPEC built-ins (todo 6).

Covers: SubProceso/Funcion execution with Por Valor / Por Referencia params
(simple-by-value + arrays-by-reference defaults), recursion with the 1000
frame cap (ERR_RECURSION), Dimension/Redimensionar with dim + element caps
(ERR_DIM), array indexing + bounds (ERR_BOUNDS), and every SPEC §(b) built-in
including the pinned AZAR(100) seed-0 sequence and the FechaActual/HoraActual
stubs.
"""

from pseint_engine.evaluator import evaluate
from pseint_engine.parser import parse
from pseint_engine.runtime import EvalResult, RuntimeError


def run(src: str, input_text: str = "", seed: int = 0) -> EvalResult:
    return evaluate(parse(src), input_text=input_text, seed=seed)


def run_ok(src: str, input_text: str = "", seed: int = 0) -> EvalResult:
    result = run(src, input_text, seed)
    assert result.error is None, f"unexpected runtime error: {result.error}"
    return result


def run_err(src: str, input_text: str = "", seed: int = 0) -> RuntimeError:
    result = run(src, input_text, seed)
    assert result.error is not None, "expected a runtime error, got none"
    return result.error


def out(src: str, input_text: str = "", seed: int = 0) -> str:
    return run_ok(src, input_text, seed).output


def prog(body: str) -> str:
    """Wrap a program body (including SubProceso declarations) in Proceso."""
    return "Proceso P\n" + body + "FinProceso"


# ---------------------------------------------------------------------------
# SubProceso / Funcion
# ---------------------------------------------------------------------------


def test_subproceso_call_no_params():
    result = run_ok(
        prog(
            "    SubProceso saludar\n"
            "        Escribir \"hola\"\n"
            "    FinSubProceso\n"
            "    saludar()\n"
        )
    )
    assert result.output == "hola\n"


def test_subproceso_call_without_parens():
    result = run_ok(
        prog(
            "    SubProceso saludar\n"
            "        Escribir \"hola\"\n"
            "    FinSubProceso\n"
            "    saludar\n"
        )
    )
    assert result.output == "hola\n"


def test_subproceso_by_value_param_does_not_mutate_caller():
    result = run_ok(
        prog(
            "    SubProceso inc(a)\n"
            "        a <- a + 1\n"
            "    FinSubProceso\n"
            "    x <- 5\n"
            "    inc(x)\n"
            "    Escribir x\n"
        )
    )
    assert result.output == "5\n"


def test_subproceso_by_reference_param_mutates_caller():
    result = run_ok(
        prog(
            "    SubProceso inc(Por Referencia a)\n"
            "        a <- a + 1\n"
            "    FinSubProceso\n"
            "    x <- 5\n"
            "    inc(x)\n"
            "    Escribir x\n"
        )
    )
    assert result.output == "6\n"


def test_subproceso_by_reference_different_param_name():
    result = run_ok(
        prog(
            "    SubProceso doble(Por Referencia y)\n"
            "        y <- y * 2\n"
            "    FinSubProceso\n"
            "    x <- 21\n"
            "    doble(x)\n"
            "    Escribir x\n"
        )
    )
    assert result.output == "42\n"


def test_subproceso_multiple_params_mixed_direction():
    result = run_ok(
        prog(
            "    SubProceso swap(Por Referencia a, Por Referencia b)\n"
            "        t <- a\n"
            "        a <- b\n"
            "        b <- t\n"
            "    FinSubProceso\n"
            "    x <- 1\n"
            "    y <- 2\n"
            "    swap(x, y)\n"
            "    Escribir x, y\n"
        )
    )
    assert result.output == "21\n"


def test_funcion_returns_value():
    result = run_ok(
        prog(
            "    Funcion cuadrado(n): Entero\n"
            "        Retornar n * n\n"
            "    FinFuncion\n"
            "    Escribir cuadrado(7)\n"
        )
    )
    assert result.output == "49\n"


def test_funcion_with_return_type_converts():
    result = run_ok(
        prog(
            "    Funcion mitad(n): Real\n"
            "        Retornar n / 2\n"
            "    FinFuncion\n"
            "    Escribir mitad(9)\n"
        )
    )
    assert result.output == "4.5\n"


def test_funcion_retornar_statement():
    result = run_ok(
        prog(
            "    Funcion maximo(a, b): Entero\n"
            "        Si a > b Entonces\n"
            "            Retornar a\n"
            "        Sino\n"
            "            Retornar b\n"
            "        FinSi\n"
            "    FinFuncion\n"
            "    Escribir maximo(3, 9)\n"
        )
    )
    assert result.output == "9\n"


def test_recursive_factorial_10():
    result = run_ok(
        prog(
            "    Funcion fact(n): Entero\n"
            "        Si n <= 1 Entonces\n"
            "            Retornar 1\n"
            "        Sino\n"
            "            Retornar n * fact(n - 1)\n"
            "        FinSi\n"
            "    FinFuncion\n"
            "    Escribir fact(10)\n"
        )
    )
    assert result.output == "3628800\n"
    assert result.steps > 0


def test_recursion_depth_cap_is_err_recursion():
    err = run_err(
        prog(
            "    Funcion f(n): Entero\n"
            "        Retornar f(n + 1)\n"
            "    FinFuncion\n"
            "    Escribir f(0)\n"
        )
    )
    assert err.code == "ERR_RECURSION"


def test_callee_steps_count_toward_caller_total():
    # Each statement inside the callee counts toward the caller's total.
    result = run_ok(
        prog(
            "    SubProceso trabajo\n"
            "        a <- 1\n"
            "        b <- 2\n"
            "    FinSubProceso\n"
            "    trabajo()\n"
        )
    )
    # 1 (SubProceso declaration) + 1 (call stmt) + 2 (callee body) = 4
    assert result.steps == 4


def test_retornar_outside_function_is_err_type():
    err = run_err(prog("    Retornar 5\n"))
    assert err.code == "ERR_TYPE"


def test_undefined_subproceso_call_is_err_type():
    err = run_err(prog("    inexistente()\n"))
    assert err.code == "ERR_TYPE"


# ---------------------------------------------------------------------------
# Arrays
# ---------------------------------------------------------------------------


def test_dimension_and_indexing():
    result = run_ok(
        prog(
            "    Dimension a[5]\n"
            "    a[0] <- 10\n"
            "    a[4] <- 40\n"
            "    Escribir a[0], a[4]\n"
        )
    )
    assert result.output == "1040\n"


def test_array_index_in_expression():
    result = run_ok(
        prog(
            "    Dimension a[3]\n"
            "    a[0] <- 2\n"
            "    a[1] <- 3\n"
            "    Escribir a[0] + a[1]\n"
        )
    )
    assert result.output == "5\n"


def test_multi_dim_array():
    result = run_ok(
        prog(
            "    Dimension m[2, 3]\n"
            "    m[1, 2] <- 99\n"
            "    Escribir m[1, 2]\n"
        )
    )
    assert result.output == "99\n"


def test_array_bounds_error():
    err = run_err(prog("    Dimension a[3]\n    a[3] <- 1\n"))
    assert err.code == "ERR_BOUNDS"


def test_array_negative_index_bounds_error():
    err = run_err(prog("    Dimension a[3]\n    a[-1] <- 1\n"))
    assert err.code == "ERR_BOUNDS"


def test_undeclared_array_is_err_dim():
    err = run_err(prog("    a[0] <- 1\n"))
    assert err.code == "ERR_DIM"


def test_dimension_too_many_dims_is_err_dim():
    err = run_err(prog("    Dimension a[2, 2, 2, 2]\n"))
    assert err.code == "ERR_DIM"


def test_dimension_too_many_elements_is_err_dim():
    err = run_err(prog("    Dimension a[10000000]\n"))
    assert err.code == "ERR_DIM"


def test_total_array_elements_cap_is_err_dim():
    # 5 arrays of 1_000_000 each would exceed the 4_000_000 per-run cap.
    err = run_err(
        prog(
            "    Dimension a[1000000]\n"
            "    Dimension b[1000000]\n"
            "    Dimension c[1000000]\n"
            "    Dimension d[1000000]\n"
            "    Dimension e[1000000]\n"
        )
    )
    assert err.code == "ERR_DIM"


def test_redimensionar_resizes():
    result = run_ok(
        prog(
            "    Dimension a[2]\n"
            "    a[0] <- 7\n"
            "    Redimensionar a[4]\n"
            "    a[3] <- 8\n"
            "    Escribir a[0], a[3]\n"
        )
    )
    assert result.output == "78\n"


def test_redimensionar_on_non_array_is_err_dim():
    err = run_err(prog("    x <- 5\n    Redimensionar x[3]\n"))
    assert err.code == "ERR_DIM"


def test_array_by_reference_mutation_visible_at_caller():
    result = run_ok(
        prog(
            "    SubProceso llenar(a)\n"
            "        a[0] <- 42\n"
            "    FinSubProceso\n"
            "    Dimension arr[3]\n"
            "    llenar(arr)\n"
            "    Escribir arr[0]\n"
        )
    )
    assert result.output == "42\n"


def test_array_literal():
    result = run_ok(prog("    a <- [1, 2, 3]\n    Escribir a[1]\n"))
    assert result.output == "2\n"


def test_read_uninitialized_array_element_is_err_type():
    err = run_err(prog("    Dimension a[3]\n    Escribir a[0]\n"))
    assert err.code == "ERR_TYPE"


# ---------------------------------------------------------------------------
# Built-ins (SPEC §(b))
# ---------------------------------------------------------------------------


def test_azar_pinned_seed_0_sequence():
    # AZAR(100) with seed 0 must always produce this exact sequence.
    result = run_ok(
        prog(
            "    Escribir AZAR(100)\n"
            "    Escribir AZAR(100)\n"
            "    Escribir AZAR(100)\n"
            "    Escribir AZAR(100)\n"
            "    Escribir AZAR(100)\n"
        )
    )
    assert result.output == "49\n97\n53\n5\n33\n"


def test_azar_different_seed_different_sequence():
    result = run_ok(prog("    Escribir AZAR(100)\n"), seed=1)
    assert result.output != "49\n"


def test_rc_random_character():
    result = run_ok(prog("    Escribir RC(1)\n"))
    # seed 0 -> 'm' (pinned deterministic scheme)
    assert result.output == "m\n"


def test_abs():
    assert out(prog("    Escribir ABS(-5)\n")) == "5\n"
    assert out(prog("    Escribir ABS(3)\n")) == "3\n"


def test_ln_exp():
    assert out(prog("    Escribir LN(1)\n")) == "0.0\n"
    assert out(prog("    Escribir EXP(0)\n")) == "1.0\n"


def test_sen_cos_atan():
    assert out(prog("    Escribir SEN(0)\n")) == "0.0\n"
    assert out(prog("    Escribir COS(0)\n")) == "1.0\n"
    assert out(prog("    Escribir ATAN(0)\n")) == "0.0\n"


def test_trunc():
    assert out(prog("    Escribir TRUNC(3.9)\n")) == "3\n"
    assert out(prog("    Escribir TRUNC(-3.9)\n")) == "-3\n"


def test_redon():
    assert out(prog("    Escribir REDON(3.4)\n")) == "3\n"
    assert out(prog("    Escribir REDON(3.6)\n")) == "4\n"


def test_largo():
    assert out(prog("    Escribir LARGO(\"hola\")\n")) == "4\n"


def test_subcadena():
    # 1-indexed, inclusive substring.
    assert out(prog("    Escribir SUBCADENA(\"hola\", 2, 3)\n")) == "ol\n"


def test_concatenar():
    assert out(prog("    Escribir CONCATENAR(\"ho\", \"la\")\n")) == "hola\n"


def test_mayusculares_minusculas():
    assert out(prog("    Escribir MAYUSCULARES(\"hola\")\n")) == "HOLA\n"
    assert out(prog("    Escribir MINUSCULAS(\"HOLA\")\n")) == "hola\n"


def test_fecha_actual_stub():
    assert out(prog("    Escribir FechaActual()\n")) == "2026-01-01\n"


def test_hora_actual_stub():
    assert out(prog("    Escribir HoraActual()\n")) == "12:00:00\n"


def test_builtin_call_costs_one_step():
    result = run_ok(prog("    Escribir ABS(5)\n"))
    # 1 (Escribir stmt) + 1 (Escribir arg) + 1 (ABS call) = 3
    assert result.steps == 3


def test_unknown_function_is_err_type():
    err = run_err(prog("    Escribir inexistente(1)\n"))
    assert err.code == "ERR_TYPE"
