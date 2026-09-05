"""Budget and quota constants for the judge (todo 15).

Single source of truth for the resource limits the judge enforces and the
practice-mode quota the API (todo 18) and the sandbox worker (todo 34)
consume.  Everything here is a pure constant — nothing is randomized and no
system clock is consulted (SPEC §(h) determinism).

Seed plumbing (SPEC §(h)): the runner (todo 10) already passes each test
case's ``seed`` to the engine as ``--seed`` via ``tc.get("seed", 0)``, so
contest/assignment runs default to ``DEFAULT_SEED`` (0).  This module
centralizes and documents that default; it does not change the runner's
behavior.

The runner's own ``_DEFAULT_OUTPUT_CAP`` (1 MB) matches ``MAX_OUTPUT_BYTES``;
the worker (todo 34) should consume these constants instead of re-declaring
them.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

# --- Default resource limits (todo 15 contract) ---------------------------
MAX_SOURCE_BYTES = 65_536  # 64 KB — submission source cap
MAX_INPUT_BYTES = 65_536  # 64 KB — per-test-case input cap
MAX_OUTPUT_BYTES = 1_048_576  # 1 MB — engine output cap (M13)
WALL_LIMIT_MS = 5_000  # 5 s — worker-side wall-clock cap
CPU_LIMIT_MS = 3_000  # 3 s — CPU time cap
MEM_LIMIT_MB = 128  # 128 MB — memory cap

# --- Practice-mode quota (M13) --------------------------------------------
PRACTICE_RUNS_PER_MIN = 10  # practice runs per minute per user

# --- Seed default (SPEC §(h)) ---------------------------------------------
DEFAULT_SEED = 0  # AZAR/RC seeded per run; contest/assignment default 0


@dataclass(frozen=True)
class Limits:
    """Effective resource limits for one problem (defaults + overrides)."""

    max_source_bytes: int = MAX_SOURCE_BYTES
    max_input_bytes: int = MAX_INPUT_BYTES
    max_output_bytes: int = MAX_OUTPUT_BYTES
    wall_limit_ms: int = WALL_LIMIT_MS
    cpu_limit_ms: int = CPU_LIMIT_MS
    mem_limit_mb: int = MEM_LIMIT_MB


def effective_limits(problem: dict | None = None) -> Limits:
    """Return the effective limits for ``problem``.

    ``problem`` may carry per-problem overrides using the same field names as
    ``Limits`` (e.g. ``{"max_output_bytes": 2_097_152}``); any present key
    wins over the default.  ``None`` or an empty dict yields pure defaults.
    Keys that are not ``Limits`` fields (e.g. ``step_budget``, handled by the
    runner/complexity modules) are ignored.
    """
    if not problem:
        return Limits()
    overrides = {
        key: value
        for key, value in problem.items()
        if key in Limits.__dataclass_fields__
    }
    return replace(Limits(), **overrides)
