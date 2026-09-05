"""AST node definitions for the pinned PseInt dialect.

Mirrors spec/SPEC.md §(a) grammar EBNF. Every node carries the source
position (``line`` 1-based, ``col`` 0-based) of the keyword or token that
started it, matching the lexer convention.

The AST is purely syntactic: no type checking, no bounds checking, no
semantic validation — that is the evaluator's job (todo 5).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Expr:
    """Base class for all expression nodes."""

    line: int
    col: int


@dataclass(frozen=True)
class IntegerLiteral(Expr):
    value: int


@dataclass(frozen=True)
class RealLiteral(Expr):
    value: float


@dataclass(frozen=True)
class StringLiteral(Expr):
    value: str


@dataclass(frozen=True)
class BooleanLiteral(Expr):
    value: bool


@dataclass(frozen=True)
class Identifier(Expr):
    name: str


@dataclass(frozen=True)
class BinaryOp(Expr):
    op: str
    left: Expr
    right: Expr


@dataclass(frozen=True)
class UnaryOp(Expr):
    op: str
    operand: Expr


@dataclass(frozen=True)
class FunctionCall(Expr):
    name: str
    args: list[Expr] = field(default_factory=list)


@dataclass(frozen=True)
class ArrayIndex(Expr):
    array: Expr
    index: Expr
    indices: list[Expr] = field(default_factory=list)


@dataclass(frozen=True)
class ArrayLiteral(Expr):
    elements: list[Expr] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stmt:
    """Base class for all statement nodes."""

    line: int
    col: int


@dataclass(frozen=True)
class Assignment(Stmt):
    target: Identifier
    value: Expr


@dataclass(frozen=True)
class Leer(Stmt):
    args: list[Expr] = field(default_factory=list)


@dataclass(frozen=True)
class Escribir(Stmt):
    args: list[Expr] = field(default_factory=list)
    sin_saltar: bool = False


@dataclass(frozen=True)
class Si(Stmt):
    condition: Expr
    then_block: list[Stmt] = field(default_factory=list)
    else_block: list[Stmt] = field(default_factory=list)


@dataclass(frozen=True)
class CaseItem:
    """A single ``Segun`` case: integer label (or ``None`` for the default)."""

    label: int | None
    block: list[Stmt] = field(default_factory=list)


@dataclass(frozen=True)
class Segun(Stmt):
    expr: Expr
    cases: list[CaseItem] = field(default_factory=list)


@dataclass(frozen=True)
class Mientras(Stmt):
    condition: Expr
    block: list[Stmt] = field(default_factory=list)


@dataclass(frozen=True)
class Repetir(Stmt):
    block: list[Stmt] = field(default_factory=list)
    condition: Expr = field(default_factory=lambda: Identifier(0, 0))


@dataclass(frozen=True)
class Para(Stmt):
    var: Identifier
    start: Expr
    end: Expr
    step: Expr | None = None
    block: list[Stmt] = field(default_factory=list)


@dataclass(frozen=True)
class HacerMientrasQue(Stmt):
    block: list[Stmt] = field(default_factory=list)
    condition: Expr = field(default_factory=lambda: Identifier(0, 0))


@dataclass(frozen=True)
class Esperar(Stmt):
    duration: Expr
    milisegundos: bool = False


@dataclass(frozen=True)
class LimpiarPantalla(Stmt):
    pass


@dataclass(frozen=True)
class Retornar(Stmt):
    value: Expr


@dataclass(frozen=True)
class SubProcCall(Stmt):
    name: str
    args: list[Expr] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Definir(Stmt):
    names: list[Identifier] = field(default_factory=list)
    type_name: str | None = None
    init: Expr | None = None


@dataclass(frozen=True)
class Dimension(Stmt):
    name: Identifier
    sizes: list[Expr] = field(default_factory=list)


@dataclass(frozen=True)
class Redimensionar(Stmt):
    name: Identifier
    sizes: list[Expr] = field(default_factory=list)


# ---------------------------------------------------------------------------
# SubProceso / Funcion
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParamDecl:
    name: Identifier
    type_name: str | None = None
    direction: str | None = None  # "Por Referencia" | "Por Valor" | None


@dataclass(frozen=True)
class SubProceso(Stmt):
    name: Identifier
    params: list[ParamDecl] = field(default_factory=list)
    block: list[Stmt] = field(default_factory=list)
    is_function: bool = False
    return_type: str | None = None


# ---------------------------------------------------------------------------
# Program
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Program:
    name: Identifier
    params: list[ParamDecl] = field(default_factory=list)
    body: list[Stmt] = field(default_factory=list)
