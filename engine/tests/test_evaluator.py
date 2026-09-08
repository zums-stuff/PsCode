"""Tests for the PseInt evaluator (engine/src/pseint_engine/evaluator.py).

Covers: implicit typing + SPEC §(c) conversion matrix (every row), arithmetic
rules, Escribir formatting (the 3 golden examples from SPEC §(e) verbatim),
Leer parsing per §(f), every control structure, exact step counts per §(g),
the recursion-depth cap (ERR_RECURSION), and clear "not yet implemented"
runtime errors for arrays/built-ins/subprocesos (todo 6).
"""

import pytest

from pseint_engine.ast_nodes import Identifier
from pseint_engine.evaluator import Evaluator, evaluate
from pseint_engine.parser import parse
from pseint_engine.runtime import EvalResult, RuntimeError


def run(src: str, input_text: str = "") -> EvalResult:
    return evaluate(parse(src), input_text=input_text)


def run_ok(src: str, input_text: str = "") -> EvalResult:
    result = run(src, input_text)
    assert result.error is None, f"unexpected runtime error: {result.error}"
    return result


def run_err(src: str, input_text: str = "") -> RuntimeError:
    result = run(src, input_text)
    assert result.error is not None, "expected a runtime error, got none"
    return result.error


def out(src: str, input_text: str = "") -> str:
    return run_ok(src, input_text).output


def body_out(*stmts: str) -> str:
    """Run a program whose body is the given statements; return its output."""
    src = "Proceso P\n" + "".join(f"    {s}\n" for s in stmts) + "FinProceso"
    return out(src)


# ---------------------------------------------------------------------------
# Assignment + implicit typing (SPEC §(c))
# ---------------------------------------------------------------------------


def test_implicit_typing_infers_from_first_assignment():
    result = run_ok(
        "Proceso P\n"
        "    x <- 5\n"
        "    Escribir x\n"
        "FinProceso"
    )
    assert result.output == "5\n"


def test_type_is_fixed_once_inferred():
    # x inferred Entero from 5; assigning 3.14 truncates to 3.
    result = run_ok(
        "Proceso P\n"
        "    x <- 5\n"
        "    x <- 3.14\n"
        "    Escribir x\n"
        "FinProceso"
    )
    assert result.output == "3\n"


def test_definir_with_type_and_init():
    result = run_ok(
        "Proceso P\n"
        "    Definir x: Entero = 5\n"
        "    Escribir x\n"
        "FinProceso"
    )
    assert result.output == "5\n"


def test_definir_multiple_names():
    result = run_ok(
        "Proceso P\n"
        "    Definir a, b Como Entero\n"
        "    a <- 1\n"
        "    b <- 2\n"
        "    Escribir a, b\n"
        "FinProceso"
    )
    assert result.output == "12\n"


def test_definir_conflicting_redeclaration_is_err_type():
    err = run_err(
        "Proceso P\n"
        "    Definir x: Entero\n"
        "    Definir x: Real\n"
        "FinProceso"
    )
    assert err.code == "ERR_TYPE"


def test_read_uninitialized_variable_is_err_type():
    err = run_err(
        "Proceso P\n"
        "    Definir x: Entero\n"
        "    Escribir x\n"
        "FinProceso"
    )
    assert err.code == "ERR_TYPE"
    assert "inicializada" in err.message


def test_read_undefined_variable_is_err_type():
    err = run_err(
        "Proceso P\n"
        "    Escribir inexistente\n"
        "FinProceso"
    )
    assert err.code == "ERR_TYPE"


# ---------------------------------------------------------------------------
# Conversion matrix (SPEC §(c)) — one test per matrix row
# ---------------------------------------------------------------------------


def test_entero_to_real():
    assert body_out("Definir x: Real", "x <- 5", "Escribir x") == "5.0\n"


def test_entero_to_logico():
    assert body_out("Definir x: Logico", "x <- 5", "Escribir x") == "Verdadero\n"
    assert body_out("Definir x: Logico", "x <- 0", "Escribir x") == "Falso\n"


def test_entero_to_caracter():
    assert body_out("Definir x: Caracter", "x <- 65", "Escribir x") == "A\n"


def test_entero_to_cadena():
    assert body_out("Definir x: Cadena", "x <- 42", "Escribir x") == "42\n"


def test_real_to_entero_truncates():
    assert body_out("Definir x: Entero", "x <- 3.7", "Escribir x") == "3\n"
    assert body_out("Definir x: Entero", "x <- -3.7", "Escribir x") == "-3\n"


def test_real_to_logico():
    assert body_out("Definir x: Logico", "x <- 0.0", "Escribir x") == "Falso\n"
    assert body_out("Definir x: Logico", "x <- 0.5", "Escribir x") == "Verdadero\n"


def test_real_to_caracter_truncates_first():
    assert body_out("Definir x: Caracter", "x <- 65.9", "Escribir x") == "A\n"


def test_real_to_cadena():
    assert body_out("Definir x: Cadena", "x <- 3.14", "Escribir x") == "3.14\n"


def test_logico_to_entero():
    assert body_out("Definir x: Entero", "x <- Verdadero", "Escribir x") == "1\n"
    assert body_out("Definir x: Entero", "x <- Falso", "Escribir x") == "0\n"


def test_logico_to_real():
    assert body_out("Definir x: Real", "x <- Verdadero", "Escribir x") == "1.0\n"


def test_logico_to_cadena():
    assert body_out("Definir x: Cadena", "x <- Verdadero", "Escribir x") == (
        "Verdadero\n"
    )


def test_logico_to_caracter_per_matrix():
    # Matrix row: Logico -> Caracter = "Verdadero"/"Falso" (literal per SPEC).
    assert body_out("Definir x: Caracter", "x <- Verdadero", "Escribir x") == (
        "Verdadero\n"
    )


def test_caracter_to_entero_ascii():
    assert body_out("Definir x: Entero", 'x <- "A"', "Escribir x") == "65\n"


def test_caracter_to_real_ascii():
    assert body_out("Definir x: Real", 'x <- "A"', "Escribir x") == "65.0\n"


def test_caracter_to_cadena():
    assert body_out("Definir x: Cadena", 'x <- "A"', "Escribir x") == "A\n"


def test_cadena_to_entero_parse():
    assert body_out("Definir x: Entero", 'x <- "42"', "Escribir x") == "42\n"


def test_cadena_to_entero_parse_fail_is_err_type():
    err = run_err("Proceso P\n    Definir x: Entero\n    x <- \"abc\"\nFinProceso")
    assert err.code == "ERR_TYPE"


def test_cadena_to_real_parse():
    assert body_out("Definir x: Real", 'x <- "3.14"', "Escribir x") == "3.14\n"


def test_cadena_to_real_parse_fail_is_err_type():
    err = run_err("Proceso P\n    Definir x: Real\n    x <- \"abc\"\nFinProceso")
    assert err.code == "ERR_TYPE"


def test_cadena_to_logico():
    assert body_out("Definir x: Logico", 'x <- "Verdadero"', "Escribir x") == (
        "Verdadero\n"
    )
    assert body_out("Definir x: Logico", 'x <- "Falso"', "Escribir x") == "Falso\n"


def test_cadena_to_logico_parse_fail_is_err_type():
    err = run_err("Proceso P\n    Definir x: Logico\n    x <- \"xyz\"\nFinProceso")
    assert err.code == "ERR_TYPE"


def test_cadena_to_caracter_takes_first_char():
    assert body_out("Definir x: Caracter", 'x <- "Hola"', "Escribir x") == "H\n"


def test_caracter_to_logico_is_not_allowed():
    # Matrix row Caracter -> Logico is "—" (no conversion).
    err = run_err("Proceso P\n    Definir x: Logico\n    x <- \"A\"\nFinProceso")
    assert err.code == "ERR_TYPE"


def test_caracter_value_flows_through_expression_with_declared_type():
    # c is Caracter; reading it must keep the Caracter type so c -> Entero is ASCII.
    result = run_ok(
        "Proceso P\n"
        "    Definir c: Caracter\n"
        "    Definir x: Entero\n"
        "    c <- \"A\"\n"
        "    x <- c\n"
        "    Escribir x\n"
        "FinProceso"
    )
    assert result.output == "65\n"


# ---------------------------------------------------------------------------
# Arithmetic rules (SPEC §(c))
# ---------------------------------------------------------------------------


def test_int_divided_by_int_is_real():
    assert out("Proceso P\n    x <- 5 / 2\n    Escribir x\nFinProceso") == "2.5\n"


def test_int_plus_int_is_int():
    assert out("Proceso P\n    x <- 5 + 2\n    Escribir x\nFinProceso") == "7\n"


def test_int_times_int_is_int():
    assert out("Proceso P\n    x <- 5 * 2\n    Escribir x\nFinProceso") == "10\n"


def test_int_op_real_is_real():
    assert out("Proceso P\n    x <- 5 + 2.5\n    Escribir x\nFinProceso") == "7.5\n"
    assert out("Proceso P\n    x <- 5.5 + 2\n    Escribir x\nFinProceso") == "7.5\n"


def test_mod_on_reals_truncates_operands():
    assert out("Proceso P\n    x <- 7.9 MOD 2\n    Escribir x\nFinProceso") == "1\n"
    assert out("Proceso P\n    x <- 7.9 % 2\n    Escribir x\nFinProceso") == "1\n"


def test_mod_by_zero_is_err_div0():
    err = run_err("Proceso P\n    x <- 5 MOD 0\nFinProceso")
    assert err.code == "ERR_DIV0"


def test_division_by_zero_is_err_div0():
    err = run_err("Proceso P\n    x <- 5 / 0\nFinProceso")
    assert err.code == "ERR_DIV0"


def test_division_by_zero_variable_is_err_div0():
    err = run_err("Proceso P\n    d <- 0\n    x <- 5 / d\nFinProceso")
    assert err.code == "ERR_DIV0"


def test_type_mismatch_in_operation_is_err_type():
    err = run_err("Proceso P\n    x <- 5 + \"hola\"\nFinProceso")
    assert err.code == "ERR_TYPE"


def test_logical_operator_on_non_logico_is_err_type():
    err = run_err("Proceso P\n    x <- 5 & Verdadero\nFinProceso")
    assert err.code == "ERR_TYPE"


def test_logical_and_or():
    assert body_out("x <- Verdadero & Falso", "Escribir x") == "Falso\n"
    assert body_out("x <- Verdadero | Falso", "Escribir x") == "Verdadero\n"


def test_not_operator():
    assert body_out("x <- ~Verdadero", "Escribir x") == "Falso\n"


def test_power_operator():
    assert out("Proceso P\n    x <- 2 ^ 3\n    Escribir x\nFinProceso") == "8\n"


def test_unary_minus():
    assert out("Proceso P\n    x <- -5\n    Escribir x\nFinProceso") == "-5\n"


def test_relational_operators_return_logico():
    assert body_out("x <- 3 > 2", "Escribir x") == "Verdadero\n"
    assert body_out("x <- 3 <> 2", "Escribir x") == "Verdadero\n"
    assert body_out("x <- 3 = 2", "Escribir x") == "Falso\n"
    assert body_out("x <- 3 <= 3", "Escribir x") == "Verdadero\n"


def test_string_equality():
    assert body_out('x <- "hola" = "hola"', "Escribir x") == "Verdadero\n"
    assert body_out('x <- "hola" = "mundo"', "Escribir x") == "Falso\n"


def test_logico_equality():
    assert body_out("x <- Verdadero = Verdadero", "Escribir x") == "Verdadero\n"


# ---------------------------------------------------------------------------
# Escribir formatting (SPEC §(e)) — golden examples verbatim
# ---------------------------------------------------------------------------


def test_golden_example_1_integer_and_real():
    src = (
        "Proceso Ej1\n"
        "    Definir x: Entero\n"
        "    Definir y: Real\n"
        "    x <- 42\n"
        "    y <- 3.14\n"
        "    Escribir x\n"
        "    Escribir y\n"
        "FinProceso"
    )
    assert out(src) == "42\n3.14\n"


def test_golden_example_2_sin_saltar_multi_arg():
    src = (
        "Proceso Ej2\n"
        "    Escribir Sin Saltar \"Resultado: \"\n"
        "    Escribir 100\n"
        "FinProceso"
    )
    assert out(src) == "Resultado: 100\n"


def test_golden_example_3_boolean_and_string():
    src = (
        "Proceso Ej3\n"
        "    Definir flag: Logico\n"
        "    flag <- Verdadero\n"
        "    Escribir flag\n"
        "    Escribir \"Hola Mundo\"\n"
        "FinProceso"
    )
    assert out(src) == "Verdadero\nHola Mundo\n"


def test_real_shortest_roundtrip_formatting():
    assert out("Proceso P\n    Escribir 2.0\nFinProceso") == "2.0\n"
    assert out("Proceso P\n    Escribir 0.5\nFinProceso") == "0.5\n"


def test_multi_arg_no_separator():
    assert out("Proceso P\n    Escribir \"a\", \"b\", \"c\"\nFinProceso") == "abc\n"


def test_sin_saltar_suppresses_newline():
    assert body_out('Escribir Sin Saltar "hola"', 'Escribir "mundo"') == "holamundo\n"


def test_caracter_prints_raw():
    assert body_out("Definir c: Caracter", 'c <- "A"', "Escribir c") == "A\n"


def test_logico_prints_verdadero_falso():
    assert body_out("Escribir Verdadero", "Escribir Falso") == "Verdadero\nFalso\n"


# ---------------------------------------------------------------------------
# Leer (SPEC §(f))
# ---------------------------------------------------------------------------


def test_leer_basic():
    result = run_ok(
        "Proceso P\n"
        "    Leer a, b\n"
        "    Escribir a, b\n"
        "FinProceso",
        input_text="1 2",
    )
    assert result.output == "12\n"


def test_leer_infers_types_from_tokens():
    result = run_ok(
        "Proceso P\n"
        "    Leer a, b, c\n"
        "    Escribir a\n"
        "    Escribir b\n"
        "    Escribir c\n"
        "FinProceso",
        input_text="42 3.14 Verdadero",
    )
    assert result.output == "42\n3.14\nVerdadero\n"


def test_leer_extra_tokens_discarded():
    result = run_ok(
        "Proceso P\n"
        "    Leer a\n"
        "    Escribir a\n"
        "FinProceso",
        input_text="1 2 3",
    )
    assert result.output == "1\n"


def test_leer_eof_is_err_eof_input():
    err = run_err(
        "Proceso P\n"
        "    Leer a, b\n"
        "FinProceso",
        input_text="1",
    )
    assert err.code == "ERR_EOF_INPUT"
    assert err.message == "fin de entrada inesperado"


def test_leer_empty_input_is_err_eof_input():
    err = run_err("Proceso P\n    Leer a\nFinProceso", input_text="")
    assert err.code == "ERR_EOF_INPUT"


def test_bare_leer_discards_one_line():
    result = run_ok(
        "Proceso P\n"
        "    Leer\n"
        "    Leer a\n"
        "    Escribir a\n"
        "FinProceso",
        input_text="1 2\n3 4",
    )
    assert result.output == "3\n"


def test_leer_crosses_line_boundaries():
    result = run_ok(
        "Proceso P\n"
        "    Leer a, b, c\n"
        "    Escribir a, b, c\n"
        "FinProceso",
        input_text="1 2\n3",
    )
    assert result.output == "123\n"


def test_leer_logico_case_insensitive():
    result = run_ok(
        "Proceso P\n"
        "    Definir f: Logico\n"
        "    Leer f\n"
        "    Escribir f\n"
        "FinProceso",
        input_text="verdadero",
    )
    assert result.output == "Verdadero\n"


def test_leer_caracter_requires_single_char():
    result = run_ok(
        "Proceso P\n"
        "    Definir c: Caracter\n"
        "    Leer c\n"
        "    Escribir c\n"
        "FinProceso",
        input_text="A",
    )
    assert result.output == "A\n"
    err = run_err(
        "Proceso P\n    Definir c: Caracter\n    Leer c\nFinProceso",
        input_text="AB",
    )
    assert err.code == "ERR_TYPE"


def test_leer_entero_rejects_non_integer_token():
    err = run_err(
        "Proceso P\n    Definir x: Entero\n    Leer x\nFinProceso",
        input_text="abc",
    )
    assert err.code == "ERR_TYPE"


def test_leer_real_accepts_integer_token():
    result = run_ok(
        "Proceso P\n"
        "    Definir x: Real\n"
        "    Leer x\n"
        "    Escribir x\n"
        "FinProceso",
        input_text="5",
    )
    assert result.output == "5.0\n"


def test_leer_cadena_takes_token_as_is():
    result = run_ok(
        "Proceso P\n"
        "    Definir s: Cadena\n"
        "    Leer s\n"
        "    Escribir s\n"
        "FinProceso",
        input_text="hola",
    )
    assert result.output == "hola\n"


# ---------------------------------------------------------------------------
# Typed declarations (``Cadena s`` / ``Entero i <- 5``) — sugar for
# ``Definir`` with the same type tag.
# ---------------------------------------------------------------------------


def test_typed_decl_cadena_then_leer_escribir():
    """The exact user repro: ``Cadena s / Leer s / Escribir s`` end-to-end."""
    result = run_ok(
        "Proceso P\n"
        "    Cadena s\n"
        "    Leer s\n"
        "    Escribir s\n"
        "FinProceso",
        input_text="Hola\n",
    )
    assert result.output == "Hola\n"
    assert result.error is None


def test_typed_decl_entero_default_is_zero():
    result = run_ok(
        "Proceso P\n"
        "    Entero x\n"
        "    Escribir x\n"
        "FinProceso",
        input_text="",
    )
    assert result.output == "0\n"


def test_typed_decl_real_default_is_zero():
    result = run_ok(
        "Proceso P\n"
        "    Real x\n"
        "    Escribir x\n"
        "FinProceso",
        input_text="",
    )
    assert result.output == "0.0\n"


def test_typed_decl_logico_default_is_falso():
    result = run_ok(
        "Proceso P\n"
        "    Logico b\n"
        "    Escribir b\n"
        "FinProceso",
        input_text="",
    )
    assert result.output == "Falso\n"


def test_typed_decl_cadena_default_is_empty():
    result = run_ok(
        "Proceso P\n"
        "    Cadena s\n"
        "    Escribir s\n"
        "FinProceso",
        input_text="",
    )
    assert result.output == "\n"


def test_typed_decl_with_initializer_entero():
    result = run_ok(
        "Proceso P\n"
        "    Entero i <- 42\n"
        "    Escribir i\n"
        "FinProceso",
        input_text="",
    )
    assert result.output == "42\n"


def test_typed_decl_with_initializer_real():
    result = run_ok(
        "Proceso P\n"
        "    Real pi <- 3.14\n"
        "    Escribir pi\n"
        "FinProceso",
        input_text="",
    )
    assert result.output == "3.14\n"


def test_typed_decl_with_initializer_logico_verdadero():
    result = run_ok(
        "Proceso P\n"
        "    Logico b <- Verdadero\n"
        "    Escribir b\n"
        "FinProceso",
        input_text="",
    )
    assert result.output == "Verdadero\n"


def test_typed_decl_with_initializer_caracter():
    result = run_ok(
        'Proceso P\n'
        '    Caracter c <- "X"\n'
        "    Escribir c\n"
        "FinProceso",
        input_text="",
    )
    assert result.output == "X\n"


def test_typed_decl_conflicting_types_is_err_type():
    """``Entero i <- 5`` then ``Cadena i`` redeclares with a different type → RE."""
    err = run_err(
        "Proceso P\n"
        "    Entero i <- 5\n"
        "    Cadena i\n"
        "FinProceso",
        input_text="",
    )
    assert err.code == "ERR_TYPE"


def test_typed_decl_coerces_value_to_declared_type():
    """``Real x <- 5`` coerces the integer 5 to 5.0 (SPEC §(c) matrix)."""
    result = run_ok(
        "Proceso P\n"
        "    Real x <- 5\n"
        "    Escribir x\n"
        "FinProceso",
        input_text="",
    )
    assert result.output == "5.0\n"


# ---------------------------------------------------------------------------
# Control structures
# ---------------------------------------------------------------------------


def test_si_then_branch():
    assert out(
        "Proceso P\n"
        "    x <- 5\n"
        "    Si x > 3 Entonces\n"
        "        Escribir \"grande\"\n"
        "    Sino\n"
        "        Escribir \"chico\"\n"
        "    FinSi\n"
        "FinProceso"
    ) == "grande\n"


def test_si_else_branch():
    assert out(
        "Proceso P\n"
        "    x <- 1\n"
        "    Si x > 3 Entonces\n"
        "        Escribir \"grande\"\n"
        "    Sino\n"
        "        Escribir \"chico\"\n"
        "    FinSi\n"
        "FinProceso"
    ) == "chico\n"


def test_si_without_else():
    assert out(
        "Proceso P\n"
        "    x <- 1\n"
        "    Si x > 3 Entonces\n"
        "        Escribir \"grande\"\n"
        "    FinSi\n"
        "    Escribir \"fin\"\n"
        "FinProceso"
    ) == "fin\n"


def test_segun_matching_case():
    assert out(
        "Proceso P\n"
        "    x <- 2\n"
        "    Segun x Hacer\n"
        "        1: Escribir \"uno\"\n"
        "        2: Escribir \"dos\"\n"
        "        De Otro Modo: Escribir \"otro\"\n"
        "    FinSegun\n"
        "FinProceso"
    ) == "dos\n"


def test_segun_default_case():
    assert out(
        "Proceso P\n"
        "    x <- 9\n"
        "    Segun x Hacer\n"
        "        1: Escribir \"uno\"\n"
        "        2: Escribir \"dos\"\n"
        "        De Otro Modo: Escribir \"otro\"\n"
        "    FinSegun\n"
        "FinProceso"
    ) == "otro\n"


def test_segun_no_match_no_default():
    assert out(
        "Proceso P\n"
        "    x <- 9\n"
        "    Segun x Hacer\n"
        "        1: Escribir \"uno\"\n"
        "        2: Escribir \"dos\"\n"
        "    FinSegun\n"
        "    Escribir \"fin\"\n"
        "FinProceso"
    ) == "fin\n"


def test_mientras_loop():
    assert out(
        "Proceso P\n"
        "    i <- 1\n"
        "    Mientras i <= 3 Hacer\n"
        "        Escribir i\n"
        "        i <- i + 1\n"
        "    FinMientras\n"
        "FinProceso"
    ) == "1\n2\n3\n"


def test_mientras_condition_false_on_first_check():
    assert out(
        "Proceso P\n"
        "    i <- 5\n"
        "    Mientras i <= 3 Hacer\n"
        "        Escribir i\n"
        "    FinMientras\n"
        "    Escribir \"fin\"\n"
        "FinProceso"
    ) == "fin\n"


def test_repetir_hasta_que():
    assert out(
        "Proceso P\n"
        "    i <- 1\n"
        "    Repetir\n"
        "        Escribir i\n"
        "        i <- i + 1\n"
        "    Hasta Que i > 3\n"
        "FinProceso"
    ) == "1\n2\n3\n"


def test_para_loop():
    assert out(
        "Proceso P\n"
        "    Para i <- 1 Hasta 3\n"
        "        Escribir i\n"
        "    FinPara\n"
        "FinProceso"
    ) == "1\n2\n3\n"


def test_para_with_con_paso():
    assert out(
        "Proceso P\n"
        "    Para i <- 1 Hasta 5 Con Paso 2\n"
        "        Escribir i\n"
        "    FinPara\n"
        "FinProceso"
    ) == "1\n3\n5\n"


def test_para_start_greater_than_end_does_not_run():
    assert out(
        "Proceso P\n"
        "    Para i <- 3 Hasta 1\n"
        "        Escribir i\n"
        "    FinPara\n"
        "    Escribir \"fin\"\n"
        "FinProceso"
    ) == "fin\n"


def test_hacer_mientras_que():
    assert out(
        "Proceso P\n"
        "    i <- 1\n"
        "    Hacer\n"
        "        Escribir i\n"
        "        i <- i + 1\n"
        "    Mientras Que i <= 3\n"
        "FinProceso"
    ) == "1\n2\n3\n"


def test_nested_control_structures():
    assert out(
        "Proceso P\n"
        "    Para i <- 1 Hasta 2\n"
        "        Si i = 1 Entonces\n"
        "            Escribir \"uno\"\n"
        "        Sino\n"
        "            Escribir \"dos\"\n"
        "        FinSi\n"
        "    FinPara\n"
        "FinProceso"
    ) == "uno\ndos\n"


def test_esperar_is_noop():
    assert out(
        "Proceso P\n"
        "    Esperar 100\n"
        "    Escribir \"ok\"\n"
        "FinProceso"
    ) == "ok\n"


def test_limpiar_pantalla_is_noop():
    assert out(
        "Proceso P\n"
        "    Limpiar Pantalla\n"
        "    Escribir \"ok\"\n"
        "FinProceso"
    ) == "ok\n"


# ---------------------------------------------------------------------------
# Step counting (SPEC §(g)) — exact counts for small programs
# ---------------------------------------------------------------------------


def test_steps_simple_assignment_and_escribir():
    # x <- 5 (1) + Escribir x (1 stmt + 1 arg) = 3
    result = run_ok("Proceso P\n    x <- 5\n    Escribir x\nFinProceso")
    assert result.steps == 3


def test_steps_sum_of_n_mientras():
    src = (
        "Proceso P\n"
        "    n <- 3\n"
        "    s <- 0\n"
        "    i <- 1\n"
        "    Mientras i <= n Hacer\n"
        "        s <- s + i\n"
        "        i <- i + 1\n"
        "    FinMientras\n"
        "    Escribir s\n"
        "FinProceso"
    )
    # 3 assigns (3) + Mientras stmt (1) + 3 iters x (check 1+op 1 + body 2+2)
    # + final false check (2) + Escribir (2) = 26
    result = run_ok(src)
    assert result.steps == 26
    assert result.output == "6\n"


def test_steps_para_loop():
    src = (
        "Proceso P\n"
        "    s <- 0\n"
        "    Para i <- 1 Hasta 3\n"
        "        s <- s + i\n"
        "    FinPara\n"
        "    Escribir s\n"
        "FinProceso"
    )
    # s <- 0 (1) + Para entry (1) + 3 iters x (check 1 + body 2 + inc 1)
    # + final failing check (1) + Escribir (2) = 17
    result = run_ok(src)
    assert result.steps == 17
    assert result.output == "6\n"


def test_steps_si():
    src = (
        "Proceso P\n"
        "    x <- 5\n"
        "    Si x > 3 Entonces\n"
        "        Escribir \"grande\"\n"
        "    Sino\n"
        "        Escribir \"chico\"\n"
        "    FinSi\n"
        "FinProceso"
    )
    # x <- 5 (1) + Si stmt (1) + cond (1 + op 1) + Escribir (2) = 6
    result = run_ok(src)
    assert result.steps == 6


def test_steps_segun():
    src = (
        "Proceso P\n"
        "    x <- 2\n"
        "    Segun x Hacer\n"
        "        1: Escribir \"uno\"\n"
        "        2: Escribir \"dos\"\n"
        "        De Otro Modo: Escribir \"otro\"\n"
        "    FinSegun\n"
        "FinProceso"
    )
    # x <- 2 (1) + Segun stmt (1) + case 1 check (1) + case 2 check (1)
    # + Escribir (2) = 6
    result = run_ok(src)
    assert result.steps == 6


def test_steps_repetir():
    src = (
        "Proceso P\n"
        "    i <- 1\n"
        "    Repetir\n"
        "        Escribir i\n"
        "        i <- i + 1\n"
        "    Hasta Que i > 3\n"
        "FinProceso"
    )
    # i <- 1 (1) + Repetir stmt (1) + 3 iters x (body 4 + cond 1+op 1) = 20
    result = run_ok(src)
    assert result.steps == 20


def test_steps_hacer_mientras_que():
    src = (
        "Proceso P\n"
        "    i <- 1\n"
        "    Hacer\n"
        "        Escribir i\n"
        "        i <- i + 1\n"
        "    Mientras Que i <= 3\n"
        "FinProceso"
    )
    result = run_ok(src)
    assert result.steps == 20


def test_steps_escribir_multi_arg():
    # Escribir (1) + 3 args (3) = 4
    result = run_ok("Proceso P\n    Escribir \"a\", \"b\", \"c\"\nFinProceso")
    assert result.steps == 4


def test_steps_leer():
    # Leer (1) + 2 args (2) = 3
    result = run_ok("Proceso P\n    Leer a, b\nFinProceso", input_text="1 2")
    assert result.steps == 3


def test_steps_esperar():
    result = run_ok("Proceso P\n    Esperar 100\nFinProceso")
    assert result.steps == 1


def test_steps_limpiar_pantalla():
    result = run_ok("Proceso P\n    Limpiar Pantalla\nFinProceso")
    assert result.steps == 1


def test_steps_operator_evaluation():
    # a,b,c assigns (3) + x <- a + b * c (1 stmt + 2 operators) = 6
    src = (
        "Proceso P\n"
        "    a <- 2\n"
        "    b <- 3\n"
        "    c <- 4\n"
        "    x <- a + b * c\n"
        "FinProceso"
    )
    result = run_ok(src)
    assert result.steps == 6
    assert result.output == ""


def test_steps_definir_counts_as_statement():
    # Definir (1) + Definir (1) + 2 assigns (2) + 2 Escribir (4) = 8
    src = (
        "Proceso Ej1\n"
        "    Definir x: Entero\n"
        "    Definir y: Real\n"
        "    x <- 42\n"
        "    y <- 3.14\n"
        "    Escribir x\n"
        "    Escribir y\n"
        "FinProceso"
    )
    result = run_ok(src)
    assert result.steps == 8


# ---------------------------------------------------------------------------
# Runtime errors (SPEC §(i))
# ---------------------------------------------------------------------------


def test_error_carries_line_and_col():
    err = run_err("Proceso P\n    x <- 5 / 0\nFinProceso")
    assert err.code == "ERR_DIV0"
    assert err.line == 2
    assert err.col == 11


def test_error_halts_execution():
    result = run("Proceso P\n    x <- 5 / 0\n    Escribir \"nunca\"\nFinProceso")
    assert result.error is not None
    assert result.error.code == "ERR_DIV0"
    assert result.output == ""


def test_partial_output_preserved_on_error():
    result = run(
        "Proceso P\n"
        "    Escribir \"antes\"\n"
        "    x <- 5 / 0\n"
        "FinProceso"
    )
    assert result.error is not None
    assert result.output == "antes\n"


def test_condition_must_be_logico():
    err = run_err(
        "Proceso P\n    Si 1 Entonces\n        Escribir \"x\"\n    FinSi\nFinProceso"
    )
    assert err.code == "ERR_TYPE"


def test_segun_expr_must_be_entero():
    err = run_err(
        "Proceso P\n    Segun 2.0 Hacer\n"
        "        2: Escribir \"x\"\n    FinSegun\nFinProceso"
    )
    assert err.code == "ERR_TYPE"


# ---------------------------------------------------------------------------
# Recursion depth cap (SPEC §(i) + Diff-from-Official #15: 1000 frames)
# ---------------------------------------------------------------------------
# SubProceso/Funcion execution is todo 6; the cap mechanism is exercised
# directly through the evaluator's frame-entry API.


def test_recursion_cap_allows_1000_frames():
    ev = Evaluator()
    for _ in range(1000):
        ev._enter_frame(Identifier(1, 0, "x"))


def test_recursion_cap_raises_err_recursion_at_1001():
    ev = Evaluator()
    for _ in range(1000):
        ev._enter_frame(Identifier(1, 0, "x"))
    with pytest.raises(RuntimeError) as ei:
        ev._enter_frame(Identifier(1, 0, "x"))
    assert ei.value.code == "ERR_RECURSION"
    assert ei.value.line == 1
    assert ei.value.col == 0


def test_recursion_cap_exit_frame_releases_slot():
    ev = Evaluator()
    for _ in range(1000):
        ev._enter_frame(Identifier(1, 0, "x"))
    ev._exit_frame()
    ev._enter_frame(Identifier(1, 0, "x"))  # no error after releasing one frame


# ---------------------------------------------------------------------------
# Arrays / built-ins / subprocesos (todo 6) — implemented; error paths only
# ---------------------------------------------------------------------------


def test_array_element_assignment_undeclared_is_err_dim():
    err = run_err("Proceso P\n    a[1] <- 5\nFinProceso")
    assert err.code == "ERR_DIM"


def test_array_index_read_undeclared_is_err_dim():
    err = run_err("Proceso P\n    x <- a[1]\nFinProceso")
    assert err.code == "ERR_DIM"


def test_dimension_declares_array():
    result = run_ok("Proceso P\n    Dimension a[10]\n    a[0] <- 1\nFinProceso")
    assert result.error is None


def test_builtin_call_works():
    result = run_ok("Proceso P\n    x <- AZAR(10)\nFinProceso")
    assert result.error is None


def test_subproc_call_undefined_is_err_type():
    err = run_err("Proceso P\n    saludar()\nFinProceso")
    assert err.code == "ERR_TYPE"


def test_subproceso_definition_is_noop():
    result = run_ok(
        "Proceso P\n"
        "    SubProceso saludar\n"
        "        Escribir \"hola\"\n"
        "    FinSubProceso\n"
        "    Escribir \"main\"\n"
        "FinProceso"
    )
    assert result.output == "main\n"


def test_retornar_outside_function_is_err_type():
    err = run_err("Proceso P\n    Retornar 5\nFinProceso")
    assert err.code == "ERR_TYPE"
