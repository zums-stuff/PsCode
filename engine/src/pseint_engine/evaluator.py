"""Tree-walking evaluator for the pinned PseInt dialect.

Consumes the AST produced by :mod:`pseint_engine.parser` and executes it
against SPEC/SPEC.md: implicit typing + the §(c) conversion matrix,
Escribir formatting per §(e), Leer parsing per §(f), exact step counting
per §(g), and the §(i) runtime-error taxonomy.

Public API::

    evaluate(program: Program, input_text: str = "", seed: int = 0) -> EvalResult

The evaluator only COUNTS steps; step budgets / wall-clock limits are a
runner-level option (todo 7). SubProceso/Funcion execution, arrays and
built-in functions are todo 6 — encountering them raises a clear runtime
error instead of crashing with a Python exception.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pseint_engine.ast_nodes import (
    ArrayIndex,
    ArrayLiteral,
    Assignment,
    BinaryOp,
    BooleanLiteral,
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
from pseint_engine.runtime import (
    CADENA,
    CARACTER,
    ENTERO,
    LOGICO,
    REAL,
    Env,
    EvalResult,
    RuntimeError,
)

# Recursion depth cap — SPEC §(i) + Diff-from-Official #15 (1000 frames).
# NOTE: the plan text says 500, but SPEC pins 1000; SPEC is authoritative.
_MAX_RECURSION = 1000

# PseInt literal grammars (SPEC §(a)): digit {digit} and digit {digit} "." digit
# {digit}, with an optional sign accepted for Leer/conversion tokens.
_INT_RE = re.compile(r"[+-]?\d+\Z")
_REAL_RE = re.compile(r"[+-]?\d+\.\d+\Z")


@dataclass(frozen=True)
class Value:
    """A typed runtime value: a Python object plus its PseInt type name."""

    value: object
    type: str


def type_of(value: object) -> str:
    """Natural PseInt type of a Python runtime value."""
    if isinstance(value, bool):
        return LOGICO
    if isinstance(value, int):
        return ENTERO
    if isinstance(value, float):
        return REAL
    if isinstance(value, str):
        return CADENA
    raise TypeError(f"unrepresentable runtime value: {value!r}")


def format_value(value: object) -> str:
    """Format a runtime value for Escribir per the SPEC §(e) table.

    Entero -> integer, no decimal point; Real -> shortest roundtrip with
    ``.`` (Python ``repr(float)`` is the reference); Logico -> Verdadero /
    Falso; Cadena/Caracter -> raw.
    """
    if isinstance(value, bool):
        return "Verdadero" if value else "Falso"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    return str(value)


def convert_value(value: object, from_type: str, to_type: str) -> object:
    """Apply one row of the SPEC §(c) conversion matrix.

    Raises :class:`ValueError` when the conversion is not defined by the
    matrix or the source value cannot be parsed (Cadena -> numeric/logico).
    """
    if from_type == ENTERO:
        if to_type == REAL:
            return float(value)
        if to_type == LOGICO:
            return value != 0
        if to_type == CARACTER:
            return _int_to_char(value)
        if to_type == CADENA:
            return str(value)
    if from_type == REAL:
        if to_type == ENTERO:
            return int(value)
        if to_type == LOGICO:
            return value != 0.0
        if to_type == CARACTER:
            return _int_to_char(int(value))
        if to_type == CADENA:
            return repr(value)
    if from_type == LOGICO:
        if to_type == ENTERO:
            return 1 if value else 0
        if to_type == REAL:
            return 1.0 if value else 0.0
        if to_type == CARACTER:
            return "Verdadero" if value else "Falso"
        if to_type == CADENA:
            return "Verdadero" if value else "Falso"
    if from_type == CARACTER:
        if to_type == ENTERO:
            if len(value) != 1:
                raise ValueError("Caracter must be a single character")
            return ord(value)
        if to_type == REAL:
            if len(value) != 1:
                raise ValueError("Caracter must be a single character")
            return float(ord(value))
        if to_type == CADENA:
            return value
    if from_type == CADENA:
        if to_type == ENTERO:
            if _INT_RE.match(value) is None:
                raise ValueError(f"'{value}' is not an integer")
            return int(value)
        if to_type == REAL:
            if _REAL_RE.match(value) is None:
                raise ValueError(f"'{value}' is not a real")
            return float(value)
        if to_type == LOGICO:
            if value == "Verdadero":
                return True
            if value == "Falso":
                return False
            raise ValueError(f"'{value}' is not a logical value")
        if to_type == CARACTER:
            if len(value) == 0:
                raise ValueError("empty string has no first character")
            return value[0]
    raise ValueError(f"no conversion {from_type} -> {to_type}")


def _int_to_char(value: int) -> str:
    if not 0 <= value <= 0x10FFFF:
        raise ValueError(f"{value} is not a valid ASCII/Unicode code point")
    return chr(value)


class Evaluator:
    """Executes a :class:`Program` AST, counting steps exactly per §(g)."""

    def __init__(self, input_text: str = "", seed: int = 0) -> None:
        self._env = Env()
        self._steps = 0
        self._output = ""
        # Input is split on \s+ per SPEC §(f); lines are kept so a bare
        # ``Leer`` can discard exactly one line.
        self._input_lines: list[list[str]] = [
            line.split() for line in input_text.split("\n")
        ]
        self._line_pos = 0
        self._token_pos = 0
        self._recursion_depth = 0
        self._max_recursion = _MAX_RECURSION
        self._seed = seed  # reserved for AZAR (todo 6)

    # -- public API ---------------------------------------------------------

    def run(self, program: Program) -> EvalResult:
        """Execute the program, returning output, steps and any error."""
        try:
            self._exec_block(program.body)
            return EvalResult(output=self._output, steps=self._steps, error=None)
        except RuntimeError as e:
            return EvalResult(output=self._output, steps=self._steps, error=e)

    # -- recursion frame accounting (used by SubProceso/Funcion in todo 6) --

    def _enter_frame(self, node: object) -> None:
        """Enter one call frame; raise ERR_RECURSION past the 1000 cap."""
        self._recursion_depth += 1
        if self._recursion_depth > self._max_recursion:
            raise self._err(
                "ERR_RECURSION",
                f"profundidad de recursión excedida (máximo {self._max_recursion})",
                node,
            )

    def _exit_frame(self) -> None:
        """Leave one call frame."""
        self._recursion_depth -= 1

    # -- statements ---------------------------------------------------------

    def _exec_block(self, stmts: list) -> None:
        for stmt in stmts:
            self._exec_stmt(stmt)

    def _exec_stmt(self, stmt: object) -> None:
        self._steps += 1  # each statement = 1 step (SPEC §(g))
        if isinstance(stmt, Assignment):
            self._exec_assignment(stmt)
        elif isinstance(stmt, Definir):
            self._exec_definir(stmt)
        elif isinstance(stmt, Leer):
            self._exec_leer(stmt)
        elif isinstance(stmt, Escribir):
            self._exec_escribir(stmt)
        elif isinstance(stmt, Si):
            self._exec_si(stmt)
        elif isinstance(stmt, Segun):
            self._exec_segun(stmt)
        elif isinstance(stmt, Mientras):
            self._exec_mientras(stmt)
        elif isinstance(stmt, Repetir):
            self._exec_repetir(stmt)
        elif isinstance(stmt, Para):
            self._exec_para(stmt)
        elif isinstance(stmt, HacerMientrasQue):
            self._exec_hacer_mientras_que(stmt)
        elif isinstance(stmt, (Esperar, LimpiarPantalla)):
            pass  # no-ops; the statement step was already counted
        elif isinstance(stmt, SubProceso):
            pass  # declaration; execution is todo 6
        elif isinstance(stmt, Retornar):
            raise self._err(
                "ERR_TYPE", "Retornar solo es válido dentro de una función", stmt
            )
        elif isinstance(stmt, SubProcCall):
            raise self._err(
                "ERR_TYPE", f"subproceso no implementado (todo 6): {stmt.name}", stmt
            )
        elif isinstance(stmt, (Dimension, Redimensionar)):
            raise self._err("ERR_DIM", "arrays no implementados (todo 6)", stmt)
        else:
            raise self._err(
                "ERR_TYPE", f"sentencia no soportada: {type(stmt).__name__}", stmt
            )

    def _exec_assignment(self, stmt: Assignment) -> None:
        target = stmt.target
        if isinstance(target, ArrayIndex):
            raise self._err("ERR_DIM", "arrays no implementados (todo 6)", stmt)
        v = self._eval_expr(stmt.value)
        declared = self._env.get_type(target.name)
        if declared is not None and declared != v.type:
            v = self._convert(v, declared, stmt)
        self._env.set(target.name, v.value, v.type)

    def _exec_definir(self, stmt: Definir) -> None:
        for name_node in stmt.names:
            if stmt.type_name is not None:
                t = stmt.type_name.lower()
                existing = self._env.get_type(name_node.name)
                if existing is not None and existing != t:
                    raise self._err(
                        "ERR_TYPE",
                        f"tipo contradictorio para {name_node.name}: "
                        f"{existing} vs {t}",
                        stmt,
                    )
            self._env.declare(name_node.name, stmt.type_name)
        if stmt.init is not None:
            v = self._eval_expr(stmt.init)
            declared = stmt.type_name.lower() if stmt.type_name else None
            if declared is not None and declared != v.type:
                v = self._convert(v, declared, stmt)
            self._env.set(stmt.names[0].name, v.value, v.type)

    def _exec_leer(self, stmt: Leer) -> None:
        if not stmt.args:
            self._discard_line()
            return
        for arg in stmt.args:
            self._steps += 1  # each Leer argument = 1 step (SPEC §(g))
            if not isinstance(arg, Identifier):
                raise self._err("ERR_TYPE", "Leer solo acepta variables", arg)
            token = self._next_token(stmt)
            declared = self._env.get_type(arg.name)
            v = self._parse_token(token, declared, arg)
            self._env.set(arg.name, v.value, v.type)

    def _exec_escribir(self, stmt: Escribir) -> None:
        parts: list[str] = []
        for arg in stmt.args:
            self._steps += 1  # each Escribir argument = 1 step (SPEC §(g))
            v = self._eval_expr(arg)
            parts.append(format_value(v.value))
        text = "".join(parts)
        if stmt.sin_saltar:
            self._output += text
        else:
            self._output += text + "\n"

    def _exec_si(self, stmt: Si) -> None:
        if self._eval_condition(stmt.condition):
            self._exec_block(stmt.then_block)
        else:
            self._exec_block(stmt.else_block)

    def _exec_segun(self, stmt: Segun) -> None:
        v = self._eval_expr(stmt.expr)
        if v.type != ENTERO:
            raise self._err("ERR_TYPE", "Segun requiere una expresión Entero", stmt)
        for case in stmt.cases:
            if case.label is None:
                continue  # De Otro Modo has no condition to check
            self._steps += 1  # each case check = 1 step (SPEC §(g))
            if case.label == v.value:
                self._exec_block(case.block)
                return
        for case in stmt.cases:
            if case.label is None:
                self._exec_block(case.block)
                return

    def _exec_mientras(self, stmt: Mientras) -> None:
        while self._eval_condition(stmt.condition):
            self._exec_block(stmt.block)

    def _exec_repetir(self, stmt: Repetir) -> None:
        while True:
            self._exec_block(stmt.block)
            if self._eval_condition(stmt.condition):
                return

    def _exec_hacer_mientras_que(self, stmt: HacerMientrasQue) -> None:
        while True:
            self._exec_block(stmt.block)
            if not self._eval_condition(stmt.condition):
                return

    def _exec_para(self, stmt: Para) -> None:
        start = self._eval_expr(stmt.start)
        end = self._eval_expr(stmt.end)
        step = self._eval_expr(stmt.step) if stmt.step is not None else Value(1, ENTERO)
        if not _is_numeric(start) or not _is_numeric(end) or not _is_numeric(step):
            raise self._err("ERR_TYPE", "Para requiere límites numéricos", stmt)
        # The loop variable's type is the declared type, else Real when any
        # bound/step is Real, else Entero.
        declared = self._env.get_type(stmt.var.name)
        if declared is not None:
            var_type = declared
        elif any(t.type == REAL for t in (start, end, step)):
            var_type = REAL
        else:
            var_type = ENTERO
        current = self._convert(start, var_type, stmt).value
        self._env.set(stmt.var.name, current, var_type)
        while True:
            self._steps += 1  # iteration check = 1 step (SPEC §(g))
            if step.value >= 0:
                done = current > end.value
            else:
                done = current < end.value
            if done:
                return
            self._exec_block(stmt.block)
            self._steps += 1  # implicit increment = 1 step (SPEC §(g))
            current = current + step.value
            if type_of(current) != var_type:
                current = self._convert(
                    Value(current, type_of(current)), var_type, stmt
                ).value
            self._env.set(stmt.var.name, current, var_type)

    # -- conditions ---------------------------------------------------------

    def _eval_condition(self, expr: object) -> bool:
        self._steps += 1  # condition evaluation = 1 step (SPEC §(g))
        v = self._eval_expr(expr)
        if v.type != LOGICO:
            raise self._err("ERR_TYPE", "la condición debe ser Logico", expr)
        return v.value

    # -- expressions --------------------------------------------------------

    def _eval_expr(self, expr: object) -> Value:
        if isinstance(expr, IntegerLiteral):
            return Value(expr.value, ENTERO)
        if isinstance(expr, RealLiteral):
            return Value(expr.value, REAL)
        if isinstance(expr, BooleanLiteral):
            return Value(expr.value, LOGICO)
        if isinstance(expr, StringLiteral):
            # SPEC §(a): character literals are double-quoted single chars.
            text = self._strip_quotes(expr.value)
            return Value(text, CARACTER if len(text) == 1 else CADENA)
        if isinstance(expr, Identifier):
            return self._read_var(expr)
        if isinstance(expr, UnaryOp):
            return self._eval_unary(expr)
        if isinstance(expr, BinaryOp):
            return self._eval_binary(expr)
        if isinstance(expr, FunctionCall):
            raise self._err(
                "ERR_TYPE", f"función no implementada (todo 6): {expr.name}", expr
            )
        if isinstance(expr, (ArrayIndex, ArrayLiteral)):
            raise self._err("ERR_DIM", "arrays no implementados (todo 6)", expr)
        raise self._err(
            "ERR_TYPE", f"expresión no soportada: {type(expr).__name__}", expr
        )

    def _read_var(self, expr: Identifier) -> Value:
        if not self._env.has(expr.name):
            raise self._err("ERR_TYPE", f"variable no definida: {expr.name}", expr)
        if not self._env.is_initialized(expr.name):
            raise self._err("ERR_TYPE", f"variable no inicializada: {expr.name}", expr)
        return Value(self._env.get(expr.name), self._env.get_type(expr.name))

    def _eval_unary(self, expr: UnaryOp) -> Value:
        self._steps += 1  # operator evaluation = 1 step (SPEC §(g))
        operand = self._eval_expr(expr.operand)
        if expr.op in ("+", "-"):
            if operand.type not in (ENTERO, REAL):
                raise self._err(
                    "ERR_TYPE", f"operador '{expr.op}' requiere un número", expr
                )
            if expr.op == "+":
                return Value(+operand.value, operand.type)
            return Value(-operand.value, operand.type)
        if expr.op == "~":
            if operand.type != LOGICO:
                raise self._err("ERR_TYPE", "operador '~' requiere un Logico", expr)
            return Value(not operand.value, LOGICO)
        raise self._err("ERR_TYPE", f"operador unario no soportado: {expr.op}", expr)

    def _eval_binary(self, expr: BinaryOp) -> Value:
        self._steps += 1  # operator evaluation = 1 step (SPEC §(g))
        left = self._eval_expr(expr.left)
        right = self._eval_expr(expr.right)
        op = expr.op
        if op in ("&", "|"):
            if left.type != LOGICO or right.type != LOGICO:
                raise self._err(
                    "ERR_TYPE", "operadores lógicos requieren operandos Logico", expr
                )
            if op == "&":
                return Value(left.value and right.value, LOGICO)
            return Value(left.value or right.value, LOGICO)
        if op in ("<", ">", "=", "==", "<>", "<=", ">="):
            return self._eval_relational(op, left, right, expr)
        return self._eval_arithmetic(op, left, right, expr)

    def _eval_relational(
        self, op: str, left: Value, right: Value, expr: object
    ) -> Value:
        lt, rt = left.type, right.type
        if lt == LOGICO and rt == LOGICO:
            if op in ("=", "=="):
                return Value(left.value == right.value, LOGICO)
            if op == "<>":
                return Value(left.value != right.value, LOGICO)
            raise self._err("ERR_TYPE", "no se puede ordenar valores Logico", expr)
        if lt in (ENTERO, REAL) and rt in (ENTERO, REAL):
            lv, rv = left.value, right.value
            if op == "<":
                return Value(lv < rv, LOGICO)
            if op == ">":
                return Value(lv > rv, LOGICO)
            if op in ("=", "=="):
                return Value(lv == rv, LOGICO)
            if op == "<>":
                return Value(lv != rv, LOGICO)
            if op == "<=":
                return Value(lv <= rv, LOGICO)
            if op == ">=":
                return Value(lv >= rv, LOGICO)
        if lt in (CADENA, CARACTER) and rt in (CADENA, CARACTER):
            lv, rv = left.value, right.value
            if op == "<":
                return Value(lv < rv, LOGICO)
            if op == ">":
                return Value(lv > rv, LOGICO)
            if op in ("=", "=="):
                return Value(lv == rv, LOGICO)
            if op == "<>":
                return Value(lv != rv, LOGICO)
            if op == "<=":
                return Value(lv <= rv, LOGICO)
            if op == ">=":
                return Value(lv >= rv, LOGICO)
        raise self._err(
            "ERR_TYPE",
            f"no se pueden comparar {lt} y {rt} con '{op}'",
            expr,
        )

    def _eval_arithmetic(
        self, op: str, left: Value, right: Value, expr: object
    ) -> Value:
        if left.type not in (ENTERO, REAL) or right.type not in (ENTERO, REAL):
            raise self._err(
                "ERR_TYPE",
                f"operación '{op}' requiere operandos numéricos",
                expr,
            )
        lv, rv = left.value, right.value
        if op == "+":
            return Value(lv + rv, _num_type(left.type, right.type))
        if op == "-":
            return Value(lv - rv, _num_type(left.type, right.type))
        if op == "*":
            return Value(lv * rv, _num_type(left.type, right.type))
        if op == "/":
            if rv == 0:
                raise self._err("ERR_DIV0", "división por cero", expr)
            return Value(lv / rv, REAL)  # int / int -> real (SPEC §(c))
        if op in ("%", "MOD"):
            li, ri = int(lv), int(rv)  # reals are truncated first (SPEC §(c))
            if ri == 0:
                raise self._err("ERR_DIV0", "módulo por cero", expr)
            return Value(li % ri, ENTERO)
        if op == "^":
            result = lv**rv
            if left.type == ENTERO and right.type == ENTERO and rv >= 0:
                return Value(result, ENTERO)
            return Value(result, REAL)
        raise self._err("ERR_TYPE", f"operador no soportado: {op}", expr)

    # -- conversion ---------------------------------------------------------

    def _convert(self, v: Value, to_type: str, node: object) -> Value:
        if v.type == to_type:
            return v
        try:
            return Value(convert_value(v.value, v.type, to_type), to_type)
        except ValueError as e:
            raise self._err(
                "ERR_TYPE",
                f"no se puede convertir {v.type} a {to_type}: {e}",
                node,
            ) from None

    # -- Leer input ---------------------------------------------------------

    def _next_token(self, node: object) -> str:
        while self._line_pos < len(self._input_lines):
            line = self._input_lines[self._line_pos]
            if self._token_pos < len(line):
                token = line[self._token_pos]
                self._token_pos += 1
                return token
            self._line_pos += 1
            self._token_pos = 0
        raise self._err("ERR_EOF_INPUT", "fin de entrada inesperado", node)

    def _discard_line(self) -> None:
        self._line_pos += 1
        self._token_pos = 0

    def _parse_token(self, token: str, declared: str | None, node: object) -> Value:
        if declared is None:
            # Infer the type from the token (SPEC §(f) type inference).
            if _INT_RE.match(token) is not None:
                return Value(int(token), ENTERO)
            if _REAL_RE.match(token) is not None:
                return Value(float(token), REAL)
            low = token.lower()
            if low == "verdadero":
                return Value(True, LOGICO)
            if low == "falso":
                return Value(False, LOGICO)
            if len(token) == 1:
                return Value(token, CARACTER)
            return Value(token, CADENA)
        if declared == ENTERO:
            if _INT_RE.match(token) is not None:
                return Value(int(token), ENTERO)
            raise self._err("ERR_TYPE", f"no se pudo leer '{token}' como Entero", node)
        if declared == REAL:
            if _REAL_RE.match(token) is not None or _INT_RE.match(token) is not None:
                return Value(float(token), REAL)
            raise self._err("ERR_TYPE", f"no se pudo leer '{token}' como Real", node)
        if declared == LOGICO:
            low = token.lower()
            if low == "verdadero":
                return Value(True, LOGICO)
            if low == "falso":
                return Value(False, LOGICO)
            raise self._err("ERR_TYPE", f"no se pudo leer '{token}' como Logico", node)
        if declared == CARACTER:
            if len(token) == 1:
                return Value(token, CARACTER)
            raise self._err(
                "ERR_TYPE", f"no se pudo leer '{token}' como Caracter", node
            )
        if declared == CADENA:
            return Value(token, CADENA)
        raise self._err("ERR_TYPE", f"tipo desconocido: {declared}", node)

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _strip_quotes(raw: str) -> str:
        if len(raw) >= 2 and raw[0] in "\"'" and raw[-1] == raw[0]:
            return raw[1:-1]
        return raw

    @staticmethod
    def _err(code: str, message: str, node: object) -> RuntimeError:
        return RuntimeError(code, message, node.line, node.col)


def _is_numeric(v: Value) -> bool:
    return v.type in (ENTERO, REAL)


def _num_type(a: str, b: str) -> str:
    return REAL if a == REAL or b == REAL else ENTERO


def evaluate(program: Program, input_text: str = "", seed: int = 0) -> EvalResult:
    """Evaluate ``program`` and return output, steps and any runtime error.

    ``input_text`` is the program's standard input (split on ``\\s+`` per
    SPEC §(f)). ``seed`` is reserved for AZAR (todo 6) and currently unused.
    """
    return Evaluator(input_text=input_text, seed=seed).run(program)
