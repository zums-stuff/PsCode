"""Redis-backed rate limiting middleware for pseint-api (todo 20).

Hand-rolled per plan (M13): no slowapi.  Fixed 1-minute windows, four
counter families:

- ``ip:{client_ip}`` — 60 req/min, every non-skipped request (auth or not)
- ``user:{user_id}`` / ``anon:{client_ip}`` — 60 req/min per identity
- ``runs:{user_id}`` — 10 POST /api/runs per minute
- ``subs:{user_id}`` — 30 submissions (POST /api/runs or /api/validate)
  per minute; the runs limit is the tighter one on runs endpoints

Healthchecks and static assets are never rate-limited (plan todo 20).  The
Redis limiter fails OPEN when Redis is unreachable: rate limiting is a
guardrail, not an availability boundary — the API keeps serving requests
(degraded) instead of 500ing everything.
"""

from __future__ import annotations

import logging
import math
import os
import time

import redis
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from . import auth, config

logger = logging.getLogger(__name__)

IP_LIMIT = 60
USER_LIMIT = 60
RUNS_LIMIT = 10
SUBS_LIMIT = 30
WINDOW_SECONDS = 60

# Paths that must never be rate-limited (plan todo 20): healthchecks,
# readiness probes, static assets, framework internals and docs.
SKIP_PREFIXES = (
    "/health",
    "/ready",
    "/static",
    "/_",
    "/docs",
    "/openapi.json",
    "/redoc",
)


class RateLimiter:
    """Redis-backed fixed-window counter (INCR + EXPIRE, TTL for retry-after)."""

    def __init__(self, url: str | None = None) -> None:
        self._redis = redis.Redis.from_url(
            url or os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            socket_connect_timeout=1,
            socket_timeout=1,
        )

    def check(
        self, key: str, limit: int, window_seconds: int = WINDOW_SECONDS
    ) -> tuple[bool, int]:
        """Increment ``key``; return (allowed, retry_after_seconds).

        INCR + TTL in one pipeline; the first hit (count == 1) sets EXPIRE.
        When the count exceeds ``limit``, retry_after is the key's remaining
        TTL (>= 1).  Fails open (allowed) if Redis is unreachable.
        """
        try:
            pipe = self._redis.pipeline()
            pipe.incr(key)
            pipe.ttl(key)
            count, ttl = pipe.execute()
            if count == 1:
                self._redis.expire(key, window_seconds)
                ttl = window_seconds
            if ttl < 0:  # key without TTL (race) — assume a fresh window
                ttl = window_seconds
            retry_after = max(1, ttl)
            return count <= limit, retry_after
        except redis.RedisError:
            logger.warning("Redis unavailable; rate limit check skipped for %s", key)
            return True, 1


class InMemoryRateLimiter:
    """Dict-backed limiter with the same interface — used by tests."""

    def __init__(self) -> None:
        self._counters: dict[str, tuple[int, float]] = {}

    def check(
        self, key: str, limit: int, window_seconds: int = WINDOW_SECONDS
    ) -> tuple[bool, int]:
        now = time.monotonic()
        count, expire_at = self._counters.get(key, (0, 0.0))
        if now >= expire_at:
            count = 0
            expire_at = now + window_seconds
        count += 1
        self._counters[key] = (count, expire_at)
        retry_after = max(1, math.ceil(expire_at - now))
        return count <= limit, retry_after


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP + per-user + endpoint-specific rate limits (M13 / todo 20)."""

    def __init__(self, app, limiter=None) -> None:
        super().__init__(app)
        self.limiter = limiter or RateLimiter()

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if path.startswith(SKIP_PREFIXES):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        # Per-IP first: every non-skipped request counts, auth or not.
        allowed, retry_after = self.limiter.check(f"ip:{client_ip}", IP_LIMIT)
        if not allowed:
            return self._rate_limited("per-ip", IP_LIMIT, retry_after)

        # Identity: JWT user when the header decodes, else anonymous by IP.
        user_id = self._extract_user_id(request)
        if user_id is not None:
            identity_key = f"user:{user_id}"
        else:
            identity_key = f"anon:{client_ip}"

        allowed, retry_after = self.limiter.check(identity_key, USER_LIMIT)
        if not allowed:
            return self._rate_limited("per-user", USER_LIMIT, retry_after)

        # Endpoint-specific per-user caps (anonymous requests 401 at the
        # route anyway; the IP/anon checks already cover them).
        if user_id is not None:
            # Rejudge is an administrative action (teacher/admin), not a
            # student submission — it stays under the global per-user/IP
            # caps but skips the runs/submission-specific buckets so a
            # teacher can re-grade a whole class without hitting the limit.
            is_rejudge = (
                path.startswith("/api/runs/")
                and path.endswith("/rejudge")
            )
            if path == "/api/runs" or is_rejudge:
                # Per-user submissions quota applies to fresh submissions
                # only (rejudges don't count — they're an admin action).
                if not is_rejudge:
                    allowed, retry_after = self.limiter.check(
                        f"subs:{user_id}", SUBS_LIMIT
                    )
                    if not allowed:
                        return self._rate_limited(
                            "submissions", SUBS_LIMIT, retry_after
                        )
                if not is_rejudge:
                    allowed, retry_after = self.limiter.check(
                        f"runs:{user_id}", RUNS_LIMIT
                    )
                    if not allowed:
                        return self._rate_limited(
                            "runs", RUNS_LIMIT, retry_after
                        )
            elif path == "/api/validate":
                allowed, retry_after = self.limiter.check(
                    f"subs:{user_id}", SUBS_LIMIT
                )
                if not allowed:
                    return self._rate_limited("submissions", SUBS_LIMIT, retry_after)

        return await call_next(request)

    def _extract_user_id(self, request: Request) -> int | None:
        """Peek at the Bearer token without forcing FastAPI to resolve it."""
        header = request.headers.get("Authorization")
        if not header or not header.startswith("Bearer "):
            return None
        token = header[len("Bearer "):].strip()
        try:
            return auth.decode_token(token, config.secret_key())
        except Exception:
            return None

    def _rate_limited(self, rule: str, limit: int, retry_after: int) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={
                "detail": f"Rate limit exceeded: {rule}",
                "limit": limit,
                "window_seconds": WINDOW_SECONDS,
                "retry_after": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )
