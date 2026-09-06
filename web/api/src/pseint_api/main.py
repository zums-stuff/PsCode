"""FastAPI application factory for pseint-api (todo 17/18/20).

The ``/healthz`` and ``/readyz`` endpoints are added here (todo 36) so the
compose stack can probe the API without going through the rate limiter or
requiring auth.  ``/healthz`` is the liveness probe (always 200 while the
process is alive).  ``/readyz`` is the readiness probe — it returns 200 only
when both Postgres and Redis are reachable, so Caddy / compose can take a
degraded API out of rotation until the DBs come back.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from sqlalchemy import text

from . import config, ws
from .db import make_engine
from .ratelimit import RateLimitMiddleware
from .routes import (
    assignments,
    auth,
    classes,
    contests,
    forums,
    listings,
    problems,
    runs,
    scoreboard,
    similarity,
    test_cases,
    validate,
)

logger = logging.getLogger(__name__)


def create_app(limiter=None) -> FastAPI:
    app = FastAPI(title="pseint-api")
    # Todo 20: rate limiting wraps all routes; tests inject an in-memory limiter.
    app.add_middleware(RateLimitMiddleware, limiter=limiter)

    # --- Liveness / readiness probes (todo 36) -----------------------------
    # Both endpoints are skipped by the rate limiter (prefixes ``/health`` and
    # ``/ready`` are in ``SKIP_PREFIXES``).  They never raise — readiness
    # returns a non-2xx status that compose/Caddy can use to take the API
    # out of rotation until the DBs recover.

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict:
        """Liveness probe — always 200 while the process is alive."""
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    def readyz() -> dict:
        """Readiness probe — 200 when Postgres and Redis are reachable.

        Degraded dependencies are reported as 503 with a ``degraded: true``
        body so operators can see which dependency is down.  Each check has
        its own short timeout so a single slow dependency cannot stall the
        probe.
        """
        deps: dict[str, str] = {}

        # Postgres: use the API's own engine (the deps.py module wires it
        # via config.database_url(); reach in for a fresh connection so we
        # don't depend on any session lifecycle).
        try:
            eng = make_engine(config.database_url())
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
            deps["postgres"] = "ok"
        except Exception as e:  # noqa: BLE001 - probe must never raise
            logger.warning("readyz: postgres unreachable: %s", e)
            deps["postgres"] = "down"

        # Redis: read REDIS_URL from the environment with the same default
        # the worker / rate limiter use so the readiness check matches the
        # real client wiring.
        try:
            import os

            import redis

            r = redis.Redis.from_url(
                os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
                socket_connect_timeout=1,
                socket_timeout=1,
            )
            r.ping()
            deps["redis"] = "ok"
        except Exception as e:  # noqa: BLE001 - probe must never raise
            logger.warning("readyz: redis unreachable: %s", e)
            deps["redis"] = "down"

        all_ok = all(v == "ok" for v in deps.values())
        payload = {"status": "ok" if all_ok else "degraded", "deps": deps}
        if not all_ok:
            from fastapi.responses import JSONResponse

            return JSONResponse(status_code=503, content=payload)
        return payload

    app.include_router(auth.router)
    app.include_router(problems.router)
    app.include_router(test_cases.router)
    app.include_router(classes.router)
    app.include_router(assignments.router)
    app.include_router(contests.router)
    app.include_router(scoreboard.router)
    app.include_router(listings.router)  # paginated lists (todo 21)
    app.include_router(runs.router)
    app.include_router(validate.router)
    app.include_router(forums.router)
    app.include_router(similarity.router)
    app.include_router(similarity.admin_router)  # todo 39 anticheat surface
    app.include_router(ws.router)  # WS surface wired after all REST routes
    return app
