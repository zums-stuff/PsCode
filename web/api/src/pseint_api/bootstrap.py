"""Bootstrap admin creation (M12).

At first ``alembic upgrade head``, if ADMIN_USERNAME/ADMIN_PASSWORD env vars are
set and no user with that username exists, create an admin user.  Password is
hashed with pwdlib argon2 (the same library todo 17 uses for auth).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .models import User


def _hash_password(password: str) -> str:
    from pwdlib import PasswordHash

    return PasswordHash.recommended().hash(password)


def bootstrap_admin(session: Session) -> User | None:
    """Create the bootstrap admin from env vars if configured and absent.

    Returns the created User, or None if env vars are unset or the user
    already exists (idempotent).
    """
    username = config.admin_username()
    password = config.admin_password()
    if not username or not password:
        return None

    existing = session.scalar(select(User).where(User.username == username))
    if existing is not None:
        return None

    admin = User(
        username=username,
        display_name="Administrator",
        password_hash=_hash_password(password),
        role="admin",
    )
    session.add(admin)
    session.flush()
    return admin
