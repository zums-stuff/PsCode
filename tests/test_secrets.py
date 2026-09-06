"""Tests for SECRET_KEY startup validation (todo 40).

The API must refuse to construct the FastAPI app (i.e. refuse to boot) if
``SECRET_KEY`` is missing, too short, or matches a documented placeholder.
Each scenario is exercised by monkeypatching ``os.environ`` and asserting
that ``create_app()`` raises ``SystemExit`` with a clear message.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_secret_key(monkeypatch):
    """Strip SECRET_KEY from the env so each scenario starts fresh."""
    monkeypatch.delenv("SECRET_KEY", raising=False)
    yield


def test_create_app_refuses_when_secret_key_missing(monkeypatch) -> None:
    """No SECRET_KEY → boot refusal with a clear generator hint."""
    from pseint_api.main import create_app

    with pytest.raises(SystemExit) as excinfo:
        create_app()
    msg = str(excinfo.value)
    assert "SECRET_KEY is not set" in msg
    assert "secrets.token_urlsafe" in msg


def test_create_app_refuses_when_secret_key_too_short(monkeypatch) -> None:
    """Length < 32 chars → boot refusal with a length diagnostic."""
    from pseint_api.main import create_app

    monkeypatch.setenv("SECRET_KEY", "abcdefgh")  # 8 chars
    with pytest.raises(SystemExit) as excinfo:
        create_app()
    msg = str(excinfo.value)
    assert "at least 32 chars" in msg
    assert "got 8" in msg


def test_create_app_refuses_when_secret_key_is_documented_placeholder(
    monkeypatch,
) -> None:
    """The .env.example placeholder must be rejected (exact match)."""
    from pseint_api.main import create_app

    monkeypatch.setenv(
        "SECRET_KEY", "replace-me-with-a-random-string-of-at-least-32-chars"
    )
    with pytest.raises(SystemExit) as excinfo:
        create_app()
    msg = str(excinfo.value).lower()
    assert "placeholder" in msg
    assert "infra/.env.example" in msg


def test_create_app_refuses_when_secret_key_is_changeme(monkeypatch) -> None:
    """The substring ``changeme`` is rejected even when padded to >= 32 chars."""
    from pseint_api.main import create_app

    monkeypatch.setenv("SECRET_KEY", "changeme" + "x" * 30)  # 37 chars
    with pytest.raises(SystemExit) as excinfo:
        create_app()
    msg = str(excinfo.value).lower()
    assert "placeholder" in msg
    assert "changeme" in msg


def test_create_app_refuses_when_secret_key_contains_development_substring(
    monkeypatch,
) -> None:
    """A long-but-trivial value containing 'development' must be rejected."""
    from pseint_api.main import create_app

    monkeypatch.setenv("SECRET_KEY", "pseint-development-environment-x" * 2)
    with pytest.raises(SystemExit) as excinfo:
        create_app()
    msg = str(excinfo.value).lower()
    assert "placeholder" in msg


def test_create_app_refuses_when_secret_key_contains_replace_me(
    monkeypatch,
) -> None:
    """Substring 'replace-me' is rejected (case-insensitive)."""
    from pseint_api.main import create_app

    monkeypatch.setenv(
        "SECRET_KEY", "REPLACE-ME-this-is-the-real-secret-padding-x" * 2
    )
    with pytest.raises(SystemExit) as excinfo:
        create_app()
    msg = str(excinfo.value).lower()
    assert "placeholder" in msg


def test_create_app_accepts_real_secret_key(monkeypatch) -> None:
    """A real random key must boot the app."""
    from pseint_api.main import create_app

    monkeypatch.setenv("SECRET_KEY", "a" * 48)
    app = create_app()
    assert app.title == "pseint-api"


def test_secret_key_function_raises_for_missing() -> None:
    """``config.secret_key()`` raises directly when SECRET_KEY is empty."""
    from pseint_api import config

    with pytest.raises(RuntimeError) as excinfo:
        config.secret_key()
    assert "SECRET_KEY is not set" in str(excinfo.value)


def test_secret_key_function_raises_for_short() -> None:
    from pseint_api import config

    old = os.environ.get("SECRET_KEY")
    os.environ["SECRET_KEY"] = "abc"
    try:
        with pytest.raises(RuntimeError) as excinfo:
            config.secret_key()
        assert "at least 32 chars" in str(excinfo.value)
    finally:
        if old is None:
            os.environ.pop("SECRET_KEY", None)
        else:
            os.environ["SECRET_KEY"] = old


def test_cors_allow_origins_default_is_empty() -> None:
    """Empty CORS env → no origins allowed (same-origin only)."""
    from pseint_api import config

    old = os.environ.get("CORS_ALLOW_ORIGINS")
    os.environ.pop("CORS_ALLOW_ORIGINS", None)
    try:
        assert config.cors_allow_origins() == ()
    finally:
        if old is not None:
            os.environ["CORS_ALLOW_ORIGINS"] = old


def test_cors_allow_origins_parses_csv() -> None:
    """CSV origins are split + trimmed; blanks dropped."""
    from pseint_api import config

    old = os.environ.get("CORS_ALLOW_ORIGINS")
    os.environ["CORS_ALLOW_ORIGINS"] = (
        "https://a.example, https://b.example ,,"
    )
    try:
        assert config.cors_allow_origins() == (
            "https://a.example",
            "https://b.example",
        )
    finally:
        if old is None:
            os.environ.pop("CORS_ALLOW_ORIGINS", None)
        else:
            os.environ["CORS_ALLOW_ORIGINS"] = old
