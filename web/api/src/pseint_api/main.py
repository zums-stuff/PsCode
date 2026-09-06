"""FastAPI application factory for pseint-api (todo 17/18/20/36/40).

The ``/healthz`` and ``/readyz`` endpoints are added here (todo 36) so the
compose stack can probe the API without going through the rate limiter or
requiring auth.  ``/healthz`` is the liveness probe (always 200 while the
process is alive).  ``/readyz`` is the readiness probe — it returns 200 only
when both Postgres and Redis are reachable, so Caddy / compose can take a
degraded API out of rotation until the DBs come back.

Todo 40 (deployment hardening) adds:
    * CORS middleware driven by ``CORS_ALLOW_ORIGINS`` env (same-origin by
      default — M9/plan §CORS).  Wildcards are NOT exposed; each origin is
      an exact match so the API rejects cross-origin browser calls unless
      an admin opts them in.
    * Structured JSON logging via :class:`JsonFormatter` — one log line
      per event with timestamp, level, logger, message and request_id
      (when set by the request middleware).  Hand-rolled (no extra dep)
      because the format is trivial and operators already grep Caddy's
      JSON access logs in the same shape.
    * SECRET_KEY startup validation: :func:`_validate_secrets` runs the
      first time the app is built and refuses to construct the FastAPI
      instance if the key is missing / weak / placeholder.  Same check
      fires from every code path that signs or verifies a JWT.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from typing import Any

from fastapi import FastAPI, Request
from sqlalchemy import text
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response

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

_RESERVED_LOG_FIELDS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "asctime",
        "taskName",
    }
)


class JsonFormatter(logging.Formatter):
    """Minimal JSON log formatter (todo 40 / plan §JSON structured logs).

    Emits one JSON object per log record with a stable schema:

        {"ts": "...", "level": "...", "logger": "...", "message": "...",
         "request_id": "..." (optional), ... extras ...}

    No external dep; the project's venv already has ``json`` + ``logging``.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime(
                "%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)
            )
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None)
        if request_id:
            payload["request_id"] = request_id
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_FIELDS or key.startswith("_"):
                continue
            if key in payload:
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = repr(value)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_json_logging(level: str | int | None = None) -> None:
    """Install the JSON formatter on the root logger (todo 40).

    Idempotent: a no-op when the root handler already uses ``JsonFormatter``
    (e.g. uvicorn already configured it).  Replaces any non-JSON handler so
    docker logs are uniformly parseable.
    """
    root = logging.getLogger()
    if level is not None:
        root.setLevel(level)
    if any(
        isinstance(h.formatter, JsonFormatter)
        for h in root.handlers
        if h.formatter is not None
    ):
        return
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]


class RequestIdMiddleware:
    """Tag every request with a UUIDv4 ``X-Request-Id`` (todo 40 / runbook).

    Honors an inbound ``X-Request-Id`` (so a CDN / load balancer can
    propagate its own trace id) and emits the same id back in the response
    header.  Stashes the id on ``request.state.request_id`` so the JSON
    log formatter can include it.
    """

    HEADER = "X-Request-Id"
    _HEADER_BYTES = b"x-request-id"

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        inbound = None
        for k, v in scope.get("headers", []):
            # ASGI headers are (bytes, bytes) with lowercase names.
            if k == self._HEADER_BYTES:
                inbound = v.decode("latin-1") if isinstance(v, bytes) else v
                break
        request_id = (inbound or uuid.uuid4().hex).strip() or uuid.uuid4().hex

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                # Replace any X-Request-Id we inherited so downstream
                # handlers can't shadow ours.
                response_headers = [
                    (k, v)
                    for k, v in response_headers
                    if k != self._HEADER_BYTES
                ]
                response_headers.append(
                    (self._HEADER_BYTES, request_id.encode("latin-1"))
                )
                message = dict(message)
                message["headers"] = response_headers
            await send(message)

        # Stash the id on the scope so downstream handlers can read it; the
        # logging integration uses ``request.state.request_id`` for HTTP.
        new_scope = dict(scope)
        new_scope["state"] = dict(scope.get("state") or {})
        new_scope["state"]["request_id"] = request_id
        await self.app(new_scope, receive, send_wrapper)


def _validate_secrets() -> None:
    """Fail-fast check on application construction (todo 40).

    Calls :func:`config.secret_key` so the refusal surfaces BEFORE any
    route is wired up — the process exits, compose restarts it, and the
    operator sees the message in ``docker compose logs api``.  Catching
    the error at request time would let the API answer the first few
    requests with a 500 (a worse failure mode).
    """
    try:
        config.secret_key()
    except RuntimeError as e:
        raise SystemExit(f"[pseint-api] refusing to boot: {e}") from None


def create_app(limiter=None) -> FastAPI:
    _validate_secrets()

    app = FastAPI(title="pseint-api")

    # Structured JSON logs (todo 40) — installed BEFORE middleware so the
    # format is applied to the very first message.
    configure_json_logging()

    # Request-ID propagation (todo 40) — must run BEFORE the JSON formatter
    # consumes ``request.state.request_id`` from the logger.  Logging
    # integration here is best-effort; the JSON formatter picks up the id
    # when ``extra={"request_id": ...}`` is passed to a log call.
    app.add_middleware(RequestIdMiddleware)

    # CORS (todo 40).  Empty allowlist → no Access-Control-Allow-Origin is
    # emitted → browser cross-origin calls are rejected (preflight returns
    # the request origin without the header so the browser blocks it).
    allow_origins = config.cors_allow_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(allow_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
        max_age=600,
    )

    # Todo 20: rate limiting wraps all routes; tests inject an in-memory limiter.
    app.add_middleware(RateLimitMiddleware, limiter=limiter)

    # --- Liveness / readiness probes (todo 36) -----------------------------
    # Both endpoints are skipped by the rate limiter (prefixes ``/health`` and
    # ``/ready`` are in ``SKIP_PREFIXES``).  They never raise — readiness
    # returns a non-2xx status that compose/Caddy can use to take the API
    # out of rotation until the DBs recover.

    @app.middleware("http")
    async def _attach_request_id(request: Request, call_next) -> Response:
        """Expose the request id on ``request.state`` for route handlers."""
        rid = _extract_request_id_from_scope(request)
        request.state.request_id = rid
        return await call_next(request)

    @app.get("/healthz", include_in_schema=False)
    def healthz(request: Request) -> dict:
        """Liveness probe — always 200 while the process is alive."""
        return {"status": "ok", "request_id": request.state.request_id}

    @app.get("/readyz", include_in_schema=False)
    def readyz(request: Request) -> Response:
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
            logger.warning(
                "readyz: postgres unreachable",
                extra={"request_id": request.state.request_id},
            )
            deps["postgres"] = "down"
            logger.debug("readyz: postgres error: %s", e)

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
            logger.warning(
                "readyz: redis unreachable",
                extra={"request_id": request.state.request_id},
            )
            deps["redis"] = "down"
            logger.debug("readyz: redis error: %s", e)

        all_ok = all(v == "ok" for v in deps.values())
        payload = {
            "status": "ok" if all_ok else "degraded",
            "deps": deps,
            "request_id": request.state.request_id,
        }
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


def _extract_request_id_from_scope(request: Request) -> str:
    """Pull the request id off the ASGI scope (set by RequestIdMiddleware).

    Starlette's ``Request.scope`` is the raw ASGI scope; we stash the id
    there so any code path can read it without re-parsing headers.
    """
    state = request.scope.get("state") if hasattr(request, "scope") else None
    if isinstance(state, dict) and "request_id" in state:
        return state["request_id"]
    return uuid.uuid4().hex
