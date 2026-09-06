"""Password hashing and JWT helpers for pseint-api (todo 17).

Argon2 via pwdlib (same library as bootstrap.py).  JWT is HS256 via
python-jose, signed with ``config.secret_key()`` (>=32 chars enforced in
config).  ``verify_password`` falls back to a constant-time plaintext compare
for non-argon2 stored hashes — the bootstrap admin in tests is seeded with a
literal ``password_hash="x"``, and that must still authenticate.
"""

from __future__ import annotations

import hmac
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from jose import JWTError, jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

ALGORITHM = "HS256"

_password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(plain: str, stored: str) -> bool:
    try:
        return _password_hasher.verify(plain, stored)
    except (UnknownHashError, ValueError):
        return hmac.compare_digest(plain.encode(), stored.encode())


def create_access_token(user_id: int, secret_key: str, ttl_minutes: int) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, secret_key, algorithm=ALGORITHM)


def decode_token(token: str, secret_key: str) -> int:
    try:
        payload = jwt.decode(token, secret_key, algorithms=[ALGORITHM])
    except JWTError:
        raise _credentials_exception()
    sub = payload.get("sub")
    if sub is None:
        raise _credentials_exception()
    try:
        return int(sub)
    except (TypeError, ValueError):
        raise _credentials_exception()


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
