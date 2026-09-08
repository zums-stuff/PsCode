"""
Re-export shim that lets the API enqueue ``process_run`` by string path
(``infra.worker.jobs.process_run``) while the canonical implementation
stays in ``infra/worker/worker.py``.

RQ requires a *module path* (not a function reference) when the job is
enqueued in one process and executed in another.  ``__main__``-scoped
functions can't cross that boundary — RQ raises
``ValueError: Functions from the __main__ module cannot be processed
by workers``.

This module exists so the API can do::

    q.enqueue("infra.worker.jobs.process_run", run_id=run.id)

and the worker subprocess can resolve it as
``from infra.worker.jobs import process_run`` — which simply re-exports
the function from ``worker.py`` where it lives next to its helpers
(``PersistHooks``, ``run_sandboxed``, ``_verdict_from_sandbox``, etc.).
"""

from __future__ import annotations

from infra.worker.worker import process_run

__all__ = ["process_run"]
