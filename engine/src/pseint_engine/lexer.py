"""Lexer (tokenizer) for the pinned PseInt dialect.

Conforms to spec/SPEC.md §(a) grammar EBNF and §(b) keyword table.

Token positions: ``line`` is 1-based, ``col`` is 0-based (both refer to the
start of the token). ``Token.value`` always preserves the ORIGINAL spelling of
the source text (e.g. ``Dimensionar`` keeps its spelling even though its type
is ``DIMENSION``; multi-word keywords keep their internal whitespace). No
Unicode normalization is applied to identifiers beyond NFC.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    """Every token kind the lexer can emit."""

    # Reserved keywords (SPEC §(b)).
    PROCESO = auto()
    FINPROCESO = auto()
    DEFINIR = auto()
    DIMENSION = auto()
    REDIMENSIONAR = auto()
    LEER = auto()
    ESCRIBIR = auto()
    SI = auto()
    ENTONCES = auto()
    SINO = auto()
    FINSI = auto()
    SEGUN = auto()
    HACER = auto()
    FINSEGUN = auto()
    DE_OTRO_MODO = auto()
    MIENTRAS = auto()
    FINMIENTRAS = auto()
    REPETIR = auto()
    HASTA = auto()
    HASTA_QUE = auto()
    PARA = auto()
    CON_PASO = auto()
    FINPARA = auto()
    ESPERAR = auto()
    MILISEGUNDOS = auto()
    LIMPIAR_PANTALLA = auto()
    RETORNAR = auto()
    SUBPROCESO = auto()
    FUNCION = auto()
    FINSUBPROCESO = auto()
    FINFUNCION = auto()
    POR_REFERENCIA = auto()
    POR_VALOR = auto()

    # Logical constants.
    VERDADERO = auto()
    FALSO = auto()

    # Built-in functions.
    AZAR = auto()
    RC = auto()
    ABS = auto()
    LN = auto()
    EXP = auto()
    SEN = auto()
    COS = auto()
    ATAN = auto()
    TRUNC = auto()
    REDON = auto()
    LARGO = auto()
    SUBCADENA = auto()
    CONCATENAR = auto()
    MAYUSCULARES = auto()
    MINUSCULAS = auto()
    FECHA_ACTUAL = auto()
    HORA_ACTUAL = auto()

    # Literals.
    IDENTIFIER = auto()
    INTEGER = auto()
    REAL = auto()
    STRING = auto()

    # Operators.
    ASSIGN = auto()  # <-
    EQ = auto()  # =
    EQEQ = auto()  # ==
    NEQ = auto()  # <>
    LT = auto()  # <
    GT = auto()  # >
    LE = auto()  # <=
    GE = auto()  # >=
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    CARET = auto()  # ^
    PERCENT = auto()  # %
    MOD = auto()
    AND = auto()  # &
    OR = auto()  # |
    NOT = auto()  # ~
    COMMA = auto()
    SEMICOLON = auto()
    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    COLON = auto()

    EOF = auto()


@dataclass(frozen=True)
class Token:
    """A single lexical token.

    ``line`` is 1-based; ``col`` is 0-based. ``value`` preserves the original
    spelling of the source text.
    """

    type: TokenType
    value: str
    line: int
    col: int


class LexError(Exception):
    """Raised when the source cannot be tokenized (e.g. malformed number)."""

    def __init__(self, message: str, line: int, col: int) -> None:
        super().__init__(message)
        self.message = message
        self.line = line
        self.col = col


# Single-word keywords: lowercase canonical spelling -> token type.
_KEYWORDS: dict[str, TokenType] = {
    "proceso": TokenType.PROCESO,
    "finproceso": TokenType.FINPROCESO,
    "definir": TokenType.DEFINIR,
    "dimension": TokenType.DIMENSION,
    "dimensionar": TokenType.DIMENSION,  # flexible synonym
    "redimensionar": TokenType.REDIMENSIONAR,
    "leer": TokenType.LEER,
    "escribir": TokenType.ESCRIBIR,
    "si": TokenType.SI,
    "entonces": TokenType.ENTONCES,
    "sino": TokenType.SINO,  # covers SiNo and Sino
    "finsi": TokenType.FINSI,
    "segun": TokenType.SEGUN,
    "hacer": TokenType.HACER,
    "finsegun": TokenType.FINSEGUN,
    "mientras": TokenType.MIENTRAS,
    "finmientras": TokenType.FINMIENTRAS,
    "repetir": TokenType.REPETIR,
    "hasta": TokenType.HASTA,
    "para": TokenType.PARA,
    "finpara": TokenType.FINPARA,
    "esperar": TokenType.ESPERAR,
    "milisegundos": TokenType.MILISEGUNDOS,
    "milisegundo": TokenType.MILISEGUNDOS,  # flexible synonym
    "retornar": TokenType.RETORNAR,
    "subproceso": TokenType.SUBPROCESO,
    "funcion": TokenType.FUNCION,
    "finsubproceso": TokenType.FINSUBPROCESO,
    "finfuncion": TokenType.FINFUNCION,
    "verdadero": TokenType.VERDADERO,
    "falso": TokenType.FALSO,
    "azar": TokenType.AZAR,
    "rc": TokenType.RC,
    "abs": TokenType.ABS,
    "ln": TokenType.LN,
    "exp": TokenType.EXP,
    "sen": TokenType.SEN,
    "cos": TokenType.COS,
    "atan": TokenType.ATAN,
    "trunc": TokenType.TRUNC,
    "redon": TokenType.REDON,
    "largo": TokenType.LARGO,
    "subcadena": TokenType.SUBCADENA,
    "concatenar": TokenType.CONCATENAR,
    "mayusculares": TokenType.MAYUSCULARES,
    "minusculas": TokenType.MINUSCULAS,
    "fechaactual": TokenType.FECHA_ACTUAL,
    "horaactual": TokenType.HORA_ACTUAL,
    "otherwise": TokenType.DE_OTRO_MODO,  # flexible synonym
    "mod": TokenType.MOD,
}

# Multi-word keywords: lowercase phrase -> token type.
_MULTIWORD_KEYWORDS: dict[str, TokenType] = {
    "hasta que": TokenType.HASTA_QUE,
    "con paso": TokenType.CON_PASO,
    "de otro modo": TokenType.DE_OTRO_MODO,
    "por referencia": TokenType.POR_REFERENCIA,
    "por valor": TokenType.POR_VALOR,
    "limpiar pantalla": TokenType.LIMPIAR_PANTALLA,
    "with step": TokenType.CON_PASO,  # flexible synonym
}

# Index multi-word keywords by their first word, longest phrase first.
_MULTIWORD_BY_FIRST: dict[str, list[tuple[tuple[str, ...], TokenType]]] = {}
for _phrase, _tok_type in _MULTIWORD_KEYWORDS.items():
    _words = tuple(_phrase.split())
    _MULTIWORD_BY_FIRST.setdefault(_words[0], []).append((_words, _tok_type))
for _cands in _MULTIWORD_BY_FIRST.values():
    _cands.sort(key=lambda item: -len(item[0]))

_MULTIWORD_FIRST = frozenset(_MULTIWORD_BY_FIRST)

_SINGLE_OPERATORS: dict[str, TokenType] = {
    "=": TokenType.EQ,
    "<": TokenType.LT,
    ">": TokenType.GT,
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "*": TokenType.STAR,
    "/": TokenType.SLASH,
    "^": TokenType.CARET,
    "%": TokenType.PERCENT,
    "&": TokenType.AND,
    "|": TokenType.OR,
    "~": TokenType.NOT,
    ",": TokenType.COMMA,
    ";": TokenType.SEMICOLON,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    "[": TokenType.LBRACKET,
    "]": TokenType.RBRACKET,
    ":": TokenType.COLON,
}

_TWO_CHAR_OPERATORS: dict[str, TokenType] = {
    "<-": TokenType.ASSIGN,
    "==": TokenType.EQEQ,
    "<>": TokenType.NEQ,
    "<=": TokenType.LE,
    ">=": TokenType.GE,
}


def _is_letter(ch: str) -> bool:
    return ch.isalpha()


def _is_ident_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def tokenize(source: str) -> list[Token]:
    """Tokenize ``source`` into a list of ``Token`` ending with an EOF token."""
    return _Lexer(source).tokenize()


class _Lexer:
    def __init__(self, source: str) -> None:
        self.source = source
        self.n = len(source)
        self.pos = 0
        self.line = 1
        self.col = 0

    # -- low-level helpers ---------------------------------------------------

    def _peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        if idx >= self.n:
            return ""
        return self.source[idx]

    def _advance(self) -> str:
        ch = self.source[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 0
        else:
            self.col += 1
        return ch

    def _error(self, message: str) -> None:
        raise LexError(message, self.line, self.col)

    def _skip_whitespace_and_comments(self) -> None:
        while self.pos < self.n:
            ch = self._peek()
            if ch in " \t\r\n":
                self._advance()
            elif ch == "/" and self._peek(1) == "/":
                while self.pos < self.n and self._peek() != "\n":
                    self._advance()
            else:
                break

    def _skip_inline_ws(self) -> bool:
        """Skip spaces/tabs (not newlines). True if at least one was skipped."""
        skipped = False
        while self.pos < self.n and self._peek() in " \t":
            self._advance()
            skipped = True
        return skipped

    # -- token readers -------------------------------------------------------

    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []
        while True:
            self._skip_whitespace_and_comments()
            if self.pos >= self.n:
                tokens.append(Token(TokenType.EOF, "", self.line, self.col))
                break
            ch = self._peek()
            if _is_letter(ch):
                tokens.append(self._read_word())
            elif ch.isdigit():
                tokens.append(self._read_number())
            elif ch in ('"', "'"):
                tokens.append(self._read_string(ch))
            else:
                tokens.append(self._read_operator())
        return tokens

    def _read_word(self) -> Token:
        start_line, start_col = self.line, self.col
        start_pos = self.pos
        while self.pos < self.n and _is_ident_char(self._peek()):
            self._advance()
        word = self.source[start_pos : self.pos]
        lower = word.lower()

        if lower in _MULTIWORD_FIRST:
            matched = self._try_multiword(lower, start_pos, start_line, start_col)
            if matched is not None:
                return matched

        tok_type = _KEYWORDS.get(lower)
        if tok_type is not None:
            return Token(tok_type, word, start_line, start_col)
        return Token(TokenType.IDENTIFIER, word, start_line, start_col)

    def _try_multiword(
        self, first_lower: str, start_pos: int, start_line: int, start_col: int
    ) -> Token | None:
        for words, tok_type in _MULTIWORD_BY_FIRST.get(first_lower, []):
            save_pos, save_line, save_col = self.pos, self.line, self.col
            ok = True
            for expected in words[1:]:
                if not self._skip_inline_ws():
                    ok = False
                    break
                wstart = self.pos
                while self.pos < self.n and _is_ident_char(self._peek()):
                    self._advance()
                if self.source[wstart : self.pos].lower() != expected:
                    ok = False
                    break
            if ok:
                value = self.source[start_pos : self.pos]
                return Token(tok_type, value, start_line, start_col)
            self.pos, self.line, self.col = save_pos, save_line, save_col
        return None

    def _read_number(self) -> Token:
        start_line, start_col = self.line, self.col
        start_pos = self.pos
        while self.pos < self.n and self._peek().isdigit():
            self._advance()

        is_real = False
        if self.pos < self.n and self._peek() == ".":
            if self._peek(1).isdigit():
                is_real = True
                self._advance()  # consume '.'
                while self.pos < self.n and self._peek().isdigit():
                    self._advance()
            else:
                self._error("malformed number: expected digit after '.'")

        if is_real and self.pos < self.n and self._peek() == ".":
            self._error("malformed number: unexpected '.'")

        value = self.source[start_pos : self.pos]
        tok_type = TokenType.REAL if is_real else TokenType.INTEGER
        return Token(tok_type, value, start_line, start_col)

    def _read_string(self, quote: str) -> Token:
        start_line, start_col = self.line, self.col
        start_pos = self.pos
        self._advance()  # consume opening quote
        while self.pos < self.n:
            ch = self._peek()
            if ch == "\\":
                self._advance()
                if self.pos < self.n:
                    self._advance()
                continue
            if ch == quote:
                self._advance()  # consume closing quote
                value = self.source[start_pos : self.pos]
                return Token(TokenType.STRING, value, start_line, start_col)
            self._advance()
        # Unterminated: report the position of the opening quote.
        raise LexError("unterminated string literal", start_line, start_col)

    def _read_operator(self) -> Token:
        start_line, start_col = self.line, self.col
        two = self.source[self.pos : self.pos + 2]
        if two in _TWO_CHAR_OPERATORS:
            self._advance()
            self._advance()
            return Token(_TWO_CHAR_OPERATORS[two], two, start_line, start_col)

        ch = self._peek()
        tok_type = _SINGLE_OPERATORS.get(ch)
        if tok_type is not None:
            self._advance()
            return Token(tok_type, ch, start_line, start_col)

        self._error(f"unexpected character {ch!r}")
