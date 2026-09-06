"""Environment-driven configuration for pseint-api (todo 16 + 40).

All values come from environment variables with sensible local defaults.
Secrets (ADMIN_PASSWORD, DATABASE_URL credentials) are never committed — they
are supplied via env at deploy time.

SECRET_KEY validation (todo 40 / OPS.md):
    The API refuses to boot if ``SECRET_KEY`` is unset, shorter than
    ``MIN_SECRET_KEY_LENGTH`` chars, or matches the documentation default
    shipped in ``.env.example``.  The same check guards any caller of
    :func:`secret_key`, so auth / JWT verification / rate-limit token peek
    all get the same refusal.  Generate a real key with::

        python -c "import secrets; print(secrets.token_urlsafe(48))"
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

# Placeholder values that must NEVER be used in production.  These appear in
# infra/.env.example as documentation; if the API sees one of these strings
# at startup it refuses to boot (the operator copy-pasted the example).  Kept
# here (not in .env.example) so the check is independent of the example file.
#
# The check is exact-match for the example placeholder (so a real random
# key isn't accidentally blocked) and case-insensitive substring for the
# common trivial values ("changeme", "secret", "dev", "development",
# "replace-me").  An operator who pads a forbidden value with random chars
# still gets caught because the substring is preserved.
_FORBIDDEN_SECRET_KEY_EXACT = frozenset(
    {
        "replace-me-with-a-random-string-of-at-least-32-chars",
    }
)
_FORBIDDEN_SECRET_KEY_SUBSTRINGS = (
    "replace-me",
    "changeme",
    "development",
    "your-secret-key",
    "your-secret",
    "todo-replace",
    "fixme",
    "placeholder",
)

# JWT access-token lifetime in minutes (M13: 24h default).  Tests override this
# with a short/negative value to exercise expiry.
DEFAULT_TOKEN_TTL_MINUTES = 24 * 60

# Default CORS allowlist is empty (same-origin only).  Operators opt into
# cross-origin browser calls by setting ``CORS_ALLOW_ORIGINS`` to a
# comma-separated list of origins (e.g. ``https://judge.example.unam.mx``).
# Whitespace is trimmed; blank entries are dropped.
_DEFAULT_CORS_ALLOW_ORIGINS: tuple[str, ...] = ()


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def admin_username() -> str | None:
    value = os.environ.get("ADMIN_USERNAME")
    return value.strip() if value and value.strip() else None


def admin_password() -> str | None:
    value = os.environ.get("ADMIN_PASSWORD")
    return value if value else None


def secret_key() -> str:
    """Return the validated ``SECRET_KEY``.

    Raises ``RuntimeError`` (never returns an empty / weak / placeholder
    value) if the env var is missing, too short, or matches a documented
    default.  Called from every code path that signs or verifies a JWT
    (auth.py, ratelimit.py, ws.py) so the refusal is universal.
    """
    value = os.environ.get("SECRET_KEY", "")
    if not value:
        raise RuntimeError(
            "SECRET_KEY is not set. Generate one with: "
            "python -c \"import secrets; print(secrets.token_urlsafe(48))\" "
            "and put it in infra/.env (never commit it)."
        )
    if value in _FORBIDDEN_SECRET_KEY_EXACT:
        raise RuntimeError(
            "SECRET_KEY matches the documented placeholder from "
            "infra/.env.example. Replace it with a real random value before "
            "booting; refusing to start so a forgotten copy-paste cannot "
            "ship."
        )
    lowered = value.lower()
    for needle in _FORBIDDEN_SECRET_KEY_SUBSTRINGS:
        if needle in lowered:
            raise RuntimeError(
                f"SECRET_KEY contains the placeholder substring {needle!r} "
                "(case-insensitive). Replace it with a real random value "
                "before booting; refusing to start so a forgotten copy-paste "
                "cannot ship."
            )
    if len(value) < MIN_SECRET_KEY_LENGTH:
        raise RuntimeError(
            f"SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} chars; "
            f"got {len(value)}. Generate one with: "
            "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    return value


def cors_allow_origins() -> tuple[str, ...]:
    """Comma-separated allowlist of browser origins allowed to call the API.

    Empty by default — the API only serves same-origin browser calls.  Set
    ``CORS_ALLOW_ORIGINS=https://app.example,https://other.example`` to
    open specific origins.  Wildcards are NOT supported: each origin must
    be an exact match (``scheme://host[:port]``).
    """
    raw = os.environ.get("CORS_ALLOW_ORIGINS", "")
    if not raw:
        return _DEFAULT_CORS_ALLOW_ORIGINS
    return tuple(o.strip() for o in raw.split(",") if o.strip())


def token_ttl_minutes() -> int:
    raw = os.environ.get("TOKEN_TTL_MINUTES", str(DEFAULT_TOKEN_TTL_MINUTES))
    return int(raw)
