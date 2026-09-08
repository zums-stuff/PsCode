"""Recursive-descent parser for the pinned PseInt dialect.

Consumes the token stream produced by :mod:`pseint_engine.lexer` and builds
the AST defined in :mod:`pseint_engine.ast_nodes`, conforming to
spec/SPEC.md §(a) grammar EBNF.

Public API::

    parse(source: str) -> Program

Raises :class:`ParseError` (code ``"CE"``) on any syntax error, carrying the
1-based ``line`` and 0-based ``col`` of the offending token. Unterminated
structures report the position of their opening keyword.
"""

from __future__ import annotations

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
from pseint_engine.lexer import Token, TokenType, tokenize

# Maximum tokens the parser may consume within a single statement before
# giving up (fail-fast guard against pathological input).
_MAX_TOKENS_PER_STATEMENT = 1000

# Type names (SPEC §(a) ``type`` rule). The lexer emits these as IDENTIFIER.
_TYPE_NAMES = frozenset({"entero", "real", "logico", "caracter", "cadena"})

# Token types that can never start a statement inside a block.
_BLOCK_ENDERS = frozenset(
    {
        TokenType.FINPROCESO,
        TokenType.FINSI,
        TokenType.FINMIENTRAS,
        TokenType.FINPARA,
        TokenType.FINSEGUN,
        TokenType.FINSUBPROCESO,
        TokenType.FINFUNCION,
        TokenType.EOF,
    }
)

# Built-in function names (SPEC §(b)); the lexer emits these as keyword
# tokens, but in expression position they are function calls.
_BUILTIN_FUNCS = frozenset(
    {
        TokenType.AZAR,
        TokenType.RC,
        TokenType.ABS,
        TokenType.LN,
        TokenType.EXP,
        TokenType.SEN,
        TokenType.COS,
        TokenType.ATAN,
        TokenType.TRUNC,
        TokenType.REDON,
        TokenType.LARGO,
        TokenType.SUBCADENA,
        TokenType.CONCATENAR,
        TokenType.MAYUSCULARES,
        TokenType.MINUSCULAS,
        TokenType.FECHA_ACTUAL,
        TokenType.HORA_ACTUAL,
    }
)

# Reserved keywords that cannot be used as identifiers.
_RESERVED_WORDS = frozenset(
    {
        TokenType.PROCESO,
        TokenType.FINPROCESO,
        TokenType.DEFINIR,
        TokenType.DIMENSION,
        TokenType.REDIMENSIONAR,
        TokenType.LEER,
        TokenType.ESCRIBIR,
        TokenType.SI,
        TokenType.ENTONCES,
        TokenType.SINO,
        TokenType.FINSI,
        TokenType.SEGUN,
        TokenType.HACER,
        TokenType.FINSEGUN,
        TokenType.DE_OTRO_MODO,
        TokenType.MIENTRAS,
        TokenType.FINMIENTRAS,
        TokenType.REPETIR,
        TokenType.HASTA,
        TokenType.HASTA_QUE,
        TokenType.PARA,
        TokenType.CON_PASO,
        TokenType.FINPARA,
        TokenType.ESPERAR,
        TokenType.MILISEGUNDOS,
        TokenType.LIMPIAR_PANTALLA,
        TokenType.RETORNAR,
        TokenType.SUBPROCESO,
        TokenType.FUNCION,
        TokenType.FINSUBPROCESO,
        TokenType.FINFUNCION,
        TokenType.POR_REFERENCIA,
        TokenType.POR_VALOR,
        TokenType.VERDADERO,
        TokenType.FALSO,
    }
)

# Token types that can begin an expression (used to decide whether a bare
# ``Leer`` has arguments).
_EXPR_START = frozenset(
    {
        TokenType.INTEGER,
        TokenType.REAL,
        TokenType.STRING,
        TokenType.VERDADERO,
        TokenType.FALSO,
        TokenType.IDENTIFIER,
        TokenType.LPAREN,
        TokenType.LBRACKET,
        TokenType.PLUS,
        TokenType.MINUS,
        TokenType.NOT,
    }
) | _BUILTIN_FUNCS


class ParseError(Exception):
    """A syntax error in the PseInt source.

    ``code`` is always ``"CE"`` (compilation error). ``line`` is 1-based,
    ``col`` is 0-based, matching the lexer convention.
    """

    def __init__(self, code: str, message: str, line: int, col: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.line = line
        self.col = col


def parse(source: str) -> Program:
    """Parse ``source`` into a :class:`Program` AST.

    Raises :class:`ParseError` with code ``"CE"`` on syntax errors.
    """
    tokens = tokenize(source)
    return _Parser(tokens).parse_program()


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0
        self._tokens_since_statement = 0

    # -- token helpers ------------------------------------------------------

    def peek(self) -> Token:
        return self.tokens[self.pos]

    def peek_at(self, offset: int) -> Token:
        idx = min(self.pos + offset, len(self.tokens) - 1)
        return self.tokens[idx]

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        self._tokens_since_statement += 1
        if self._tokens_since_statement > _MAX_TOKENS_PER_STATEMENT:
            raise self._error(
                f"parser exceeded {_MAX_TOKENS_PER_STATEMENT} tokens without "
                "making progress",
                tok,
            )
        return tok

    def match(self, *types: TokenType) -> Token | None:
        if self.peek().type in types:
            return self.advance()
        return None

    def expect(self, type_: TokenType, what: str | None = None) -> Token:
        tok = self.peek()
        if tok.type is not type_:
            expected = what or type_.name
            raise self._error(f"expected {expected}, found {tok.type.name}", tok)
        return self.advance()

    def _error(self, message: str, tok: Token) -> ParseError:
        return ParseError("CE", message, tok.line, tok.col)

    def _expect_identifier(self, what: str = "identifier") -> Identifier:
        tok = self.peek()
        if tok.type is not TokenType.IDENTIFIER:
            raise self._error(
                f"expected {what}, found {tok.type.name}"
                + (
                    f" (reserved word '{tok.value}' cannot be used as an "
                    "identifier)"
                    if tok.type is not TokenType.IDENTIFIER
                    else ""
                ),
                tok,
            )
        self.advance()
        return Identifier(tok.line, tok.col, tok.value)

    def _is_type_name(self, tok: Token) -> bool:
        return tok.type is TokenType.IDENTIFIER and tok.value.lower() in _TYPE_NAMES

    def _expect_type_name(self) -> str:
        tok = self.peek()
        if not self._is_type_name(tok):
            raise self._error(
                f"expected type name (Entero/Real/Logico/Caracter/Cadena), "
                f"found {tok.type.name}",
                tok,
            )
        self.advance()
        return tok.value

    def _is_identifier_value(self, value: str) -> bool:
        return (
            self.peek().type is TokenType.IDENTIFIER
            and self.peek().value.lower() == value
        )

    def _is_mientras_que(self) -> bool:
        """True if the current position is ``Mientras Que`` (do-while tail)."""
        return (
            self.peek().type is TokenType.MIENTRAS
            and self.peek_at(1).type is TokenType.IDENTIFIER
            and self.peek_at(1).value.lower() == "que"
        )

    # -- program ------------------------------------------------------------

    def parse_program(self) -> Program:
        tok = self.expect(TokenType.PROCESO, "'Proceso'")
        name = self._expect_identifier("procedure name")
        params: list[ParamDecl] = []
        if self.match(TokenType.LBRACKET):
            params = self._parse_param_list()
            self.expect(TokenType.RBRACKET, "']'")
        body = self._parse_block(
            frozenset({TokenType.FINPROCESO, TokenType.EOF}), tok.line, tok.col
        )
        if self.peek().type is TokenType.EOF:
            raise ParseError("CE", "missing 'FinProceso'", tok.line, tok.col)
        self.expect(TokenType.FINPROCESO, "'FinProceso'")
        self.expect(TokenType.EOF, "end of file")
        return Program(name, params, body)

    def _parse_param_list(self) -> list[ParamDecl]:
        params = [self._parse_param()]
        while self.match(TokenType.COMMA):
            params.append(self._parse_param())
        return params

    def _parse_param(self) -> ParamDecl:
        direction: str | None = None
        if self.peek().type is TokenType.POR_REFERENCIA:
            direction = "Por Referencia"
            self.advance()
        elif self.peek().type is TokenType.POR_VALOR:
            direction = "Por Valor"
            self.advance()
        name = self._expect_identifier("parameter name")
        type_name: str | None = None
        if self.match(TokenType.COLON):
            type_name = self._expect_type_name()
        return ParamDecl(name, type_name, direction)

    # -- blocks -------------------------------------------------------------

    def _parse_block(
        self, stop: frozenset[TokenType], open_line: int, open_col: int
    ) -> list:
        stmts: list = []
        while True:
            t = self.peek().type
            if t in stop:
                break
            if t in _BLOCK_ENDERS:
                raise ParseError(
                    "CE",
                    "missing closing keyword for structure opened here",
                    open_line,
                    open_col,
                )
            stmts.append(self._parse_statement())
        return stmts

    # -- statements ---------------------------------------------------------

    def _parse_statement(self):
        tok = self.peek()
        self._tokens_since_statement = 0
        t = tok.type
        if t is TokenType.IDENTIFIER and self._is_type_name(tok):
            return self._parse_typed_declaration()
        if t is TokenType.IDENTIFIER:
            return self._parse_identifier_statement()
        if t in _RESERVED_WORDS and self.peek_at(1).type is TokenType.ASSIGN:
            raise self._error(
                f"reserved word '{tok.value}' cannot be used as an identifier",
                tok,
            )
        if t is TokenType.DEFINIR:
            return self._parse_definir()
        if t is TokenType.DIMENSION:
            return self._parse_dimension()
        if t is TokenType.REDIMENSIONAR:
            return self._parse_redimensionar()
        if t is TokenType.LEER:
            return self._parse_leer()
        if t is TokenType.ESCRIBIR:
            return self._parse_escribir()
        if t is TokenType.SI:
            return self._parse_si()
        if t is TokenType.SEGUN:
            return self._parse_segun()
        if t is TokenType.MIENTRAS:
            return self._parse_mientras()
        if t is TokenType.REPETIR:
            return self._parse_repetir()
        if t is TokenType.PARA:
            return self._parse_para()
        if t is TokenType.HACER:
            return self._parse_hacer_mientras_que()
        if t is TokenType.ESPERAR:
            return self._parse_esperar()
        if t is TokenType.LIMPIAR_PANTALLA:
            self.advance()
            return LimpiarPantalla(tok.line, tok.col)
        if t is TokenType.RETORNAR:
            return self._parse_retornar()
        if t is TokenType.SUBPROCESO or t is TokenType.FUNCION:
            return self._parse_subproceso()
        if t in _BLOCK_ENDERS:
            raise self._error(
                f"unexpected {t.name} (missing enclosing structure?)", tok
            )
        raise self._error(f"unexpected token {t.name}", tok)

    def _parse_identifier_statement(self):
        tok = self.peek()
        nxt = self.peek_at(1)
        if nxt.type is TokenType.ASSIGN:
            self.advance()  # identifier
            self.advance()  # <-
            value = self._parse_expr()
            return Assignment(
                tok.line, tok.col, Identifier(tok.line, tok.col, tok.value), value
            )
        if nxt.type is TokenType.LBRACKET:
            # Array element assignment: identifier "[" expr {"," expr} "]" "<-" expr
            self.advance()  # identifier
            self.advance()  # [
            first = self._parse_expr()
            indices: list = []
            while self.match(TokenType.COMMA):
                indices.append(self._parse_expr())
            self.expect(TokenType.RBRACKET, "']'")
            self.expect(TokenType.ASSIGN, "'<-'")
            value = self._parse_expr()
            target = ArrayIndex(
                tok.line,
                tok.col,
                Identifier(tok.line, tok.col, tok.value),
                first,
                indices,
            )
            return Assignment(tok.line, tok.col, target, value)
        # SubProceso call: identifier ["(" [expr_list] ")"]
        name = self.advance()
        args: list = []
        if self.match(TokenType.LPAREN):
            if not self.match(TokenType.RPAREN):
                args = self._parse_expr_list()
                self.expect(TokenType.RPAREN, "')'")
        return SubProcCall(name.line, name.col, name.value, args)

    def _parse_typed_declaration(self) -> Assignment:
        """Parse a PseInt typed declaration: ``Entero i`` / ``Cadena s <- "x"``.

        Per SPEC §(a) ``type identifier [ "<-" expr ]`` and the official
        PseInt semantics, ``<type> <ident>`` is sugar for declaring the
        variable with the given type and optionally initialising it. The
        evaluator distinguishes three forms via :attr:`Assignment.value`
        and :attr:`Assignment.type_name`:

        - ``Cadena s``              → ``value=None``, ``type_name="Cadena"``
          (default-initialised; evaluator picks the type's zero value)
        - ``Entero i <- 5``         → ``value=IntegerLiteral(5)``, ``type_name="Entero"``
        - ``Cadena arr()``          → never reached: a procedure call cannot
          start with a type name, so this is malformed and raises CE (the
          ``(`` form here would actually be eaten as a function-call
          expression and the leftover statement would fail).
        """
        type_tok = self.advance()  # "Cadena" / "Entero" / etc.
        type_name = type_tok.value
        var = self._expect_identifier("variable name")
        # Typed array declaration: "Cadena arr[3]". The official PseInt
        # grammar treats this as a Dimension with an element type tag; the
        # pinned dialect does not surface this form in the SPEC, so we
        # raise CE rather than guess.  (If/when the corpus needs it,
        # extend ``Dimension`` with a ``type_name`` field and dispatch here.)
        if self.match(TokenType.LBRACKET):
            raise self._error(
                "las declaraciones de arreglos con tipo explícito no están "
                "soportadas; usa 'Dimension' o 'Definir'",
                self.peek(),
            )
        value: Expr | None = None
        if self.match(TokenType.ASSIGN, TokenType.EQ):
            value = self._parse_expr()
        return Assignment(
            type_tok.line,
            type_tok.col,
            Identifier(var.line, var.col, var.name),
            value,
            type_name=type_name,
        )

    # -- declarations -------------------------------------------------------

    def _parse_definir(self) -> Definir:
        tok = self.advance()  # DEFINIR
        names = [self._expect_identifier("variable name")]
        while self.match(TokenType.COMMA):
            names.append(self._expect_identifier("variable name"))
        type_name: str | None = None
        if self.match(TokenType.COLON):
            type_name = self._expect_type_name()
        elif self._is_identifier_value("como"):
            self.advance()
            type_name = self._expect_type_name()
        init = None
        if self.match(TokenType.ASSIGN, TokenType.EQ):
            init = self._parse_expr()
        return Definir(tok.line, tok.col, names, type_name, init)

    def _parse_dimension(self) -> Dimension:
        tok = self.advance()  # DIMENSION
        name = self._expect_identifier("array name")
        self.expect(TokenType.LBRACKET, "'['")
        sizes = [self._parse_expr()]
        while self.match(TokenType.COMMA):
            sizes.append(self._parse_expr())
        self.expect(TokenType.RBRACKET, "']'")
        return Dimension(tok.line, tok.col, name, sizes)

    def _parse_redimensionar(self) -> Redimensionar:
        tok = self.advance()  # REDIMENSIONAR
        name = self._expect_identifier("array name")
        self.expect(TokenType.LBRACKET, "'['")
        sizes = [self._parse_expr()]
        while self.match(TokenType.COMMA):
            sizes.append(self._parse_expr())
        self.expect(TokenType.RBRACKET, "']'")
        return Redimensionar(tok.line, tok.col, name, sizes)

    # -- simple statements --------------------------------------------------

    def _parse_leer(self) -> Leer:
        tok = self.advance()  # LEER
        args: list = []
        if self.peek().type in _EXPR_START:
            args = self._parse_expr_list()
        return Leer(tok.line, tok.col, args)

    def _parse_escribir(self) -> Escribir:
        tok = self.advance()  # ESCRIBIR
        sin_saltar = False
        if self._is_sin_saltar():
            self.advance()  # Sin
            self.advance()  # Saltar
            sin_saltar = True
        args = self._parse_expr_list()
        return Escribir(tok.line, tok.col, args, sin_saltar)

    def _is_sin_saltar(self) -> bool:
        return (
            self.peek().type is TokenType.IDENTIFIER
            and self.peek().value.lower() == "sin"
            and self.peek_at(1).type is TokenType.IDENTIFIER
            and self.peek_at(1).value.lower() == "saltar"
        )

    def _parse_esperar(self) -> Esperar:
        tok = self.advance()  # ESPERAR
        duration = self._parse_expr()
        milisegundos = self.match(TokenType.MILISEGUNDOS) is not None
        return Esperar(tok.line, tok.col, duration, milisegundos)

    def _parse_retornar(self) -> Retornar:
        tok = self.advance()  # RETORNAR
        value = self._parse_expr()
        return Retornar(tok.line, tok.col, value)

    # -- control flow -------------------------------------------------------

    def _parse_si(self) -> Si:
        tok = self.advance()  # SI
        condition = self._parse_expr()
        self.expect(TokenType.ENTONCES, "'Entonces'")
        then_block = self._parse_block(
            frozenset({TokenType.SINO, TokenType.FINSI}), tok.line, tok.col
        )
        else_block: list = []
        if self.match(TokenType.SINO):
            else_block = self._parse_block(
                frozenset({TokenType.FINSI}), tok.line, tok.col
            )
        self.expect(TokenType.FINSI, "'FinSi'")
        return Si(tok.line, tok.col, condition, then_block, else_block)

    def _parse_segun(self) -> Segun:
        tok = self.advance()  # SEGUN
        expr = self._parse_expr()
        self.expect(TokenType.HACER, "'Hacer'")
        cases: list[CaseItem] = []
        while True:
            if self.peek().type is TokenType.INTEGER:
                label_tok = self.advance()
                label = int(label_tok.value)
            elif self.peek().type is TokenType.DE_OTRO_MODO:
                label_tok = self.advance()
                label = None
            else:
                break
            self.expect(TokenType.COLON, "':'")
            block = self._parse_case_block(tok.line, tok.col)
            cases.append(CaseItem(label, block))
        self.expect(TokenType.FINSEGUN, "'FinSegun'")
        return Segun(tok.line, tok.col, expr, cases)

    def _parse_case_block(self, open_line: int, open_col: int) -> list:
        stmts: list = []
        while True:
            t = self.peek().type
            if t is TokenType.FINSEGUN:
                break
            if t is TokenType.DE_OTRO_MODO:
                break
            if t is TokenType.INTEGER and self.peek_at(1).type is TokenType.COLON:
                break
            if t in _BLOCK_ENDERS:
                raise ParseError("CE", "missing 'FinSegun'", open_line, open_col)
            stmts.append(self._parse_statement())
        return stmts

    def _parse_mientras(self) -> Mientras:
        tok = self.advance()  # MIENTRAS
        condition = self._parse_expr()
        self.expect(TokenType.HACER, "'Hacer'")
        block = self._parse_block(
            frozenset({TokenType.FINMIENTRAS}), tok.line, tok.col
        )
        self.expect(TokenType.FINMIENTRAS, "'FinMientras'")
        return Mientras(tok.line, tok.col, condition, block)

    def _parse_repetir(self) -> Repetir:
        tok = self.advance()  # REPETIR
        block = self._parse_block(
            frozenset({TokenType.HASTA_QUE}), tok.line, tok.col
        )
        self.expect(TokenType.HASTA_QUE, "'Hasta Que'")
        condition = self._parse_expr()
        return Repetir(tok.line, tok.col, block, condition)

    def _parse_para(self) -> Para:
        tok = self.advance()  # PARA
        var = self._expect_identifier("loop variable")
        if not self.match(TokenType.EQ, TokenType.ASSIGN):
            raise self._error("expected '=' or '<-'", self.peek())
        start = self._parse_expr()
        self.expect(TokenType.HASTA, "'Hasta'")
        end = self._parse_expr()
        step = None
        if self.match(TokenType.CON_PASO):
            step = self._parse_expr()
        block = self._parse_block(
            frozenset({TokenType.FINPARA}), tok.line, tok.col
        )
        self.expect(TokenType.FINPARA, "'FinPara'")
        return Para(tok.line, tok.col, var, start, end, step, block)

    def _parse_hacer_mientras_que(self) -> HacerMientrasQue:
        tok = self.advance()  # HACER
        block: list = []
        while not self._is_mientras_que():
            t = self.peek().type
            if t in _BLOCK_ENDERS:
                raise ParseError(
                    "CE", "missing 'Mientras Que'", tok.line, tok.col
                )
            block.append(self._parse_statement())
        self.advance()  # MIENTRAS
        self.advance()  # Que
        condition = self._parse_expr()
        return HacerMientrasQue(tok.line, tok.col, block, condition)

    def _parse_subproceso(self) -> SubProceso:
        tok = self.advance()  # SUBPROCESO or FUNCION
        is_function = tok.type is TokenType.FUNCION
        name = self._expect_identifier("subprocess name")
        params: list[ParamDecl] = []
        if self.match(TokenType.LPAREN):
            if not self.match(TokenType.RPAREN):
                params = self._parse_param_list()
                self.expect(TokenType.RPAREN, "')'")
        return_type: str | None = None
        if is_function and self.match(TokenType.COLON):
            return_type = self._expect_type_name()
        end_type = (
            TokenType.FINFUNCION if is_function else TokenType.FINSUBPROCESO
        )
        block = self._parse_block(frozenset({end_type}), tok.line, tok.col)
        self.expect(
            end_type, "'FinFuncion'" if is_function else "'FinSubProceso'"
        )
        return SubProceso(
            tok.line, tok.col, name, params, block, is_function, return_type
        )

    # -- expressions --------------------------------------------------------

    def _parse_expr_list(self) -> list:
        exprs = [self._parse_expr()]
        while self.match(TokenType.COMMA):
            exprs.append(self._parse_expr())
        return exprs

    def _parse_expr(self):
        return self._parse_logical_or()

    def _parse_logical_or(self):
        left = self._parse_logical_and()
        while self.peek().type is TokenType.OR:
            tok = self.advance()
            right = self._parse_logical_and()
            left = BinaryOp(tok.line, tok.col, "|", left, right)
        return left

    def _parse_logical_and(self):
        left = self._parse_relational()
        while self.peek().type is TokenType.AND:
            tok = self.advance()
            right = self._parse_relational()
            left = BinaryOp(tok.line, tok.col, "&", left, right)
        return left

    def _parse_relational(self):
        left = self._parse_additive()
        while self.peek().type in (
            TokenType.LT,
            TokenType.GT,
            TokenType.EQ,
            TokenType.EQEQ,
            TokenType.NEQ,
            TokenType.LE,
            TokenType.GE,
        ):
            tok = self.advance()
            right = self._parse_additive()
            left = BinaryOp(tok.line, tok.col, tok.value, left, right)
        return left

    def _parse_additive(self):
        left = self._parse_multiplicative()
        while self.peek().type in (TokenType.PLUS, TokenType.MINUS):
            tok = self.advance()
            right = self._parse_multiplicative()
            left = BinaryOp(tok.line, tok.col, tok.value, left, right)
        return left

    def _parse_multiplicative(self):
        left = self._parse_unary()
        while self.peek().type in (
            TokenType.STAR,
            TokenType.SLASH,
            TokenType.PERCENT,
            TokenType.MOD,
        ):
            tok = self.advance()
            right = self._parse_unary()
            left = BinaryOp(tok.line, tok.col, tok.value, left, right)
        return left

    def _parse_unary(self):
        tok = self.peek()
        if tok.type in (TokenType.PLUS, TokenType.MINUS, TokenType.NOT):
            self.advance()
            operand = self._parse_power()
            return UnaryOp(tok.line, tok.col, tok.value, operand)
        return self._parse_power()

    def _parse_power(self):
        base = self._parse_primary()
        if self.peek().type is TokenType.CARET:
            tok = self.advance()
            exponent = self._parse_power()  # right-associative
            return BinaryOp(tok.line, tok.col, "^", base, exponent)
        return base

    def _parse_primary(self):
        tok = self.peek()
        t = tok.type
        if t is TokenType.INTEGER:
            self.advance()
            return IntegerLiteral(tok.line, tok.col, int(tok.value))
        if t is TokenType.REAL:
            self.advance()
            return RealLiteral(tok.line, tok.col, float(tok.value))
        if t is TokenType.STRING:
            self.advance()
            return StringLiteral(tok.line, tok.col, tok.value)
        if t is TokenType.VERDADERO:
            self.advance()
            return BooleanLiteral(tok.line, tok.col, True)
        if t is TokenType.FALSO:
            self.advance()
            return BooleanLiteral(tok.line, tok.col, False)
        if t in _BUILTIN_FUNCS:
            self.advance()
            self.expect(TokenType.LPAREN, "'('")
            args: list = []
            if not self.match(TokenType.RPAREN):
                args = self._parse_expr_list()
                self.expect(TokenType.RPAREN, "')'")
            return FunctionCall(tok.line, tok.col, tok.value, args)
        if t is TokenType.IDENTIFIER:
            self.advance()
            if self.match(TokenType.LPAREN):
                args: list = []
                if not self.match(TokenType.RPAREN):
                    args = self._parse_expr_list()
                    self.expect(TokenType.RPAREN, "')'")
                return FunctionCall(tok.line, tok.col, tok.value, args)
            if self.match(TokenType.LBRACKET):
                first = self._parse_expr()
                indices: list = []
                while self.match(TokenType.COMMA):
                    indices.append(self._parse_expr())
                self.expect(TokenType.RBRACKET, "']'")
                return ArrayIndex(
                    tok.line,
                    tok.col,
                    Identifier(tok.line, tok.col, tok.value),
                    first,
                    indices,
                )
            return Identifier(tok.line, tok.col, tok.value)
        if t is TokenType.LPAREN:
            self.advance()
            inner = self._parse_expr()
            self.expect(TokenType.RPAREN, "')'")
            return inner
        if t is TokenType.LBRACKET:
            self.advance()
            elements: list = []
            if not self.match(TokenType.RBRACKET):
                elements = self._parse_expr_list()
                self.expect(TokenType.RBRACKET, "']'")
            return ArrayLiteral(tok.line, tok.col, elements)
        raise self._error(f"expected expression, found {t.name}", tok)
