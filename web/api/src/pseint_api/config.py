"""Environment-driven configuration for pseint-api (todo 16).

All values come from environment variables with sensible local defaults.
Secrets (ADMIN_PASSWORD, DATABASE_URL credentials) are never committed — they
are supplied via env at deploy time.
"""

from __future__ import annotations

import os

# Default local Postgres (matches infra/docker-compose.yml postgres service).
DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://pseint:pseint@localhost:5432/pseint"
)

# SECRET_KEY < 32 chars refuses boot (plan anti-pattern). Not used by todo 16
# itself, but declared here so the API package owns the invariant from day one.
MIN_SECRET_KEY_LENGTH = 32

# JWT access-token lifetime in minutes (M13: 24h default).  Tests override this
# with a short/negative value to exercise expiry.
DEFAULT_TOKEN_TTL_MINUTES = 24 * 60


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def admin_username() -> str | None:
    value = os.environ.get("ADMIN_USERNAME")
    return value.strip() if value and value.strip() else None


def admin_password() -> str | None:
    value = os.environ.get("ADMIN_PASSWORD")
    return value if value else None


def secret_key() -> str:
    value = os.environ.get("SECRET_KEY", "")
    if len(value) < MIN_SECRET_KEY_LENGTH:
        raise RuntimeError(
            f"SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} chars"
        )
    return value


def token_ttl_minutes() -> int:
    raw = os.environ.get("TOKEN_TTL_MINUTES", str(DEFAULT_TOKEN_TTL_MINUTES))
    return int(raw)
