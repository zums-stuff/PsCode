"""Tests for the PseInt parser (engine/src/pseint_engine/parser.py).

Covers every statement kind in SPEC §(a), declarations, expression
precedence, flexible-syntax variants, nested structures, error positions
(line/col), reserved-word misuse -> CE, and the token cycle limit.
"""

import pytest

from pseint_engine.ast_nodes import (
    ArrayIndex,
    ArrayLiteral,
    Assignment,
    BinaryOp,
    BooleanLiteral,
    CaseItem,
    Definir,
    Dimension,
    Escribir,
    Esperar,
    FunctionCall,
    HacerMientrasQue,
    Identifier,
    IntegerLiteral,
    Leer,
    LimpiarPantalla,
    Mientras,
    Para,
    ParamDecl,
    Program,
    RealLiteral,
    Redimensionar,
    Repetir,
    Retornar,
    Segun,
    Si,
    StringLiteral,
    SubProcCall,
    SubProceso,
    UnaryOp,
)
from pseint_engine.parser import ParseError, parse


def body(src: str) -> list:
    """Parse a full program and return its body statements."""
    return parse(src).body


def single(src: str):
    """Parse a program with exactly one body statement and return it."""
    stmts = body(src)
    assert len(stmts) == 1, f"expected 1 statement, got {len(stmts)}"
    return stmts[0]


# ---------------------------------------------------------------------------
# Program structure
# ---------------------------------------------------------------------------


def test_minimal_program():
    prog = parse("Proceso x\nFinProceso\n")
    assert isinstance(prog, Program)
    assert prog.name == Identifier(1, 8, "x")
    assert prog.params == []
    assert prog.body == []


def test_program_with_params():
    prog = parse("Proceso x [a, b]\nFinProceso\n")
    assert prog.name == Identifier(1, 8, "x")
    assert prog.params == [
        ParamDecl(Identifier(1, 11, "a")),
        ParamDecl(Identifier(1, 14, "b")),
    ]


def test_program_with_typed_params():
    prog = parse("Proceso x [a: Entero, Por Valor b: Real]\nFinProceso\n")
    assert prog.params == [
        ParamDecl(Identifier(1, 11, "a"), type_name="Entero"),
        ParamDecl(
            Identifier(1, 32, "b"), type_name="Real", direction="Por Valor"
        ),
    ]


def test_program_with_reference_param():
    prog = parse("Proceso x [Por Referencia a]\nFinProceso\n")
    assert prog.params == [
        ParamDecl(Identifier(1, 26, "a"), direction="Por Referencia")
    ]


# ---------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------


def test_definir_with_colon():
    stmt = single("Proceso p\nDefinir x: Entero\nFinProceso\n")
    assert isinstance(stmt, Definir)
    assert stmt.names == [Identifier(2, 8, "x")]
    assert stmt.type_name == "Entero"
    assert stmt.init is None


def test_definir_with_como():
    stmt = single("Proceso p\nDefinir x Como Entero\nFinProceso\n")
    assert isinstance(stmt, Definir)
    assert stmt.names == [Identifier(2, 8, "x")]
    assert stmt.type_name == "Entero"


def test_definir_comma_list_como():
    stmt = single("Proceso p\nDefinir a, b, c Como Entero\nFinProceso\n")
    assert isinstance(stmt, Definir)
    assert stmt.names == [
        Identifier(2, 8, "a"),
        Identifier(2, 11, "b"),
        Identifier(2, 14, "c"),
    ]
    assert stmt.type_name == "Entero"


def test_definir_bare():
    stmt = single("Proceso p\nDefinir x\nFinProceso\n")
    assert isinstance(stmt, Definir)
    assert stmt.names == [Identifier(2, 8, "x")]
    assert stmt.type_name is None
    assert stmt.init is None


def test_definir_with_init():
    stmt = single("Proceso p\nDefinir x: Entero = 5\nFinProceso\n")
    assert isinstance(stmt, Definir)
    assert stmt.type_name == "Entero"
    assert stmt.init == IntegerLiteral(2, 20, 5)


# ---------------------------------------------------------------------------
# Typed declarations (sugar: ``Cadena s`` is ``Assignment(s, None, Cadena)``)
# ---------------------------------------------------------------------------


def test_typed_decl_cadena_no_init():
    """``Cadena s`` parses to a typed-decl Assignment with value=None."""
    stmt = single("Proceso p\nCadena s\nFinProceso\n")
    assert isinstance(stmt, Assignment)
    assert stmt.target == Identifier(2, 7, "s")
    assert stmt.value is None
    assert stmt.type_name == "Cadena"


def test_typed_decl_entero_with_init():
    stmt = single("Proceso p\nEntero i <- 5\nFinProceso\n")
    assert isinstance(stmt, Assignment)
    assert stmt.target == Identifier(2, 7, "i")
    assert stmt.value == IntegerLiteral(2, 12, 5)
    assert stmt.type_name == "Entero"


def test_typed_decl_real_with_init():
    stmt = single("Proceso p\nReal x <- 3.14\nFinProceso\n")
    assert isinstance(stmt, Assignment)
    assert stmt.target == Identifier(2, 5, "x")
    assert stmt.value == RealLiteral(2, 10, 3.14)
    assert stmt.type_name == "Real"


def test_typed_decl_logico_with_init():
    stmt = single("Proceso p\nLogico b <- Verdadero\nFinProceso\n")
    assert isinstance(stmt, Assignment)
    assert stmt.target == Identifier(2, 7, "b")
    assert stmt.value == BooleanLiteral(2, 12, True)
    assert stmt.type_name == "Logico"


def test_typed_decl_caracter_with_init():
    stmt = single('Proceso p\nCaracter c <- "X"\nFinProceso\n')
    assert isinstance(stmt, Assignment)
    assert stmt.target == Identifier(2, 9, "c")
    assert stmt.value == StringLiteral(2, 14, '"X"')
    assert stmt.type_name == "Caracter"


def test_typed_decl_eq_arrow_also_accepted():
    """``Entero i = 5`` is the flexible ``=`` arrow variant."""
    stmt = single("Proceso p\nEntero i = 5\nFinProceso\n")
    assert isinstance(stmt, Assignment)
    assert stmt.target == Identifier(2, 7, "i")
    assert stmt.value == IntegerLiteral(2, 11, 5)
    assert stmt.type_name == "Entero"


def test_typed_decl_lowercase_type_name():
    """Type-name keywords are case-insensitive (lexer normalisation)."""
    stmt = single("Proceso p\ncadena s\nFinProceso\n")
    assert isinstance(stmt, Assignment)
    assert stmt.target == Identifier(2, 7, "s")
    assert stmt.type_name == "cadena"


def test_typed_decl_missing_identifier_is_ce():
    """``Cadena`` alone (no variable name) must be a CE."""
    with pytest.raises(ParseError) as exc:
        parse("Proceso p\nCadena\nFinProceso\n")
    assert exc.value.code == "CE"


def test_typed_decl_missing_identifier_after_type_is_ce():
    """``Entero 5`` (no identifier) must be a CE."""
    with pytest.raises(ParseError) as exc:
        parse("Proceso p\nEntero 5\nFinProceso\n")
    assert exc.value.code == "CE"
    assert exc.value.line == 2


def test_typed_decl_missing_arrow_is_ce():
    """``Real x 3.14`` (no ``<-`` between name and value) must be a CE.

    After consuming ``Real x``, the parser sees ``3.14`` which starts an
    expression — but the typed-decl handler only accepts ``<-`` / ``=``
    after the identifier.  Anything else triggers a CE at that position.
    """
    with pytest.raises(ParseError) as exc:
        parse("Proceso p\nReal x 3.14\nFinProceso\n")
    assert exc.value.code == "CE"


def test_typed_decl_array_form_is_ce():
    """``Cadena arr[3]`` (typed array) is not in the pinned dialect → CE.

    The parser accepts scalar typed-decls only; for arrays the user must
    use the canonical ``Dimension`` / ``Definir`` forms.
    """
    with pytest.raises(ParseError) as exc:
        parse("Proceso p\nCadena arr[3]\nFinProceso\n")
    assert exc.value.code == "CE"
    assert exc.value.line == 2


def test_dimension():
    stmt = single("Proceso p\nDimension arr[10]\nFinProceso\n")
    assert isinstance(stmt, Dimension)
    assert stmt.name == Identifier(2, 10, "arr")
    assert stmt.sizes == [IntegerLiteral(2, 14, 10)]


def test_dimension_multi():
    stmt = single("Proceso p\nDimension arr[3, 4]\nFinProceso\n")
    assert isinstance(stmt, Dimension)
    assert stmt.sizes == [
        IntegerLiteral(2, 14, 3),
        IntegerLiteral(2, 17, 4),
    ]


def test_dimensionar_flexible():
    stmt = single("Proceso p\nDimensionar arr[10]\nFinProceso\n")
    assert isinstance(stmt, Dimension)
    assert stmt.name == Identifier(2, 12, "arr")


def test_redimensionar():
    stmt = single("Proceso p\nRedimensionar arr[5]\nFinProceso\n")
    assert isinstance(stmt, Redimensionar)
    assert stmt.name == Identifier(2, 14, "arr")
    assert stmt.sizes == [IntegerLiteral(2, 18, 5)]


# ---------------------------------------------------------------------------
# Simple statements
# ---------------------------------------------------------------------------


def test_assignment():
    stmt = single("Proceso p\nx <- 5\nFinProceso\n")
    assert isinstance(stmt, Assignment)
    assert stmt.target == Identifier(2, 0, "x")
    assert stmt.value == IntegerLiteral(2, 5, 5)


def test_assignment_expression():
    stmt = single("Proceso p\nx <- a + b * 2\nFinProceso\n")
    assert isinstance(stmt, Assignment)
    assert isinstance(stmt.value, BinaryOp)
    assert stmt.value.op == "+"
    assert stmt.value.left == Identifier(2, 5, "a")
    assert isinstance(stmt.value.right, BinaryOp)
    assert stmt.value.right.op == "*"


def test_leer():
    stmt = single("Proceso p\nLeer x\nFinProceso\n")
    assert isinstance(stmt, Leer)
    assert stmt.args == [Identifier(2, 5, "x")]


def test_leer_bare():
    stmts = body("Proceso p\nLeer\nEscribir x\nFinProceso\n")
    assert len(stmts) == 2
    assert isinstance(stmts[0], Leer)
    assert stmts[0].args == []
    assert isinstance(stmts[1], Escribir)


def test_leer_bare_at_end():
    stmts = body("Proceso p\nLeer\nFinProceso\n")
    assert len(stmts) == 1
    assert isinstance(stmts[0], Leer)
    assert stmts[0].args == []


def test_leer_multiple():
    stmt = single("Proceso p\nLeer x, y, z\nFinProceso\n")
    assert isinstance(stmt, Leer)
    assert stmt.args == [
        Identifier(2, 5, "x"),
        Identifier(2, 8, "y"),
        Identifier(2, 11, "z"),
    ]


def test_escribir():
    stmt = single("Proceso p\nEscribir x\nFinProceso\n")
    assert isinstance(stmt, Escribir)
    assert stmt.args == [Identifier(2, 9, "x")]
    assert stmt.sin_saltar is False


def test_escribir_multiple():
    stmt = single('Proceso p\nEscribir "a", x, 1.5\nFinProceso\n')
    assert isinstance(stmt, Escribir)
    assert stmt.args == [
        StringLiteral(2, 9, '"a"'),
        Identifier(2, 14, "x"),
        RealLiteral(2, 17, 1.5),
    ]


def test_escribir_sin_saltar():
    stmt = single("Proceso p\nEscribir Sin Saltar x\nFinProceso\n")
    assert isinstance(stmt, Escribir)
    assert stmt.sin_saltar is True
    assert stmt.args == [Identifier(2, 20, "x")]


def test_escribir_sin_saltar_lowercase():
    stmt = single("Proceso p\nEscribir sin saltar x\nFinProceso\n")
    assert isinstance(stmt, Escribir)
    assert stmt.sin_saltar is True


def test_escribir_variable_named_sin():
    # "Sin" alone is a valid identifier, not the Sin Saltar modifier.
    stmt = single("Proceso p\nEscribir Sin\nFinProceso\n")
    assert isinstance(stmt, Escribir)
    assert stmt.sin_saltar is False
    assert stmt.args == [Identifier(2, 9, "Sin")]


def test_esperar():
    stmt = single("Proceso p\nEsperar 1000\nFinProceso\n")
    assert isinstance(stmt, Esperar)
    assert stmt.duration == IntegerLiteral(2, 8, 1000)
    assert stmt.milisegundos is False


def test_esperar_milisegundos():
    stmt = single("Proceso p\nEsperar 1000 Milisegundos\nFinProceso\n")
    assert isinstance(stmt, Esperar)
    assert stmt.milisegundos is True


def test_esperar_milisegundo_singular():
    stmt = single("Proceso p\nEsperar 1000 Milisegundo\nFinProceso\n")
    assert isinstance(stmt, Esperar)
    assert stmt.milisegundos is True


def test_limpiar_pantalla():
    stmt = single("Proceso p\nLimpiar Pantalla\nFinProceso\n")
    assert isinstance(stmt, LimpiarPantalla)


def test_retornar():
    stmt = single("Proceso p\nRetornar x + 1\nFinProceso\n")
    assert isinstance(stmt, Retornar)
    assert isinstance(stmt.value, BinaryOp)
    assert stmt.value.op == "+"


# ---------------------------------------------------------------------------
# SubProceso / Funcion
# ---------------------------------------------------------------------------


def test_subproceso():
    stmt = single(
        "Proceso p\nSubProceso foo(x, y)\n  a <- x\nFinSubProceso\nFinProceso\n"
    )
    assert isinstance(stmt, SubProceso)
    assert stmt.name == Identifier(2, 11, "foo")
    assert stmt.params == [
        ParamDecl(Identifier(2, 15, "x")),
        ParamDecl(Identifier(2, 18, "y")),
    ]
    assert stmt.is_function is False
    assert len(stmt.block) == 1
    assert isinstance(stmt.block[0], Assignment)


def test_subproceso_no_params():
    stmt = single("Proceso p\nSubProceso foo\nFinSubProceso\nFinProceso\n")
    assert isinstance(stmt, SubProceso)
    assert stmt.name == Identifier(2, 11, "foo")
    assert stmt.params == []


def test_funcion():
    stmt = single(
        "Proceso p\n"
        "Funcion doble(x): Entero\n"
        "  Retornar x * 2\n"
        "FinFuncion\n"
        "FinProceso\n"
    )
    assert isinstance(stmt, SubProceso)
    assert stmt.is_function is True
    assert stmt.return_type == "Entero"
    assert stmt.params == [ParamDecl(Identifier(2, 14, "x"))]
    assert len(stmt.block) == 1
    assert isinstance(stmt.block[0], Retornar)


def test_subproc_call_with_args():
    stmt = single("Proceso p\nfoo(x, y)\nFinProceso\n")
    assert isinstance(stmt, SubProcCall)
    assert stmt.name == "foo"
    assert stmt.args == [Identifier(2, 4, "x"), Identifier(2, 7, "y")]


def test_subproc_call_no_args():
    stmt = single("Proceso p\nfoo\nFinProceso\n")
    assert isinstance(stmt, SubProcCall)
    assert stmt.name == "foo"
    assert stmt.args == []


def test_subproc_call_empty_parens():
    stmt = single("Proceso p\nfoo()\nFinProceso\n")
    assert isinstance(stmt, SubProcCall)
    assert stmt.name == "foo"
    assert stmt.args == []


# ---------------------------------------------------------------------------
# Control flow
# ---------------------------------------------------------------------------


def test_si_simple():
    stmt = single("Proceso p\nSi x > 0 Entonces\n  y <- 1\nFinSi\nFinProceso\n")
    assert isinstance(stmt, Si)
    assert isinstance(stmt.condition, BinaryOp)
    assert stmt.condition.op == ">"
    assert len(stmt.then_block) == 1
    assert isinstance(stmt.then_block[0], Assignment)
    assert stmt.else_block == []


def test_si_sino():
    stmt = single(
        "Proceso p\n"
        "Si x > 0 Entonces\n"
        "  y <- 1\n"
        "SiNo\n"
        "  y <- 2\n"
        "FinSi\n"
        "FinProceso\n"
    )
    assert isinstance(stmt, Si)
    assert len(stmt.then_block) == 1
    assert len(stmt.else_block) == 1
    assert isinstance(stmt.else_block[0], Assignment)


def test_si_sino_synonym():
    # "Sino" (without capital N) is a synonym for "SiNo".
    stmt = single(
        "Proceso p\n"
        "Si x > 0 Entonces\n"
        "  y <- 1\n"
        "Sino\n"
        "  y <- 2\n"
        "FinSi\n"
        "FinProceso\n"
    )
    assert isinstance(stmt, Si)
    assert len(stmt.else_block) == 1


def test_segun():
    stmt = single(
        "Proceso p\n"
        "Segun x Hacer\n"
        "  1: y <- 10\n"
        "  2: y <- 20\n"
        "FinSegun\n"
        "FinProceso\n"
    )
    assert isinstance(stmt, Segun)
    assert stmt.expr == Identifier(2, 6, "x")
    assert stmt.cases == [
        CaseItem(1, [Assignment(3, 5, Identifier(3, 5, "y"), IntegerLiteral(3, 10, 10))]),
        CaseItem(2, [Assignment(4, 5, Identifier(4, 5, "y"), IntegerLiteral(4, 10, 20))]),
    ]


def test_segun_de_otro_modo():
    stmt = single(
        "Proceso p\n"
        "Segun x Hacer\n"
        "  1: y <- 10\n"
        "  De Otro Modo: y <- 99\n"
        "FinSegun\n"
        "FinProceso\n"
    )
    assert isinstance(stmt, Segun)
    assert len(stmt.cases) == 2
    assert stmt.cases[0].label == 1
    assert stmt.cases[1].label is None  # default case


def test_segun_otherwise():
    stmt = single(
        "Proceso p\n"
        "Segun x Hacer\n"
        "  1: y <- 10\n"
        "  Otherwise: y <- 99\n"
        "FinSegun\n"
        "FinProceso\n"
    )
    assert isinstance(stmt, Segun)
    assert stmt.cases[1].label is None


def test_mientras():
    stmt = single(
        "Proceso p\n"
        "Mientras x > 0 Hacer\n"
        "  x <- x - 1\n"
        "FinMientras\n"
        "FinProceso\n"
    )
    assert isinstance(stmt, Mientras)
    assert isinstance(stmt.condition, BinaryOp)
    assert stmt.condition.op == ">"
    assert len(stmt.block) == 1


def test_repetir():
    stmt = single(
        "Proceso p\nRepetir\n  x <- x + 1\nHasta Que x > 10\nFinProceso\n"
    )
    assert isinstance(stmt, Repetir)
    assert len(stmt.block) == 1
    assert isinstance(stmt.condition, BinaryOp)
    assert stmt.condition.op == ">"


def test_para():
    stmt = single(
        "Proceso p\nPara i <- 1 Hasta 10\n  s <- s + i\nFinPara\nFinProceso\n"
    )
    assert isinstance(stmt, Para)
    assert stmt.var == Identifier(2, 5, "i")
    assert stmt.start == IntegerLiteral(2, 10, 1)
    assert stmt.end == IntegerLiteral(2, 18, 10)
    assert stmt.step is None
    assert len(stmt.block) == 1


def test_para_con_paso():
    stmt = single(
        "Proceso p\n"
        "Para i <- 1 Hasta 10 Con Paso 2\n"
        "  s <- s + i\n"
        "FinPara\n"
        "FinProceso\n"
    )
    assert isinstance(stmt, Para)
    assert stmt.step == IntegerLiteral(2, 30, 2)


def test_para_with_step():
    stmt = single(
        "Proceso p\n"
        "Para i <- 1 Hasta 10 With step 2\n"
        "  s <- s + i\n"
        "FinPara\n"
        "FinProceso\n"
    )
    assert isinstance(stmt, Para)
    assert stmt.step == IntegerLiteral(2, 31, 2)


def test_hacer_mientras_que():
    stmt = single(
        "Proceso p\nHacer\n  x <- x + 1\nMientras Que x < 10\nFinProceso\n"
    )
    assert isinstance(stmt, HacerMientrasQue)
    assert len(stmt.block) == 1
    assert isinstance(stmt.condition, BinaryOp)
    assert stmt.condition.op == "<"


# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------


def test_integer_literal():
    stmt = single("Proceso p\nx <- 42\nFinProceso\n")
    assert stmt.value == IntegerLiteral(2, 5, 42)


def test_real_literal():
    stmt = single("Proceso p\nx <- 3.14\nFinProceso\n")
    assert stmt.value == RealLiteral(2, 5, 3.14)


def test_string_literal():
    stmt = single('Proceso p\nx <- "hola"\nFinProceso\n')
    assert stmt.value == StringLiteral(2, 5, '"hola"')


def test_boolean_literals():
    stmt = single("Proceso p\nx <- Verdadero\nFinProceso\n")
    assert stmt.value == BooleanLiteral(2, 5, True)
    stmt = single("Proceso p\nx <- Falso\nFinProceso\n")
    assert stmt.value == BooleanLiteral(2, 5, False)


def test_identifier_expr():
    stmt = single("Proceso p\nx <- y\nFinProceso\n")
    assert stmt.value == Identifier(2, 5, "y")


def test_binary_ops():
    stmt = single("Proceso p\nx <- a + b - c\nFinProceso\n")
    assert isinstance(stmt.value, BinaryOp)
    assert stmt.value.op == "-"
    assert isinstance(stmt.value.left, BinaryOp)
    assert stmt.value.left.op == "+"


def test_multiplicative_precedence():
    stmt = single("Proceso p\nx <- a + b * c\nFinProceso\n")
    assert stmt.value.op == "+"
    assert isinstance(stmt.value.right, BinaryOp)
    assert stmt.value.right.op == "*"


def test_relational_precedence():
    stmt = single("Proceso p\nx <- a < b & c > d\nFinProceso\n")
    assert stmt.value.op == "&"
    assert isinstance(stmt.value.left, BinaryOp)
    assert stmt.value.left.op == "<"
    assert isinstance(stmt.value.right, BinaryOp)
    assert stmt.value.right.op == ">"


def test_power_right_associative():
    stmt = single("Proceso p\nx <- 2 ^ 3 ^ 2\nFinProceso\n")
    assert stmt.value.op == "^"
    assert stmt.value.left == IntegerLiteral(2, 5, 2)
    assert isinstance(stmt.value.right, BinaryOp)
    assert stmt.value.right.op == "^"
    assert stmt.value.right.left == IntegerLiteral(2, 9, 3)


def test_unary_minus():
    stmt = single("Proceso p\nx <- -5\nFinProceso\n")
    assert isinstance(stmt.value, UnaryOp)
    assert stmt.value.op == "-"
    assert stmt.value.operand == IntegerLiteral(2, 6, 5)


def test_unary_plus():
    stmt = single("Proceso p\nx <- +5\nFinProceso\n")
    assert isinstance(stmt.value, UnaryOp)
    assert stmt.value.op == "+"


def test_unary_not():
    stmt = single("Proceso p\nx <- ~y\nFinProceso\n")
    assert isinstance(stmt.value, UnaryOp)
    assert stmt.value.op == "~"
    assert stmt.value.operand == Identifier(2, 6, "y")


def test_logical_or():
    stmt = single("Proceso p\nx <- a | b\nFinProceso\n")
    assert isinstance(stmt.value, BinaryOp)
    assert stmt.value.op == "|"


def test_logical_and():
    stmt = single("Proceso p\nx <- a & b\nFinProceso\n")
    assert isinstance(stmt.value, BinaryOp)
    assert stmt.value.op == "&"


def test_equality_alias_eq():
    stmt = single("Proceso p\nx <- a = b\nFinProceso\n")
    assert isinstance(stmt.value, BinaryOp)
    assert stmt.value.op == "="


def test_equality_alias_eqeq():
    stmt = single("Proceso p\nx <- a == b\nFinProceso\n")
    assert isinstance(stmt.value, BinaryOp)
    assert stmt.value.op == "=="


def test_relational_ops():
    for op in ("<", ">", "<>", "<=", ">="):
        stmt = single(f"Proceso p\nx <- a {op} b\nFinProceso\n")
        assert isinstance(stmt.value, BinaryOp)
        assert stmt.value.op == op


def test_modulo_percent():
    stmt = single("Proceso p\nx <- a % b\nFinProceso\n")
    assert isinstance(stmt.value, BinaryOp)
    assert stmt.value.op == "%"


def test_modulo_mod_keyword():
    stmt = single("Proceso p\nx <- a MOD b\nFinProceso\n")
    assert isinstance(stmt.value, BinaryOp)
    assert stmt.value.op == "MOD"


def test_parenthesized_expr():
    stmt = single("Proceso p\nx <- (a + b) * c\nFinProceso\n")
    assert stmt.value.op == "*"
    assert isinstance(stmt.value.left, BinaryOp)
    assert stmt.value.left.op == "+"


def test_function_call_expr():
    stmt = single("Proceso p\nx <- abs(y)\nFinProceso\n")
    assert isinstance(stmt.value, FunctionCall)
    assert stmt.value.name == "abs"
    assert stmt.value.args == [Identifier(2, 9, "y")]


def test_function_call_no_args():
    stmt = single("Proceso p\nx <- azar()\nFinProceso\n")
    assert isinstance(stmt.value, FunctionCall)
    assert stmt.value.name == "azar"
    assert stmt.value.args == []


def test_array_index():
    stmt = single("Proceso p\nx <- arr[3]\nFinProceso\n")
    assert isinstance(stmt.value, ArrayIndex)
    assert stmt.value.array == Identifier(2, 5, "arr")
    assert stmt.value.index == IntegerLiteral(2, 9, 3)


def test_array_index_multi_dim_expression():
    stmt = single("Proceso p\nx <- a[1, 2]\nFinProceso\n")
    assert isinstance(stmt.value, ArrayIndex)
    assert stmt.value.array == Identifier(2, 5, "a")
    assert stmt.value.index == IntegerLiteral(2, 7, 1)
    assert stmt.value.indices == [IntegerLiteral(2, 10, 2)]


def test_array_element_assignment():
    stmt = single("Proceso p\na[1] <- 5\nFinProceso\n")
    assert isinstance(stmt, Assignment)
    assert isinstance(stmt.target, ArrayIndex)
    assert stmt.target.array == Identifier(2, 0, "a")
    assert stmt.target.index == IntegerLiteral(2, 2, 1)
    assert stmt.target.indices == []
    assert stmt.value == IntegerLiteral(2, 8, 5)


def test_array_element_assignment_multi_dim():
    stmt = single("Proceso p\na[1, 2] <- 5\nFinProceso\n")
    assert isinstance(stmt, Assignment)
    assert isinstance(stmt.target, ArrayIndex)
    assert stmt.target.array == Identifier(2, 0, "a")
    assert stmt.target.index == IntegerLiteral(2, 2, 1)
    assert stmt.target.indices == [IntegerLiteral(2, 5, 2)]
    assert stmt.value == IntegerLiteral(2, 11, 5)


def test_array_element_assignment_expression_index():
    stmt = single("Proceso p\na[i + 1] <- x * 2\nFinProceso\n")
    assert isinstance(stmt, Assignment)
    assert isinstance(stmt.target, ArrayIndex)
    assert isinstance(stmt.target.index, BinaryOp)
    assert stmt.target.index.op == "+"
    assert isinstance(stmt.value, BinaryOp)
    assert stmt.value.op == "*"


def test_array_element_assignment_in_nested():
    stmt = single(
        "Proceso p\n"
        "Si x > 0 Entonces\n"
        "  a[1] <- 5\n"
        "FinSi\n"
        "FinProceso\n"
    )
    assert isinstance(stmt, Si)
    assert isinstance(stmt.then_block[0], Assignment)
    assert isinstance(stmt.then_block[0].target, ArrayIndex)


def test_array_index_expression():
    stmt = single("Proceso p\nx <- arr[i + 1]\nFinProceso\n")
    assert isinstance(stmt.value, ArrayIndex)
    assert isinstance(stmt.value.index, BinaryOp)
    assert stmt.value.index.op == "+"


def test_array_literal():
    stmt = single("Proceso p\nx <- [1, 2, 3]\nFinProceso\n")
    assert isinstance(stmt.value, ArrayLiteral)
    assert stmt.value.elements == [
        IntegerLiteral(2, 6, 1),
        IntegerLiteral(2, 9, 2),
        IntegerLiteral(2, 12, 3),
    ]


def test_builtin_function_call():
    stmt = single("Proceso p\nx <- subcadena(s, 1, 3)\nFinProceso\n")
    assert isinstance(stmt.value, FunctionCall)
    assert stmt.value.name == "subcadena"
    assert len(stmt.value.args) == 3


# ---------------------------------------------------------------------------
# Nested structures
# ---------------------------------------------------------------------------


def test_si_inside_mientras():
    stmt = single(
        "Proceso p\n"
        "Mientras x > 0 Hacer\n"
        "  Si x > 5 Entonces\n"
        "    x <- x - 1\n"
        "  FinSi\n"
        "FinMientras\n"
        "FinProceso\n"
    )
    assert isinstance(stmt, Mientras)
    assert len(stmt.block) == 1
    assert isinstance(stmt.block[0], Si)


def test_mientras_inside_para():
    stmt = single(
        "Proceso p\n"
        "Para i <- 1 Hasta 10\n"
        "  Mientras j > 0 Hacer\n"
        "    j <- j - 1\n"
        "  FinMientras\n"
        "FinPara\n"
        "FinProceso\n"
    )
    assert isinstance(stmt, Para)
    assert len(stmt.block) == 1
    assert isinstance(stmt.block[0], Mientras)


def test_segun_inside_si():
    stmt = single(
        "Proceso p\n"
        "Si x > 0 Entonces\n"
        "  Segun x Hacer\n"
        "    1: y <- 1\n"
        "  FinSegun\n"
        "FinSi\n"
        "FinProceso\n"
    )
    assert isinstance(stmt, Si)
    assert len(stmt.then_block) == 1
    assert isinstance(stmt.then_block[0], Segun)


def test_deep_nesting():
    stmt = single(
        "Proceso p\n"
        "Para i <- 1 Hasta 10\n"
        "  Mientras j > 0 Hacer\n"
        "    Si j > 5 Entonces\n"
        "      Repetir\n"
        "        j <- j - 1\n"
        "      Hasta Que j < 3\n"
        "    FinSi\n"
        "  FinMientras\n"
        "FinPara\n"
        "FinProceso\n"
    )
    assert isinstance(stmt, Para)
    assert isinstance(stmt.block[0], Mientras)
    assert isinstance(stmt.block[0].block[0], Si)
    assert isinstance(stmt.block[0].block[0].then_block[0], Repetir)


def test_si_inside_si_else():
    stmt = single(
        "Proceso p\n"
        "Si x > 0 Entonces\n"
        "  y <- 1\n"
        "SiNo\n"
        "  Si x < 0 Entonces\n"
        "    y <- -1\n"
        "  SiNo\n"
        "    y <- 0\n"
        "  FinSi\n"
        "FinSi\n"
        "FinProceso\n"
    )
    assert isinstance(stmt, Si)
    assert len(stmt.else_block) == 1
    assert isinstance(stmt.else_block[0], Si)


# ---------------------------------------------------------------------------
# Error positions
# ---------------------------------------------------------------------------


def test_error_missing_finsi():
    with pytest.raises(ParseError) as exc:
        parse("Proceso p\nSi x > 0 Entonces\n  y <- 1\nFinProceso\n")
    assert exc.value.code == "CE"
    assert exc.value.line == 2  # the opening Si
    assert exc.value.col == 0


def test_error_missing_finmientras():
    with pytest.raises(ParseError) as exc:
        parse("Proceso p\nMientras x > 0 Hacer\n  x <- x - 1\nFinProceso\n")
    assert exc.value.code == "CE"
    assert exc.value.line == 2
    assert exc.value.col == 0


def test_error_missing_finpara():
    with pytest.raises(ParseError) as exc:
        parse("Proceso p\nPara i <- 1 Hasta 10\n  s <- s + i\nFinProceso\n")
    assert exc.value.code == "CE"
    assert exc.value.line == 2
    assert exc.value.col == 0


def test_error_missing_finsegun():
    with pytest.raises(ParseError) as exc:
        parse("Proceso p\nSegun x Hacer\n  1: y <- 1\nFinProceso\n")
    assert exc.value.code == "CE"
    assert exc.value.line == 2
    assert exc.value.col == 0


def test_error_missing_finsubproceso():
    with pytest.raises(ParseError) as exc:
        parse("Proceso p\nSubProceso foo\n  a <- 1\nFinProceso\n")
    assert exc.value.code == "CE"
    assert exc.value.line == 2
    assert exc.value.col == 0

def test_error_unexpected_token():
    # After '+' the parser expects an operand; the next token is FinProceso.
    with pytest.raises(ParseError) as exc:
        parse("Proceso p\nx <- 5 +\nFinProceso\n")
    assert exc.value.code == "CE"
    assert exc.value.line == 3
    assert exc.value.col == 0


def test_error_unexpected_token_position():
    # ')' is lexically valid but cannot start a statement.
    with pytest.raises(ParseError) as exc:
        parse("Proceso p\nx <- 5 )\nFinProceso\n")
    assert exc.value.code == "CE"


def test_error_missing_proceso():
    with pytest.raises(ParseError) as exc:
        parse("x <- 5\n")
    assert exc.value.code == "CE"
    assert exc.value.line == 1
    assert exc.value.col == 0


def test_error_missing_finproceso():
    with pytest.raises(ParseError) as exc:
        parse("Proceso p\nx <- 5\n")
    assert exc.value.code == "CE"
    assert exc.value.line == 1
    assert exc.value.col == 0


# ---------------------------------------------------------------------------
# Reserved-word misuse -> CE
# ---------------------------------------------------------------------------


def test_reserved_word_as_assignment_target():
    with pytest.raises(ParseError) as exc:
        parse("Proceso p\nSi <- 5\nFinProceso\n")
    assert exc.value.code == "CE"
    assert exc.value.line == 2
    assert exc.value.col == 0


def test_reserved_word_mientras_as_target():
    with pytest.raises(ParseError) as exc:
        parse("Proceso p\nMientras <- 5\nFinProceso\n")
    assert exc.value.code == "CE"


def test_reserved_word_as_proceso_name():
    with pytest.raises(ParseError) as exc:
        parse("Proceso Si\nFinProceso\n")
    assert exc.value.code == "CE"


def test_reserved_word_in_definir():
    with pytest.raises(ParseError) as exc:
        parse("Proceso p\nDefinir Si Como Entero\nFinProceso\n")
    assert exc.value.code == "CE"


# ---------------------------------------------------------------------------
# Cycle limit
# ---------------------------------------------------------------------------


def test_cycle_limit_fails_fast():
    # A single statement consuming >1000 tokens trips the fail-fast guard.
    src = "Proceso p\nx <- " + " + ".join(["1"] * 2000) + "\nFinProceso\n"
    with pytest.raises(ParseError) as exc:
        parse(src)
    assert exc.value.code == "CE"


# ---------------------------------------------------------------------------
# Misc / robustness
# ---------------------------------------------------------------------------


def test_comments_ignored():
    stmt = single("Proceso p\n// comentario\nx <- 5 // otro\nFinProceso\n")
    assert isinstance(stmt, Assignment)


def test_multiple_statements():
    stmts = body(
        "Proceso p\n"
        "a <- 1\n"
        "b <- 2\n"
        "Escribir a\n"
        "Leer c\n"
        "FinProceso\n"
    )
    assert len(stmts) == 4
    assert isinstance(stmts[0], Assignment)
    assert isinstance(stmts[1], Assignment)
    assert isinstance(stmts[2], Escribir)
    assert isinstance(stmts[3], Leer)


def test_escribir_string_with_spaces():
    stmt = single('Proceso p\nEscribir "hola mundo"\nFinProceso\n')
    assert isinstance(stmt, Escribir)
    assert stmt.args == [StringLiteral(2, 9, '"hola mundo"')]


def test_identifier_with_accents():
    stmt = single("Proceso p\nniño <- año\nFinProceso\n")
    assert isinstance(stmt, Assignment)
    assert stmt.target == Identifier(2, 0, "niño")
    assert stmt.value == Identifier(2, 8, "año")


def test_parse_error_has_code_message_line_col():
    with pytest.raises(ParseError) as exc:
        parse("Proceso p\nx <- 5 +\nFinProceso\n")
    err = exc.value
    assert err.code == "CE"
    assert isinstance(err.message, str) and len(err.message) > 0
    assert isinstance(err.line, int)
    assert isinstance(err.col, int)