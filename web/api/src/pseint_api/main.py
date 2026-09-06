"""FastAPI application factory for pseint-api (todo 17/18/20)."""

from __future__ import annotations

from fastapi import FastAPI

from . import ws
from .ratelimit import RateLimitMiddleware
from .routes import (
    assignments,
    auth,
    classes,
    contests,
    forums,
    problems,
    runs,
    scoreboard,
    similarity,
    test_cases,
    validate,
)


def create_app(limiter=None) -> FastAPI:
    app = FastAPI(title="pseint-api")
    # Todo 20: rate limiting wraps all routes; tests inject an in-memory limiter.
    app.add_middleware(RateLimitMiddleware, limiter=limiter)
    app.include_router(auth.router)
    app.include_router(problems.router)
    app.include_router(test_cases.router)
    app.include_router(classes.router)
    app.include_router(assignments.router)
    app.include_router(contests.router)
    app.include_router(scoreboard.router)
    app.include_router(runs.router)
    app.include_router(validate.router)
    app.include_router(forums.router)
    app.include_router(similarity.router)
    app.include_router(ws.router)  # WS surface wired after all REST routes
    return app
