"""Rate limiting tests for pseint-api (todo 20).

Covers the plan's acceptance list: burst of 11 practice runs in a minute →
10 ok + 1×429 with Retry-After; per-IP cap (60 req/min); healthchecks and
static assets never rate-limited; normal flow unaffected under the
threshold; the submissions counter shared between /api/runs and
/api/validate with the runs limit taking precedence (runs allowed but
submissions exceeded → still 429).

Uses InMemoryRateLimiter injected via ``create_app(limiter=...)`` — no Redis
required.  Runs against a dedicated ``pseint_test`` database on the same
docker postgres (reusing the test_ws/test_api fixture pattern).  This todo
adds NO tables, so the migration is unchanged and ``alembic check`` stays
clean.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from pseint_api.models import Problem, User
from pseint_api.ratelimit import InMemoryRateLimiter

TEST_DB_NAME = "pseint_test"
ADMIN_URL = "postgresql+psycopg://pseint:pseint@localhost:5432/postgres"

VALID_SOURCE = "Proceso P\n  Escribir 1\nFinProceso\n"


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
    """FastAPI TestClient with get_db overridden and an in-memory limiter."""
    from pseint_api.deps import get_db
    from pseint_api.main import create_app

    app = create_app(limiter=InMemoryRateLimiter())

    def override_get_db():
        with Session(test_engine) as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def db_session(test_engine):
    """Direct session for seeding users/problems before HTTP calls."""
    with Session(test_engine) as s:
        yield s
        s.rollback()


# --- Seed helpers -----------------------------------------------------------


def _make_user(db: Session, username: str = "alice", role: str = "student") -> User:
    user = User(
        username=username,
        display_name=username.title(),
        password_hash="x",
        role=role,
    )
    db.add(user)
    db.commit()
    return user


def _make_problem(db: Session, author_id: int) -> Problem:
    problem = Problem(
        title="Suma",
        statement="Sumar dos numeros",
        expected_complexity="O(1)",
        compare_mode="exact",
        author_id=author_id,
    )
    db.add(problem)
    db.commit()
    return problem


def _login(client: TestClient, username: str, password: str = "x") -> str:
    resp = client.post(
        "/api/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _submit_run(client: TestClient, token: str, problem_id: int):
    return client.post(
        "/api/runs",
        json={"problem_id": problem_id, "source": VALID_SOURCE, "mode": "practice"},
        headers=_auth(token),
    )


def _assert_429(resp, rule: str, limit: int) -> None:
    assert resp.status_code == 429
    assert resp.headers["Retry-After"] is not None
    retry_after = int(resp.headers["Retry-After"])
    assert retry_after >= 1
    body = resp.json()
    assert body["detail"] == f"Rate limit exceeded: {rule}"
    assert body["limit"] == limit
    assert body["window_seconds"] == 60
    assert body["retry_after"] == retry_after


# --- Acceptance: burst of 11 practice runs ----------------------------------


def test_burst_of_11_practice_runs_10_ok_1_429(client, db_session):
    _make_user(db_session, "alice")
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher.id)
    token = _login(client, "alice")

    for _ in range(10):
        resp = _submit_run(client, token, problem.id)
        assert resp.status_code == 202

    resp = _submit_run(client, token, problem.id)
    _assert_429(resp, "runs", 10)


# --- Acceptance: per-IP cap -------------------------------------------------


def test_per_ip_60_ok_61st_429(client):
    # /api/me 401s without auth, but the middleware counts every request
    # against the IP budget regardless of the route's auth outcome.
    for _ in range(60):
        resp = client.get("/api/me")
        assert resp.status_code == 401

    resp = client.get("/api/me")
    _assert_429(resp, "per-ip", 60)


# --- Plan-forbidden: healthchecks and static assets are never limited -------


def test_healthchecks_skipped(client):
    # The API has no /health route (healthz/readyz are Caddy-level, todo 40),
    # so these 404 — the point is they are NOT rate-limited and do NOT
    # consume the IP budget.
    for _ in range(100):
        resp = client.get("/health")
        assert resp.status_code != 429

    # 60 more real requests still fit: the 100 health hits were skipped.
    for _ in range(60):
        resp = client.get("/api/me")
        assert resp.status_code == 401
    resp = client.get("/api/me")
    _assert_429(resp, "per-ip", 60)


def test_static_assets_skipped(client):
    for _ in range(100):
        resp = client.get("/static/x.css")
        assert resp.status_code != 429

    for _ in range(60):
        resp = client.get("/api/me")
        assert resp.status_code == 401
    resp = client.get("/api/me")
    _assert_429(resp, "per-ip", 60)


# --- QA: normal flow unaffected under the threshold -------------------------


def test_normal_flow_5_runs_all_202(client, db_session):
    _make_user(db_session, "alice")
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher.id)
    token = _login(client, "alice")

    for _ in range(5):
        resp = _submit_run(client, token, problem.id)
        assert resp.status_code == 202


# --- Submissions counter shared with /api/validate --------------------------


def test_validate_shares_submissions_counter(client, db_session):
    _make_user(db_session, "alice")
    token = _login(client, "alice")

    for _ in range(30):
        resp = client.post(
            "/api/validate", json={"source": VALID_SOURCE}, headers=_auth(token)
        )
        assert resp.status_code == 200

    resp = client.post(
        "/api/validate", json={"source": VALID_SOURCE}, headers=_auth(token)
    )
    _assert_429(resp, "submissions", 30)


def test_runs_limit_takes_precedence_over_submissions(client, db_session):
    """Runs allowed (<=10) but submissions exceeded (>30) → still 429."""
    _make_user(db_session, "alice")
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher.id)
    token = _login(client, "alice")

    # 25 validates → subs counter at 25.
    for _ in range(25):
        resp = client.post(
            "/api/validate", json={"source": VALID_SOURCE}, headers=_auth(token)
        )
        assert resp.status_code == 200

    # 5 runs → subs 26..30, runs 1..5 — all under both limits.
    for _ in range(5):
        resp = _submit_run(client, token, problem.id)
        assert resp.status_code == 202

    # 6th run: subs would hit 31 (>30) while runs is only 6 (<=10) → 429.
    resp = _submit_run(client, token, problem.id)
    _assert_429(resp, "submissions", 30)


# --- InMemoryRateLimiter unit behavior --------------------------------------


def test_inmemory_limiter_window_resets():
    limiter = InMemoryRateLimiter()
    key = "ip:testclient"
    for _ in range(60):
        allowed, _ = limiter.check(key, 60, window_seconds=1)
        assert allowed
    allowed, retry_after = limiter.check(key, 60, window_seconds=1)
    assert not allowed
    assert retry_after >= 1

    time.sleep(1.1)  # window (1s) expires → counter resets
    allowed, _ = limiter.check(key, 60, window_seconds=1)
    assert allowed


def test_inmemory_limiter_keys_are_independent():
    limiter = InMemoryRateLimiter()
    for _ in range(10):
        assert limiter.check("runs:1", 10)[0]
    # A different key is unaffected by the exhausted one.
    assert limiter.check("subs:1", 30)[0]
    assert not limiter.check("runs:1", 10)[0]
