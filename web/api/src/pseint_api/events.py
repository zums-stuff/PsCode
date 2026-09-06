"""WebSocket event payload helpers for pseint-api (todo 19).

Event shape (plan todo 19)::

    {"type": "submission" | "run",
     "run_id": int,
     "status": str,
     "per_case": [{"case_index": int, "verdict": str,
                   "steps": int | None, "wall_ms": int | None}]}

Design choice (documented in the plan): the worker emits ONE ``run`` event
per run after all per_case entries are filled; ``per_case`` is always ordered
by case_index.  ``submission`` events carry an empty ``per_case`` and are
emitted when a run is enqueued.
"""

from __future__ import annotations

from typing import Any

PerCase = list[dict[str, Any]]


def make_run_event(
    run_id: int, status: str, per_case: PerCase | None = None
) -> dict[str, Any]:
    """Build a ``run`` event for ``run_id`` with the given status and cases."""
    return {
        "type": "run",
        "run_id": run_id,
        "status": status,
        "per_case": per_case or [],
    }


def make_submission_event(run_id: int, status: str = "queued") -> dict[str, Any]:
    """Build a ``submission`` event (run enqueued, no per-case data yet)."""
    return {
        "type": "submission",
        "run_id": run_id,
        "status": status,
        "per_case": [],
    }
