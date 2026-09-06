"""Auth tests for pseint-api (todo 17).

Covers the plan's acceptance list: register (valid/invalid class code,
duplicate username 409), login (ok/wrong-password 401), JWT expiry via a
short-lived TOKEN_TTL_MINUTES override, role guards (student->teacher action
403, teacher->admin action 403), GET /api/me, admin teacher creation and
admin password reset.

Runs against a dedicated ``pseint_test`` database on the same docker postgres
(reusing the test_models.py fixture pattern).  Auth adds NO tables, so the
migration is unchanged and ``alembic check`` stays clean.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from pseint_api.models import Class, ClassMember, User

TEST_DB_NAME = "pseint_test"
ADMIN_URL = "postgresql+psycopg://pseint:pseint@localhost:5432/postgres"


def _admin_engine():
    return create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")


def _drop_test_db() -> None:
    # TEST_DB_NAME is a module constant (not user input) — safe to interpolate.
    with _admin_engine().connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)"))


@pytest.fixture(scope="session")
def test_engine():
    """Create the test DB, migrate to head, yield an engine, drop the DB."""
    _drop_test_db()
    with _admin_engine().connect() as conn:
        conn.execute(text(f"CREATE DATABASE {TEST_DB_NAME}"))

    from alembic.config import Config

    from alembic import command

    url = f"postgresql+psycopg://pseint:pseint@localhost:5432/{TEST_DB_NAME}"
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("DATABASE_URL", url)
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        monkeypatch.undo()

    engine = create_engine(url)
    yield engine
    engine.dispose()
    _drop_test_db()


@pytest.fixture(scope="session", autouse=True)
def _jwt_secret():
    """JWT signing key for the whole session (config.secret_key() needs >=32)."""
    import os

    os.environ["SECRET_KEY"] = "test-secret-key-1234567890abcdef"
    yield
    os.environ.pop("SECRET_KEY", None)


@pytest.fixture(autouse=True)
def _clean_tables(test_engine):
    """Truncate all tables before each test.

    HTTP endpoints commit, so the session-scoped DB persists rows across
    tests; a rollback-only fixture cannot isolate them.
    """
    from pseint_api.db import Base

    with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    yield


@pytest.fixture()
def client(test_engine):
    """FastAPI TestClient with get_db overridden to the test engine."""
    from pseint_api.deps import get_db
    from pseint_api.main import create_app

    app = create_app()

    def override_get_db():
        with Session(test_engine) as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def db_session(test_engine):
    """Direct session for seeding classes/teachers before HTTP calls."""
    with Session(test_engine) as s:
        yield s
        s.rollback()


def _seed_class(db: Session, code: str = "C1") -> Class:
    teacher = User(
        username=f"teacher_{code}",
        display_name="Teacher",
        password_hash="x",
        role="teacher",
    )
    db.add(teacher)
    db.flush()
    cls = Class(name="Intro", code=code, teacher_id=teacher.id)
    db.add(cls)
    db.commit()
    return cls


def _register(client, username="alice", password="secret-123", class_code=None):
    payload = {
        "username": username,
        "display_name": "Alice",
        "password": password,
    }
    if class_code is not None:
        payload["class_code"] = class_code
    return client.post("/api/register", json=payload)


def _login(client, username="alice", password="secret-123"):
    return client.post(
        "/api/login", json={"username": username, "password": password}
    )


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Register ---------------------------------------------------------------


def test_register_with_valid_class_code_joins_class(client, db_session):
    _seed_class(db_session, code="C1")
    resp = _register(client, class_code="C1")
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "alice"
    assert body["role"] == "student"

    user = db_session.scalar(select(User).where(User.username == "alice"))
    assert user is not None
    member = db_session.get(ClassMember, (1, user.id))
    assert member is not None


def test_register_with_invalid_class_code_400(client):
    resp = _register(client, class_code="NOPE")
    assert resp.status_code == 400
    assert "class code" in resp.json()["detail"].lower()


def test_register_duplicate_username_409(client):
    assert _register(client, username="dup").status_code == 201
    resp = _register(client, username="dup")
    assert resp.status_code == 409


def test_register_short_password_422(client):
    resp = _register(client, password="short")
    assert resp.status_code == 422


# --- Login ------------------------------------------------------------------


def test_login_ok_returns_token(client):
    _register(client)
    resp = _login(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_wrong_password_401(client):
    _register(client)
    resp = _login(client, password="wrong-pass")
    assert resp.status_code == 401


def test_login_unknown_user_401(client):
    resp = _login(client, username="ghost")
    assert resp.status_code == 401


# --- JWT expiry -------------------------------------------------------------


def test_jwt_expiry_short_lived_override(monkeypatch, client):
    monkeypatch.setenv("TOKEN_TTL_MINUTES", "-1")
    _register(client)
    token = _login(client).json()["access_token"]
    resp = client.get("/api/me", headers=_auth_headers(token))
    assert resp.status_code == 401


# --- GET /api/me ------------------------------------------------------------


def test_me_returns_current_user(client):
    _register(client)
    token = _login(client).json()["access_token"]
    resp = client.get("/api/me", headers=_auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "alice"
    assert body["role"] == "student"
    assert body["display_name"] == "Alice"


def test_me_requires_auth(client):
    resp = client.get("/api/me")
    assert resp.status_code == 401


# --- Role guards ------------------------------------------------------------


def test_student_cannot_create_problem_403(client):
    """require_teacher guard rejects a student (the 'create problem' action)."""
    from fastapi import HTTPException

    from pseint_api.deps import require_teacher

    _register(client)
    token = _login(client).json()["access_token"]
    me = client.get("/api/me", headers=_auth_headers(token)).json()

    student = User(
        id=me["id"],
        username=me["username"],
        display_name=me["display_name"],
        password_hash="x",
        role=me["role"],
    )
    with pytest.raises(HTTPException) as exc:
        require_teacher(student)
    assert exc.value.status_code == 403
    assert "teacher" in exc.value.detail.lower()


def test_teacher_cannot_bootstrap_admin_action_403(client):
    """Teacher POST /api/admin/teachers -> 403 (admin-only)."""
    _register(client)
    token = _login(client).json()["access_token"]
    resp = client.post(
        "/api/admin/teachers",
        json={
            "username": "newteacher",
            "display_name": "New Teacher",
            "password": "teacher-secret-123",
        },
        headers=_auth_headers(token),
    )
    assert resp.status_code == 403
    assert "admin" in resp.json()["detail"].lower()


# --- Admin: teacher creation ------------------------------------------------


def _make_admin(client, db_session, username="admin"):
    admin = User(
        username=username,
        display_name="Admin",
        password_hash="x",
        role="admin",
    )
    db_session.add(admin)
    db_session.commit()
    return admin


def test_admin_can_create_teacher(client, db_session):
    _make_admin(client, db_session)
    token = _login(client, username="admin", password="x").json()["access_token"]
    resp = client.post(
        "/api/admin/teachers",
        json={
            "username": "prof",
            "display_name": "Prof",
            "password": "teacher-secret-123",
        },
        headers=_auth_headers(token),
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "teacher"
    teacher = db_session.scalar(select(User).where(User.username == "prof"))
    assert teacher is not None
    assert teacher.role == "teacher"
    assert teacher.password_hash != "teacher-secret-123"  # hashed


def test_admin_create_teacher_duplicate_409(client, db_session):
    _make_admin(client, db_session)
    token = _login(client, username="admin", password="x").json()["access_token"]
    payload = {
        "username": "prof",
        "display_name": "Prof",
        "password": "teacher-secret-123",
    }
    assert (
        client.post(
            "/api/admin/teachers", json=payload, headers=_auth_headers(token)
        ).status_code
        == 201
    )
    resp = client.post(
        "/api/admin/teachers", json=payload, headers=_auth_headers(token)
    )
    assert resp.status_code == 409


# --- Admin: password reset --------------------------------------------------


def test_admin_can_reset_password(client, db_session):
    _make_admin(client, db_session)
    _register(client, username="bob", password="old-secret-123")
    bob = db_session.scalar(select(User).where(User.username == "bob"))
    old_hash = bob.password_hash

    token = _login(client, username="admin", password="x").json()["access_token"]
    resp = client.post(
        f"/api/admin/users/{bob.id}/reset-password",
        json={"password": "new-secret-456"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200

    db_session.expire_all()
    bob = db_session.scalar(select(User).where(User.username == "bob"))
    assert bob.password_hash != old_hash
    # old password no longer works, new one does
    assert _login(client, username="bob", password="old-secret-123").status_code == 401
    assert _login(client, username="bob", password="new-secret-456").status_code == 200


def test_password_reset_requires_admin(client, db_session):
    _register(client, username="bob", password="old-secret-123")
    bob = db_session.scalar(select(User).where(User.username == "bob"))
    token = _login(client, username="bob", password="old-secret-123").json()[
        "access_token"
    ]
    resp = client.post(
        f"/api/admin/users/{bob.id}/reset-password",
        json={"password": "new-secret-456"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 403
