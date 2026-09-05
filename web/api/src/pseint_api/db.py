"""SQLAlchemy engine and session factory for pseint-api (todo 16)."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def make_engine(url: str | None = None):
    """Create a SQLAlchemy engine for ``url`` (defaults to env DATABASE_URL)."""
    return create_engine(url or config.database_url(), pool_pre_ping=True)


def make_session_factory(engine):
    """Create a sessionmaker bound to ``engine``."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# Default engine + session factory bound to the env DATABASE_URL.
engine = make_engine()
SessionLocal = make_session_factory(engine)
