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

import math
import random
import re
import sys
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
    ARREGLO,
    CADENA,
    CARACTER,
    ENTERO,
    LOGICO,
    REAL,
    Array,
    Env,
    EvalResult,
    RuntimeError,
)

# Recursion depth cap — SPEC §(i) + Diff-from-Official #15 (1000 frames).
# NOTE: the plan text says 500, but SPEC pins 1000; SPEC is authoritative.
_MAX_RECURSION = 1000

# Each PseInt call frame costs several Python frames (evaluator -> block ->
# stmt -> expr -> call -> ...), so Python's default 1000-frame limit would
# fire before our SPEC cap. Raise it with margin for the 1000-frame cap.
sys.setrecursionlimit(20000)

# Array caps (todo 6): max 3 dims, max 1_000_000 elements per array, and a
# per-run total of 4_000_000 array elements -> ERR_DIM.
_MAX_DIMS = 3
_MAX_ARRAY_ELEMENTS = 1_000_000
_MAX_TOTAL_ARRAY_ELEMENTS = 4_000_000

# Fixed deterministic stubs (SPEC §(h)).
_FECHA_ACTUAL = "2026-01-01"
_HORA_ACTUAL = "12:00:00"

# Alphabet for RC(n): deterministic lowercase letters.
_RC_ALPHABET = "abcdefghijklmnopqrstuvwxyz"


class _ReturnSignal(Exception):  # noqa: N818 — control flow, not an error
    """Internal control-flow signal carrying a Funcion's return value."""

    def __init__(self, value: Value) -> None:
        super().__init__()
        self.value = value

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
    if isinstance(value, Array):
        return ARREGLO
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
        self._seed = seed
        self._rng = random.Random(seed)  # AZAR/RC (SPEC §(h))
        self._subprocesos: dict[str, SubProceso] = {}
        self._total_array_elements = 0
        self._in_function = False

    # -- public API ---------------------------------------------------------

    def run(self, program: Program) -> EvalResult:
        """Execute the program, returning output, steps and any error."""
        try:
            self._collect_subprocesos(program)
            self._exec_block(program.body)
            return EvalResult(output=self._output, steps=self._steps, error=None)
        except RuntimeError as e:
            return EvalResult(output=self._output, steps=self._steps, error=e)

    def _collect_subprocesos(self, program: Program) -> None:
        """Index SubProceso/Funcion declarations by name for call dispatch."""
        for stmt in program.body:
            if isinstance(stmt, SubProceso):
                self._subprocesos[stmt.name.name] = stmt

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
            pass  # declaration; indexed by _collect_subprocesos
        elif isinstance(stmt, Retornar):
            if not self._in_function:
                raise self._err(
                    "ERR_TYPE", "Retornar solo es válido dentro de una función", stmt
                )
            raise _ReturnSignal(self._eval_expr(stmt.value))
        elif isinstance(stmt, SubProcCall):
            self._exec_subproc_call(stmt)
        elif isinstance(stmt, Dimension):
            self._exec_dimension(stmt)
        elif isinstance(stmt, Redimensionar):
            self._exec_redimensionar(stmt)
        else:
            raise self._err(
                "ERR_TYPE", f"sentencia no soportada: {type(stmt).__name__}", stmt
            )

    def _exec_assignment(self, stmt: Assignment) -> None:
        target = stmt.target
        if isinstance(target, ArrayIndex):
            self._exec_array_assignment(target, stmt.value, stmt)
            return
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

    # -- subprocesos / funciones --------------------------------------------

    def _exec_subproc_call(self, stmt: SubProcCall) -> None:
        sub = self._subprocesos.get(stmt.name)
        if sub is None:
            raise self._err(
                "ERR_TYPE", f"subproceso no definido: {stmt.name}", stmt
            )
        self._call_subproceso(sub, stmt.args, stmt)

    def _call_subproceso(
        self, sub: SubProceso, args: list, node: object
    ) -> Value | None:
        """Execute a SubProceso/Funcion body in a fresh scope.

        Returns the Funcion's return value (or ``None`` for a SubProceso).
        The callee's statements count toward the caller's step total via the
        shared ``_steps`` counter; recursion is capped by ``_enter_frame``.
        """
        if len(args) != len(sub.params):
            raise self._err(
                "ERR_TYPE",
                f"la llamada a {sub.name.name} esperaba {len(sub.params)} "
                f"argumentos, recibió {len(args)}",
                node,
            )
        self._enter_frame(node)
        self._env.push_scope()
        prev_in_function = self._in_function
        self._in_function = sub.is_function
        try:
            for param, arg_expr in zip(sub.params, args):
                self._bind_param(param, arg_expr, node)
            if sub.is_function:
                try:
                    self._exec_block(sub.block)
                except _ReturnSignal as sig:
                    v = sig.value
                    if sub.return_type is not None:
                        v = self._convert(v, sub.return_type.lower(), node)
                    return v
                raise self._err(
                    "ERR_TYPE",
                    f"la función {sub.name.name} no retornó un valor",
                    node,
                )
            self._exec_block(sub.block)
            return None
        finally:
            self._in_function = prev_in_function
            self._env.pop_scope()
            self._exit_frame()

    def _bind_param(self, param: object, arg_expr: object, node: object) -> None:
        """Bind one call argument to a parameter.

        Por Referencia (and arrays by default) alias the caller's variable:
        the param name is not shadowed, so reads/writes resolve outward to
        the caller's scope. Por Valor binds a copy in the callee's scope.
        """
        if param.direction == "Por Referencia":
            if not isinstance(arg_expr, Identifier):
                raise self._err(
                    "ERR_TYPE", "Por Referencia requiere una variable", node
                )
            self._env.bind_reference(param.name.name, arg_expr.name)
            return
        v = self._eval_expr(arg_expr)
        if param.direction is None and v.type == ARREGLO:
            self._env.bind_reference(param.name.name, arg_expr.name)
            return
        if param.type_name is not None and param.type_name.lower() != v.type:
            v = self._convert(v, param.type_name.lower(), node)
        self._env.set(param.name.name, v.value, v.type)

    # -- arrays -------------------------------------------------------------

    def _exec_dimension(self, stmt: Dimension) -> None:
        sizes = self._eval_sizes(stmt.sizes, stmt)
        arr = self._make_array(sizes, stmt)
        self._env.set(stmt.name.name, arr, ARREGLO)

    def _exec_redimensionar(self, stmt: Redimensionar) -> None:
        name = stmt.name.name
        if not self._env.has(name):
            raise self._err("ERR_DIM", f"arreglo no declarado: {name}", stmt)
        if self._env.get_type(name) != ARREGLO:
            raise self._err("ERR_DIM", f"{name} no es un arreglo", stmt)
        arr = self._env.get(name)
        sizes = self._eval_sizes(stmt.sizes, stmt)
        old_total = arr.total()
        new_total = self._check_array_caps(
            sizes, stmt, exclude_current_total=old_total
        )
        old_data = arr.data
        arr.sizes = sizes
        arr.data = [None] * new_total
        for off in range(min(old_total, new_total)):
            arr.data[off] = old_data[off]
        self._total_array_elements = (
            self._total_array_elements - old_total + new_total
        )

    def _eval_sizes(self, size_exprs: list, node: object) -> list[int]:
        sizes: list[int] = []
        for s in size_exprs:
            v = self._eval_expr(s)
            if v.type != ENTERO:
                raise self._err("ERR_TYPE", "tamaño de arreglo debe ser Entero", node)
            sizes.append(v.value)
        return sizes

    def _make_array(self, sizes: list[int], node: object) -> Array:
        total = self._check_array_caps(sizes, node)
        self._total_array_elements += total
        return Array(sizes)

    def _check_array_caps(
        self, sizes: list[int], node: object, exclude_current_total: int = 0
    ) -> int:
        if len(sizes) > _MAX_DIMS:
            raise self._err(
                "ERR_DIM", f"máximo {_MAX_DIMS} dimensiones", node
            )
        total = 1
        for s in sizes:
            total *= s
        if total > _MAX_ARRAY_ELEMENTS:
            raise self._err(
                "ERR_DIM",
                f"arreglo excede {_MAX_ARRAY_ELEMENTS} elementos",
                node,
            )
        if (
            self._total_array_elements - exclude_current_total + total
            > _MAX_TOTAL_ARRAY_ELEMENTS
        ):
            raise self._err(
                "ERR_DIM",
                "total de elementos de arreglos excede el límite",
                node,
            )
        return total

    def _exec_array_assignment(
        self, target: ArrayIndex, value_expr: object, stmt: object
    ) -> None:
        self._steps += 1  # array indexing = operator evaluation (SPEC §(g))
        arr = self._resolve_array(target.array, stmt)
        v = self._eval_expr(value_expr)
        off = self._eval_indices(arr, target, stmt)
        arr.data[off] = v

    def _eval_array_index(self, expr: ArrayIndex) -> Value:
        self._steps += 1  # array indexing = operator evaluation (SPEC §(g))
        arr = self._resolve_array(expr.array, expr)
        off = self._eval_indices(arr, expr, expr)
        elem = arr.data[off]
        if elem is None:
            raise self._err(
                "ERR_TYPE", "elemento de arreglo no inicializado", expr
            )
        return elem

    def _eval_array_literal(self, expr: ArrayLiteral) -> Value:
        total = self._check_array_caps([len(expr.elements)], expr)
        elements = [self._eval_expr(e) for e in expr.elements]
        arr = Array([len(elements)])
        for i, v in enumerate(elements):
            arr.data[i] = v
        self._total_array_elements += total
        return Value(arr, ARREGLO)

    def _resolve_array(self, array_expr: object, node: object) -> Array:
        if not isinstance(array_expr, Identifier):
            raise self._err("ERR_DIM", "el arreglo debe ser un identificador", node)
        name = array_expr.name
        if not self._env.has(name):
            raise self._err("ERR_DIM", f"arreglo no declarado: {name}", node)
        if self._env.get_type(name) != ARREGLO:
            raise self._err("ERR_DIM", f"{name} no es un arreglo", node)
        return self._env.get(name)

    def _eval_indices(
        self, arr: Array, expr: object, node: object
    ) -> int:
        if isinstance(expr, ArrayIndex):
            index_exprs = [expr.index] + expr.indices
        else:
            raise self._err("ERR_TYPE", "índice de arreglo inválido", node)
        idx_vals: list[int] = []
        for ie in index_exprs:
            v = self._eval_expr(ie)
            if v.type != ENTERO:
                raise self._err("ERR_TYPE", "índice de arreglo debe ser Entero", node)
            idx_vals.append(v.value)
        if len(idx_vals) != len(arr.sizes):
            raise self._err(
                "ERR_DIM",
                "número de índices no coincide con las dimensiones",
                node,
            )
        off = 0
        for i, idx in enumerate(idx_vals):
            size = arr.sizes[i]
            if idx < 0 or idx >= size:
                raise self._err(
                    "ERR_BOUNDS",
                    f"índice {idx} fuera de límites [0, {size})",
                    node,
                )
            off = off * size + idx
        return off

    # -- built-ins (SPEC §(b)) ----------------------------------------------

    def _eval_function_call(self, expr: FunctionCall) -> Value:
        self._steps += 1  # function call = 1 step (SPEC §(g))
        name = expr.name.lower()
        if name in _BUILTIN_IMPL:
            return _BUILTIN_IMPL[name](self, expr)
        sub = self._subprocesos.get(expr.name)
        if sub is None or not sub.is_function:
            raise self._err("ERR_TYPE", f"función no definida: {expr.name}", expr)
        v = self._call_subproceso(sub, expr.args, expr)
        assert v is not None
        return v

    def _builtin_azar(self, expr: FunctionCall) -> Value:
        n = self._builtin_int_arg(expr, 0)
        if n <= 0:
            raise self._err(
                "ERR_TYPE", "AZAR requiere un límite positivo", expr
            )
        return Value(self._rng.randrange(n), ENTERO)

    def _builtin_rc(self, expr: FunctionCall) -> Value:
        self._builtin_int_arg(expr, 0)  # n is ignored; alphabet is fixed
        return Value(_RC_ALPHABET[self._rng.randrange(len(_RC_ALPHABET))], CARACTER)

    def _builtin_abs(self, expr: FunctionCall) -> Value:
        v = self._builtin_num_arg(expr, 0)
        return Value(abs(v.value), v.type)

    def _builtin_ln(self, expr: FunctionCall) -> Value:
        v = self._builtin_num_arg(expr, 0)
        if v.value <= 0:
            raise self._err(
                "ERR_TYPE", "LN requiere un argumento positivo", expr
            )
        return Value(math.log(v.value), REAL)

    def _builtin_exp(self, expr: FunctionCall) -> Value:
        v = self._builtin_num_arg(expr, 0)
        try:
            return Value(math.exp(v.value), REAL)
        except OverflowError:
            raise self._err(
                "ERR_TYPE", "EXP excede el rango numérico", expr
            ) from None

    def _builtin_sen(self, expr: FunctionCall) -> Value:
        v = self._builtin_num_arg(expr, 0)
        return Value(math.sin(v.value), REAL)

    def _builtin_cos(self, expr: FunctionCall) -> Value:
        v = self._builtin_num_arg(expr, 0)
        return Value(math.cos(v.value), REAL)

    def _builtin_atan(self, expr: FunctionCall) -> Value:
        v = self._builtin_num_arg(expr, 0)
        return Value(math.atan(v.value), REAL)

    def _builtin_trunc(self, expr: FunctionCall) -> Value:
        v = self._builtin_num_arg(expr, 0)
        return Value(int(v.value), ENTERO)

    def _builtin_redon(self, expr: FunctionCall) -> Value:
        v = self._builtin_num_arg(expr, 0)
        x = v.value
        rounded = math.floor(x + 0.5) if x >= 0 else math.ceil(x - 0.5)
        return Value(int(rounded), ENTERO)

    def _builtin_largo(self, expr: FunctionCall) -> Value:
        v = self._builtin_str_arg(expr, 0)
        return Value(len(v.value), ENTERO)

    def _builtin_subcadena(self, expr: FunctionCall) -> Value:
        s = self._builtin_str_arg(expr, 0)
        i = self._builtin_int_arg(expr, 1)
        j = self._builtin_int_arg(expr, 2)
        # 1-indexed, inclusive (official PseInt semantics).
        return Value(s.value[i - 1 : j], CADENA)

    def _builtin_concatenar(self, expr: FunctionCall) -> Value:
        a = self._builtin_str_arg(expr, 0)
        b = self._builtin_str_arg(expr, 1)
        return Value(a.value + b.value, CADENA)

    def _builtin_mayusculares(self, expr: FunctionCall) -> Value:
        v = self._builtin_str_arg(expr, 0)
        return Value(v.value.upper(), CADENA)

    def _builtin_minusculas(self, expr: FunctionCall) -> Value:
        v = self._builtin_str_arg(expr, 0)
        return Value(v.value.lower(), CADENA)

    def _builtin_fecha_actual(self, expr: FunctionCall) -> Value:
        return Value(_FECHA_ACTUAL, CADENA)

    def _builtin_hora_actual(self, expr: FunctionCall) -> Value:
        return Value(_HORA_ACTUAL, CADENA)

    def _builtin_int_arg(self, expr: FunctionCall, idx: int) -> int:
        if idx >= len(expr.args):
            raise self._err("ERR_TYPE", "faltan argumentos", expr)
        v = self._eval_expr(expr.args[idx])
        if v.type != ENTERO:
            raise self._err("ERR_TYPE", "el argumento debe ser Entero", expr)
        return v.value

    def _builtin_num_arg(self, expr: FunctionCall, idx: int) -> Value:
        if idx >= len(expr.args):
            raise self._err("ERR_TYPE", "faltan argumentos", expr)
        v = self._eval_expr(expr.args[idx])
        if v.type not in (ENTERO, REAL):
            raise self._err("ERR_TYPE", "el argumento debe ser numérico", expr)
        return v

    def _builtin_str_arg(self, expr: FunctionCall, idx: int) -> Value:
        if idx >= len(expr.args):
            raise self._err("ERR_TYPE", "faltan argumentos", expr)
        v = self._eval_expr(expr.args[idx])
        if v.type not in (CADENA, CARACTER):
            raise self._err("ERR_TYPE", "el argumento debe ser Cadena", expr)
        return v

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
            return self._eval_function_call(expr)
        if isinstance(expr, ArrayIndex):
            return self._eval_array_index(expr)
        if isinstance(expr, ArrayLiteral):
            return self._eval_array_literal(expr)
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
            try:
                result = lv**rv
            except OverflowError:
                raise self._err(
                    "ERR_TYPE", "potencia excede el rango numérico", expr
                ) from None
            if isinstance(result, complex):
                raise self._err(
                    "ERR_TYPE",
                    "potencia con base negativa y exponente fraccionario",
                    expr,
                )
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


# SPEC §(b) built-in dispatch: lowercase name -> evaluator method.
_BUILTIN_IMPL = {
    "azar": Evaluator._builtin_azar,
    "rc": Evaluator._builtin_rc,
    "abs": Evaluator._builtin_abs,
    "ln": Evaluator._builtin_ln,
    "exp": Evaluator._builtin_exp,
    "sen": Evaluator._builtin_sen,
    "cos": Evaluator._builtin_cos,
    "atan": Evaluator._builtin_atan,
    "trunc": Evaluator._builtin_trunc,
    "redon": Evaluator._builtin_redon,
    "largo": Evaluator._builtin_largo,
    "subcadena": Evaluator._builtin_subcadena,
    "concatenar": Evaluator._builtin_concatenar,
    "mayusculares": Evaluator._builtin_mayusculares,
    "minusculas": Evaluator._builtin_minusculas,
    "fechaactual": Evaluator._builtin_fecha_actual,
    "horaactual": Evaluator._builtin_hora_actual,
}


def evaluate(program: Program, input_text: str = "", seed: int = 0) -> EvalResult:
    """Evaluate ``program`` and return output, steps and any runtime error.

    ``input_text`` is the program's standard input (split on ``\\s+`` per
    SPEC §(f)). ``seed`` is reserved for AZAR (todo 6) and currently unused.
    """
    return Evaluator(input_text=input_text, seed=seed).run(program)
