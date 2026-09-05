"""Runtime support for the PseInt evaluator.

Defines the variable environment (``Env``), the runtime-error type
(``RuntimeError``) carrying one of the SPEC §(i) taxonomy codes, and the
``EvalResult`` produced by :func:`pseint_engine.evaluator.evaluate`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Normalized (lowercase) type names — SPEC §(c).
ENTERO = "entero"
REAL = "real"
LOGICO = "logico"
CARACTER = "caracter"
CADENA = "cadena"
# Array type — not one of the five scalar types; used for Dimension'd values.
ARREGLO = "arreglo"

# All five scalar type names, for validation.
TYPE_NAMES = frozenset({ENTERO, REAL, LOGICO, CARACTER, CADENA})


class Array:
    """A PseInt array: fixed dimensions plus a flat element store.

    ``sizes`` is the per-dimension length (row-major). ``data`` is a flat
    list of :class:`Value` objects (or ``None`` for uninitialized elements).
    The object is mutable and shared by reference, so a by-reference array
    parameter mutates the caller's array in place.
    """

    __slots__ = ("sizes", "data")

    def __init__(self, sizes: list[int]) -> None:
        self.sizes = list(sizes)
        total = 1
        for s in self.sizes:
            total *= s
        self.data: list = [None] * total

    def total(self) -> int:
        """Total number of elements (product of the dimension sizes)."""
        return len(self.data)


class RuntimeError(Exception):
    """A runtime error in PseInt execution.

    ``code`` is one of the SPEC §(i) taxonomy codes (``ERR_DIV0``,
    ``ERR_TYPE``, ``ERR_BOUNDS``, ``ERR_DIM``, ``ERR_RECURSION``,
    ``ERR_EOF_INPUT``, ``ERR_STEP_LIMIT``, ``ERR_OUTPUT_CAP``).
    ``line`` is 1-based and ``col`` is 0-based, matching the lexer
    convention. All runtime errors immediately halt execution.
    """

    def __init__(self, code: str, message: str, line: int, col: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.line = line
        self.col = col


@dataclass
class EvalResult:
    """The outcome of evaluating a program.

    ``output`` is the accumulated program output (Escribir), ``steps`` the
    exact step count per SPEC §(g), and ``error`` the first runtime error,
    or ``None`` when the program ran to completion.
    """

    output: str = ""
    steps: int = 0
    error: RuntimeError | None = None


@dataclass
class _Scope:
    """One variable scope: values, fixed/inferred types, and aliases.

    ``refs`` maps a by-reference parameter name to the caller's variable
    name it aliases (used by SubProceso/Funcion Por Referencia params).
    """

    values: dict[str, object] = field(default_factory=dict)
    types: dict[str, str] = field(default_factory=dict)
    refs: dict[str, str] = field(default_factory=dict)


@dataclass
class Env:
    """Variable environment with a scope stack.

    The global scope is created on construction; ``push_scope`` /
    ``pop_scope`` add and remove inner scopes (used by SubProceso/Funcion
    calls in todo 6). Reads resolve outward (innermost scope first); writes
    go to the innermost scope that already knows the name, otherwise to the
    innermost scope — so a variable's type is fixed once inferred and
    re-binding is not possible.
    """

    _scopes: list[_Scope] = field(default_factory=lambda: [_Scope()])

    def push_scope(self) -> None:
        """Enter a new inner scope."""
        self._scopes.append(_Scope())

    def pop_scope(self) -> None:
        """Leave the innermost scope."""
        self._scopes.pop()

    def declare(self, name: str, type_name: str | None) -> None:
        """Pre-declare a variable (from ``Definir``).

        ``type_name`` is normalized to lowercase. ``None`` (a bare
        ``Definir x``) is a no-op: the variable stays untyped and its type
        is inferred from the first assignment.
        """
        if type_name is not None:
            self._scopes[-1].types[name] = type_name.lower()

    def bind_reference(self, name: str, target: str) -> None:
        """Alias ``name`` (a by-reference param) to the caller's ``target``.

        Reads and writes of ``name`` forward to ``target`` in the caller's
        scope, so mutations are visible at the caller.
        """
        self._scopes[-1].refs[name] = target

    def _resolve(self, name: str) -> tuple[int, str] | None:
        """Return ``(scope_index, actual_name)`` for ``name``, following refs.

        Returns ``None`` when ``name`` is not bound in any scope. A reference
        alias resolves to its target in an outer scope.
        """
        for i in reversed(range(len(self._scopes))):
            s = self._scopes[i]
            if name in s.refs:
                target = s.refs[name]
                for j in reversed(range(i)):
                    ts = self._scopes[j]
                    if target in ts.values or target in ts.types:
                        return j, target
                return None
            if name in s.values or name in s.types:
                return i, name
        return None

    def has(self, name: str) -> bool:
        """True if the variable is known in any scope (declared or assigned)."""
        return self._resolve(name) is not None

    def is_initialized(self, name: str) -> bool:
        """True if the variable has been assigned a value."""
        r = self._resolve(name)
        if r is None:
            return False
        i, actual = r
        return actual in self._scopes[i].values

    def get(self, name: str) -> object:
        """Return the variable's value (innermost scope wins)."""
        r = self._resolve(name)
        if r is None:
            raise KeyError(name)
        i, actual = r
        return self._scopes[i].values[actual]

    def get_type(self, name: str) -> str | None:
        """Return the variable's fixed type, or ``None`` if untyped."""
        r = self._resolve(name)
        if r is None:
            return None
        i, actual = r
        return self._scopes[i].types.get(actual)

    def set(self, name: str, value: object, value_type: str) -> None:
        """Assign ``value`` to ``name`` and fix its type to ``value_type``.

        The write lands in the innermost scope that already knows the name
        (so a declared outer variable is updated in place); otherwise it is
        created in the innermost scope.
        """
        r = self._resolve(name)
        if r is not None:
            i, actual = r
            self._scopes[i].values[actual] = value
            self._scopes[i].types[actual] = value_type
            return
        self._scopes[-1].values[name] = value
        self._scopes[-1].types[name] = value_type
