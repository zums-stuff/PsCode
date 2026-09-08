"""Problem visibility (is_public) + contest authoring tests.

Covers:
- Student problem listing excludes is_public=false problems, unless the
  student is in a class that links the problem or has submitted to it.
- PATCH can flip is_public.
- Admin sees both visible and hidden problems.
- Creating a problem with is_public=false and adding it to a contest links
  the new problem to the contest (two-call flow used by the frontend).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from pseint_api.models import (
    Assignment,
    Class,
    ClassMember,
    Problem,
    Run,
    User,
)
from pseint_api.ratelimit import InMemoryRateLimiter

TEST_DB_NAME = "pseint_test_vis"
ADMIN_URL = "postgresql+psycopg://pseint:pseint@localhost:5432/postgres"

VALID_SOURCE = "Proceso P\n  Escribir 1\nFinProceso\n"


def _admin_engine():
    return create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")


def _drop_test_db() -> None:
    with _admin_engine().connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)"))


@pytest.fixture(scope="session")
def test_engine():
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
    import os

    os.environ["SECRET_KEY"] = "test-secret-key-1234567890abcdef"
    yield
    os.environ.pop("SECRET_KEY", None)


@pytest.fixture(autouse=True)
def _clean_tables(test_engine):
    from pseint_api.db import Base

    with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    yield


@pytest.fixture()
def client(test_engine):
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
    with Session(test_engine) as s:
        yield s
        s.rollback()


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


def _make_class(db: Session, teacher: User) -> Class:
    cls = Class(name="Intro", code="C1", teacher_id=teacher.id)
    db.add(cls)
    db.commit()
    return cls


def _make_problem(
    db: Session,
    author: User,
    title: str = "Suma",
    is_public: bool = False,
) -> Problem:
    problem = Problem(
        title=title,
        statement="Sumar dos números",
        expected_complexity="O(1)",
        compare_mode="exact",
        is_public=is_public,
        author_id=author.id,
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


def test_student_listing_excludes_hidden_unless_class_or_submitted(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    cls = _make_class(db_session, teacher)
    pub = _make_problem(db_session, teacher, title="Pub", is_public=True)
    hidden = _make_problem(db_session, teacher, title="Hidden", is_public=False)
    class_linked = _make_problem(db_session, teacher, title="ClassLink", is_public=False)
    submitted = _make_problem(db_session, teacher, title="Submitted", is_public=False)

    db_session.add(Assignment(class_id=cls.id, problem_id=class_linked.id,
                              deadline=__import__("datetime").datetime.now(
                                  __import__("datetime").UTC)))
    db_session.commit()

    alice = _make_user(db_session, "alice")
    db_session.add(ClassMember(class_id=cls.id, user_id=alice.id))
    db_session.add(Run(
        user_id=alice.id, problem_id=submitted.id, kind="practice",
        status="done", summary_verdict="AC", steps=10, wall_ms=5,
        source=VALID_SOURCE,
    ))
    db_session.commit()

    token = _login(client, "alice")
    resp = client.get("/api/problems", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    titles = {p["title"] for p in body["items"]}
    assert "Pub" in titles
    assert "ClassLink" in titles
    assert "Submitted" in titles
    assert "Hidden" not in titles


def test_patch_can_flip_is_public(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher, title="P", is_public=False)
    token = _login(client, "prof")
    resp = client.patch(
        f"/api/problems/{problem.id}",
        json={"is_public": True},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["is_public"] is True

    # Flip back
    resp = client.patch(
        f"/api/problems/{problem.id}",
        json={"is_public": False},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["is_public"] is False


def test_admin_sees_visible_and_hidden(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    _make_problem(db_session, teacher, title="Visible", is_public=True)
    _make_problem(db_session, teacher, title="Hidden", is_public=False)
    _make_user(db_session, "admin", role="admin")
    token = _login(client, "admin")
    resp = client.get("/api/problems", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    titles = {p["title"] for p in body["items"]}
    assert "Visible" in titles
    assert "Hidden" in titles


def test_create_hidden_problem_and_link_to_contest(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    token = _login(client, "prof")

    # Create a contest first
    resp = client.post(
        "/api/contests",
        json={
            "title": "Concurso",
            "start_at": "2026-01-01T00:00:00Z",
            "end_at": "2026-01-02T00:00:00Z",
            "scoring_mode": "cf",
            "teams_enabled": False,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    contest_id = resp.json()["id"]

    # Create a hidden problem
    resp = client.post(
        "/api/problems",
        json={
            "title": "Nuevo",
            "statement": "Enunciado",
            "expected_complexity": "O(1)",
            "compare_mode": "exact",
            "is_public": False,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201
    problem_id = resp.json()["id"]
    assert resp.json()["is_public"] is False

    # Add test case
    resp = client.post(
        f"/api/problems/{problem_id}/cases",
        json={"input": "1", "expected_output": "1", "seed": 0, "points": 1,
              "order": 0, "is_sample": True},
        headers=_auth(token),
    )
    assert resp.status_code == 201

    # Link to contest
    resp = client.post(
        f"/api/contests/{contest_id}/contest-problems",
        json={"problem_id": problem_id},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["problem_id"] == problem_id
    assert body["contest_id"] == contest_id
    assert body["title"] == "Nuevo"

    # The problem appears in the contest's problem set
    resp = client.get(
        f"/api/contests/{contest_id}/contest-problems", headers=_auth(token)
    )
    assert resp.status_code == 200
    titles = {p["title"] for p in resp.json()}
    assert "Nuevo" in titles
