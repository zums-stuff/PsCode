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

# All five type names, for validation.
TYPE_NAMES = frozenset({ENTERO, REAL, LOGICO, CARACTER, CADENA})


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
    """One variable scope: values plus their fixed/inferred types."""

    values: dict[str, object] = field(default_factory=dict)
    types: dict[str, str] = field(default_factory=dict)


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

    def has(self, name: str) -> bool:
        """True if the variable is known in any scope (declared or assigned)."""
        return any(name in s.values or name in s.types for s in self._scopes)

    def is_initialized(self, name: str) -> bool:
        """True if the variable has been assigned a value."""
        return any(name in s.values for s in self._scopes)

    def get(self, name: str) -> object:
        """Return the variable's value (innermost scope wins)."""
        for s in reversed(self._scopes):
            if name in s.values:
                return s.values[name]
        raise KeyError(name)

    def get_type(self, name: str) -> str | None:
        """Return the variable's fixed type, or ``None`` if untyped."""
        for s in reversed(self._scopes):
            if name in s.types:
                return s.types[name]
        return None

    def set(self, name: str, value: object, value_type: str) -> None:
        """Assign ``value`` to ``name`` and fix its type to ``value_type``.

        The write lands in the innermost scope that already knows the name
        (so a declared outer variable is updated in place); otherwise it is
        created in the innermost scope.
        """
        for s in reversed(self._scopes):
            if name in s.values or name in s.types:
                s.values[name] = value
                s.types[name] = value_type
                return
        self._scopes[-1].values[name] = value
        self._scopes[-1].types[name] = value_type
