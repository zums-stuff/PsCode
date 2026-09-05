"""Tests for the PseInt lexer (engine/src/pseint_engine/lexer.py).

Covers every row of the SPEC keyword table + flexible synonyms, identifiers
with accents/eñe, 20+ string/number edge cases, operator tokens, comment
skipping, and error positions (line/col).
"""

import pytest

from pseint_engine.lexer import LexError, Token, TokenType, tokenize


def types(source):
    """Return the list of token types for a source string (excluding EOF)."""
    return [t.type for t in tokenize(source) if t.type is not TokenType.EOF]


def values(source):
    """Return the list of token values for a source string (excluding EOF)."""
    return [t.value for t in tokenize(source) if t.type is not TokenType.EOF]


# ---------------------------------------------------------------------------
# Keyword table: every row of SPEC §(b) + flexible synonyms + MOD operator.
# ---------------------------------------------------------------------------

KEYWORD_CASES = [
    # Reserved keywords (SPEC §(b) table)
    ("Proceso", TokenType.PROCESO),
    ("FinProceso", TokenType.FINPROCESO),
    ("Definir", TokenType.DEFINIR),
    ("Dimension", TokenType.DIMENSION),
    ("Redimensionar", TokenType.REDIMENSIONAR),
    ("Leer", TokenType.LEER),
    ("Escribir", TokenType.ESCRIBIR),
    ("Si", TokenType.SI),
    ("Entonces", TokenType.ENTONCES),
    ("SiNo", TokenType.SINO),
    ("FinSi", TokenType.FINSI),
    ("Segun", TokenType.SEGUN),
    ("Hacer", TokenType.HACER),
    ("FinSegun", TokenType.FINSEGUN),
    ("De Otro Modo", TokenType.DE_OTRO_MODO),
    ("Mientras", TokenType.MIENTRAS),
    ("FinMientras", TokenType.FINMIENTRAS),
    ("Repetir", TokenType.REPETIR),
    ("Hasta Que", TokenType.HASTA_QUE),
    ("Para", TokenType.PARA),
    ("Con Paso", TokenType.CON_PASO),
    ("FinPara", TokenType.FINPARA),
    ("Esperar", TokenType.ESPERAR),
    ("Milisegundos", TokenType.MILISEGUNDOS),
    ("Limpiar Pantalla", TokenType.LIMPIAR_PANTALLA),
    ("Retornar", TokenType.RETORNAR),
    ("SubProceso", TokenType.SUBPROCESO),
    ("Funcion", TokenType.FUNCION),
    ("FinSubProceso", TokenType.FINSUBPROCESO),
    ("FinFuncion", TokenType.FINFUNCION),
    ("Por Referencia", TokenType.POR_REFERENCIA),
    ("Por Valor", TokenType.POR_VALOR),
    # Logical constants
    ("Verdadero", TokenType.VERDADERO),
    ("Falso", TokenType.FALSO),
    # Built-in functions
    ("AZAR", TokenType.AZAR),
    ("RC", TokenType.RC),
    ("ABS", TokenType.ABS),
    ("LN", TokenType.LN),
    ("EXP", TokenType.EXP),
    ("SEN", TokenType.SEN),
    ("COS", TokenType.COS),
    ("ATAN", TokenType.ATAN),
    ("TRUNC", TokenType.TRUNC),
    ("REDON", TokenType.REDON),
    ("LARGO", TokenType.LARGO),
    ("SUBCADENA", TokenType.SUBCADENA),
    ("CONCATENAR", TokenType.CONCATENAR),
    ("MAYUSCULARES", TokenType.MAYUSCULARES),
    ("MINUSCULAS", TokenType.MINUSCULAS),
    ("FechaActual", TokenType.FECHA_ACTUAL),
    ("HoraActual", TokenType.HORA_ACTUAL),
    # Flexible-syntax synonyms (SPEC §(b) synonyms table)
    ("Dimensionar", TokenType.DIMENSION),
    ("Sino", TokenType.SINO),
    ("Otherwise", TokenType.DE_OTRO_MODO),
    ("With step", TokenType.CON_PASO),
    ("Milisegundo", TokenType.MILISEGUNDOS),
    # MOD multiplicative operator
    ("MOD", TokenType.MOD),
]


@pytest.mark.parametrize("source,expected", KEYWORD_CASES)
def test_keyword_table(source, expected):
    assert types(source) == [expected]


# Case-insensitivity of keywords.
@pytest.mark.parametrize(
    "source,expected",
    [
        ("proceso", TokenType.PROCESO),
        ("PROCESO", TokenType.PROCESO),
        ("ProCeSo", TokenType.PROCESO),
        ("mientras", TokenType.MIENTRAS),
        ("MIENTRAS", TokenType.MIENTRAS),
        ("hasta que", TokenType.HASTA_QUE),
        ("HASTA QUE", TokenType.HASTA_QUE),
        ("Hasta Que", TokenType.HASTA_QUE),
        ("con paso", TokenType.CON_PASO),
        ("CON PASO", TokenType.CON_PASO),
        ("de otro modo", TokenType.DE_OTRO_MODO),
        ("DE OTRO MODO", TokenType.DE_OTRO_MODO),
        ("por referencia", TokenType.POR_REFERENCIA),
        ("por valor", TokenType.POR_VALOR),
        ("limpiar pantalla", TokenType.LIMPIAR_PANTALLA),
        ("mod", TokenType.MOD),
        ("Mod", TokenType.MOD),
    ],
)
def test_keyword_case_insensitive(source, expected):
    assert types(source) == [expected]


# Multi-word keywords are recognized as a single token, value preserves spelling.
@pytest.mark.parametrize(
    "source,expected_type,expected_value",
    [
        ("Hasta Que", TokenType.HASTA_QUE, "Hasta Que"),
        ("hasta que", TokenType.HASTA_QUE, "hasta que"),
        ("Con Paso", TokenType.CON_PASO, "Con Paso"),
        ("De Otro Modo", TokenType.DE_OTRO_MODO, "De Otro Modo"),
        ("Por Referencia", TokenType.POR_REFERENCIA, "Por Referencia"),
        ("Por Valor", TokenType.POR_VALOR, "Por Valor"),
        ("Limpiar Pantalla", TokenType.LIMPIAR_PANTALLA, "Limpiar Pantalla"),
        ("With step", TokenType.CON_PASO, "With step"),
    ],
)
def test_multiword_keyword_single_token(source, expected_type, expected_value):
    toks = tokenize(source)
    non_eof = [t for t in toks if t.type is not TokenType.EOF]
    assert len(non_eof) == 1
    assert non_eof[0].type == expected_type
    assert non_eof[0].value == expected_value


# "Hasta" alone (Para upper bound) is distinct from "Hasta Que" (Repetir).
def test_hasta_alone_is_distinct_from_hasta_que():
    assert types("Hasta") == [TokenType.HASTA]
    assert types("Hasta Que") == [TokenType.HASTA_QUE]


# Reserved keyword cannot be used as an identifier.
@pytest.mark.parametrize(
    "source,expected",
    [
        ("Proceso", TokenType.PROCESO),
        ("Si", TokenType.SI),
        ("Mientras", TokenType.MIENTRAS),
        ("AZAR", TokenType.AZAR),
        ("Verdadero", TokenType.VERDADERO),
    ],
)
def test_reserved_word_not_identifier(source, expected):
    assert types(source) == [expected]


# ---------------------------------------------------------------------------
# Identifiers: case-sensitive, accents/eñe allowed, distinct spellings.
# ---------------------------------------------------------------------------

IDENTIFIER_CASES = [
    "nombre",
    "Nombre",
    "x",
    "contador",
    "suma_total",
    "a1",
    "año",
    "Año",
    "Árbol",
    "niño",
    "mañana",
    "café",
    "índice",
    "último",
    "Ñandú",
    "variable_ñ",
    "x2_y3",
]


@pytest.mark.parametrize("source", IDENTIFIER_CASES)
def test_identifier(source):
    assert types(source) == [TokenType.IDENTIFIER]
    assert values(source) == [source]


def test_identifiers_are_case_sensitive():
    assert values("nombre") == ["nombre"]
    assert values("Nombre") == ["Nombre"]
    assert values("NOMBRE") == ["NOMBRE"]


def test_accented_vs_non_accented_are_distinct():
    assert values("año") == ["año"]
    assert values("ano") == ["ano"]
    assert values("año") != values("ano")


def test_identifier_value_preserves_original_spelling():
    toks = tokenize("MiVariable")
    assert toks[0].value == "MiVariable"


# ---------------------------------------------------------------------------
# Numbers: integers, reals, edge cases.
# ---------------------------------------------------------------------------

NUMBER_CASES = [
    ("0", TokenType.INTEGER, "0"),
    ("1", TokenType.INTEGER, "1"),
    ("42", TokenType.INTEGER, "42"),
    ("007", TokenType.INTEGER, "007"),
    ("12345678901234567890", TokenType.INTEGER, "12345678901234567890"),
    ("0.0", TokenType.REAL, "0.0"),
    ("1.5", TokenType.REAL, "1.5"),
    ("3.14", TokenType.REAL, "3.14"),
    ("0.5", TokenType.REAL, "0.5"),
    ("10.0", TokenType.REAL, "10.0"),
    ("123.456", TokenType.REAL, "123.456"),
]


@pytest.mark.parametrize("source,expected_type,expected_value", NUMBER_CASES)
def test_number(source, expected_type, expected_value):
    assert types(source) == [expected_type]
    assert values(source) == [expected_value]


def test_number_followed_by_identifier():
    # "123abc" -> INTEGER 123 then IDENTIFIER abc (maximal munch on digits).
    assert types("123abc") == [TokenType.INTEGER, TokenType.IDENTIFIER]


def test_number_followed_by_operator():
    assert types("1+2") == [TokenType.INTEGER, TokenType.PLUS, TokenType.INTEGER]
    assert types("1.5*2") == [TokenType.REAL, TokenType.STAR, TokenType.INTEGER]


# ---------------------------------------------------------------------------
# Strings: double and single quotes, escapes, edge cases.
# ---------------------------------------------------------------------------

STRING_CASES = [
    ('"hola"', '"hola"'),
    ("'hola'", "'hola'"),
    ('""', '""'),
    ("''", "''"),
    ('"a b c"', '"a b c"'),
    ('"123"', '"123"'),
    ('"con espacios  y  dobles"', '"con espacios  y  dobles"'),
    ('"con,comas"', '"con,comas"'),
    ('"paréntesis (x)"', '"paréntesis (x)"'),
    ('"línea \\"entre comillas\\""', '"línea \\"entre comillas\\""'),
    ("'it\\'s'", "'it\\'s'"),
    ('"backslash \\\\ ok"', '"backslash \\\\ ok"'),
    ('"ñandú café"', '"ñandú café"'),
    ('"año"', '"año"'),
]


@pytest.mark.parametrize("source,expected_value", STRING_CASES)
def test_string(source, expected_value):
    assert types(source) == [TokenType.STRING]
    assert values(source) == [expected_value]


def test_string_does_not_terminate_on_escaped_quote():
    # The escaped quote must not end the string.
    toks = tokenize('"a\\"b"')
    assert [t.type for t in toks if t.type is not TokenType.EOF] == [TokenType.STRING]


def test_string_then_identifier():
    assert types('"hola" mundo') == [TokenType.STRING, TokenType.IDENTIFIER]


# ---------------------------------------------------------------------------
# Operators.
# ---------------------------------------------------------------------------

OPERATOR_CASES = [
    ("<-", TokenType.ASSIGN),
    ("=", TokenType.EQ),
    ("==", TokenType.EQEQ),
    ("<>", TokenType.NEQ),
    ("<", TokenType.LT),
    (">", TokenType.GT),
    ("<=", TokenType.LE),
    (">=", TokenType.GE),
    ("+", TokenType.PLUS),
    ("-", TokenType.MINUS),
    ("*", TokenType.STAR),
    ("/", TokenType.SLASH),
    ("^", TokenType.CARET),
    ("%", TokenType.PERCENT),
    ("&", TokenType.AND),
    ("|", TokenType.OR),
    ("~", TokenType.NOT),
    (",", TokenType.COMMA),
    (";", TokenType.SEMICOLON),
    ("(", TokenType.LPAREN),
    (")", TokenType.RPAREN),
    ("[", TokenType.LBRACKET),
    ("]", TokenType.RBRACKET),
    (":", TokenType.COLON),
]


@pytest.mark.parametrize("source,expected", OPERATOR_CASES)
def test_operator(source, expected):
    assert types(source) == [expected]


def test_operator_sequence():
    assert types("a<-b") == [TokenType.IDENTIFIER, TokenType.ASSIGN, TokenType.IDENTIFIER]
    assert types("x==y") == [TokenType.IDENTIFIER, TokenType.EQEQ, TokenType.IDENTIFIER]
    assert types("a<=b") == [TokenType.IDENTIFIER, TokenType.LE, TokenType.IDENTIFIER]
    assert types("a>=b") == [TokenType.IDENTIFIER, TokenType.GE, TokenType.IDENTIFIER]
    assert types("a<>b") == [TokenType.IDENTIFIER, TokenType.NEQ, TokenType.IDENTIFIER]


# ---------------------------------------------------------------------------
# Comments.
# ---------------------------------------------------------------------------

def test_comment_skipped():
    assert types("// comentario") == []
    assert types("a // comentario") == [TokenType.IDENTIFIER]


def test_comment_to_eol_only():
    # Comment ends at newline; next line is tokenized.
    assert types("// c1\nb") == [TokenType.IDENTIFIER]


def test_slash_is_division_not_comment():
    assert types("a/b") == [TokenType.IDENTIFIER, TokenType.SLASH, TokenType.IDENTIFIER]


# ---------------------------------------------------------------------------
# Positions (line 1-based, col 0-based).
# ---------------------------------------------------------------------------

def test_position_single_line():
    toks = tokenize("a <- b")
    assert toks[0].line == 1 and toks[0].col == 0  # a
    assert toks[1].line == 1 and toks[1].col == 2  # <-
    assert toks[2].line == 1 and toks[2].col == 5  # b


def test_position_multiline():
    toks = tokenize("a\nb")
    assert toks[0].line == 1 and toks[0].col == 0  # a
    assert toks[1].line == 2 and toks[1].col == 0  # b


def test_position_after_indent():
    toks = tokenize("  x")
    assert toks[0].line == 1 and toks[0].col == 2


def test_position_multiword_keyword():
    toks = tokenize("Hasta Que")
    assert toks[0].line == 1 and toks[0].col == 0


# ---------------------------------------------------------------------------
# Errors.
# ---------------------------------------------------------------------------

def test_malformed_number_double_dot():
    with pytest.raises(LexError) as exc:
        tokenize("1.2.3")
    assert exc.value.line == 1
    assert exc.value.col == 3  # points at the second '.'


def test_malformed_number_trailing_dot():
    with pytest.raises(LexError):
        tokenize("1.")


def test_malformed_number_dot_no_digit():
    with pytest.raises(LexError):
        tokenize("1.x")


def test_unterminated_double_string():
    with pytest.raises(LexError) as exc:
        tokenize('"hola')
    assert exc.value.line == 1
    assert exc.value.col == 0


def test_unterminated_single_string():
    with pytest.raises(LexError):
        tokenize("'hola")


def test_unterminated_string_position_multiline():
    with pytest.raises(LexError) as exc:
        tokenize('a\n"hola')
    assert exc.value.line == 2
    assert exc.value.col == 0


def test_unexpected_character():
    with pytest.raises(LexError):
        tokenize("a @ b")


# ---------------------------------------------------------------------------
# End-to-end: a small program tokenizes into the expected sequence.
# ---------------------------------------------------------------------------

def test_small_program():
    src = (
        "Proceso Suma\n"
        "  Definir a, b Como Entero\n"
        "  a <- 5\n"
        "  b <- 3\n"
        "  Escribir a + b\n"
        "FinProceso\n"
    )
    expected = [
        TokenType.PROCESO,
        TokenType.IDENTIFIER,
        TokenType.DEFINIR,
        TokenType.IDENTIFIER,
        TokenType.COMMA,
        TokenType.IDENTIFIER,
        TokenType.IDENTIFIER,  # Como
        TokenType.IDENTIFIER,  # Entero
        TokenType.IDENTIFIER,
        TokenType.ASSIGN,
        TokenType.INTEGER,
        TokenType.IDENTIFIER,
        TokenType.ASSIGN,
        TokenType.INTEGER,
        TokenType.ESCRIBIR,
        TokenType.IDENTIFIER,
        TokenType.PLUS,
        TokenType.IDENTIFIER,
        TokenType.FINPROCESO,
    ]
    assert types(src) == expected
