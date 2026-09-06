"""Listing endpoints tests for pseint-api (todo 21).

Covers the plan's acceptance list: problemset list with per-user solved
state + best verdict, pagination envelope + limits (page>=1, 1<=size<=100,
beyond-range page -> empty 200), assignment list (open/closed status, best
result, class scoping), contest list (upcoming/running/ended + registered
flag via participant OR team membership).

Runs against a dedicated ``pseint_test`` database on the same docker
postgres (reusing the test_api/test_ratelimit fixture pattern).  This todo
adds NO tables, so the migration is unchanged and ``alembic check`` stays
clean.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from pseint_api.models import (
    Assignment,
    Class,
    ClassMember,
    Contest,
    ContestParticipant,
    ContestTeam,
    ContestTeamMember,
    Problem,
    Run,
    User,
)
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
    """Direct session for seeding rows before HTTP calls."""
    with Session(test_engine) as s:
        yield s
        s.rollback()


# --- Seeding helpers --------------------------------------------------------


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


def _make_class(
    db: Session, teacher: User, code: str = "C1", name: str = "Intro"
) -> Class:
    cls = Class(name=name, code=code, teacher_id=teacher.id)
    db.add(cls)
    db.commit()
    return cls


def _make_problem(
    db: Session,
    author: User,
    title: str = "Suma",
    complexity: str = "O(1)",
    compare_mode: str = "exact",
) -> Problem:
    problem = Problem(
        title=title,
        statement="Sumar dos números",
        expected_complexity=complexity,
        compare_mode=compare_mode,
        author_id=author.id,
    )
    db.add(problem)
    db.commit()
    return problem


def _make_assignment(
    db: Session, cls: Class, problem: Problem, deadline: datetime
) -> Assignment:
    assignment = Assignment(
        class_id=cls.id, problem_id=problem.id, deadline=deadline
    )
    db.add(assignment)
    db.commit()
    return assignment


def _make_contest(
    db: Session,
    teacher: User,
    title: str = "Concurso",
    scoring_mode: str = "cf",
    teams_enabled: bool = False,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> Contest:
    now = datetime.now(UTC)
    contest = Contest(
        title=title,
        start_at=start_at or now - timedelta(hours=1),
        end_at=end_at or now + timedelta(hours=1),
        scoring_mode=scoring_mode,
        teams_enabled=teams_enabled,
        created_by=teacher.id,
    )
    db.add(contest)
    db.commit()
    return contest


def _seed_run(
    db: Session,
    user: User,
    problem: Problem,
    verdict: str,
    kind: str = "practice",
    assignment_id: int | None = None,
    steps: int = 10,
) -> Run:
    run = Run(
        user_id=user.id,
        problem_id=problem.id,
        kind=kind,
        status="done",
        summary_verdict=verdict,
        steps=steps,
        wall_ms=5,
        source=VALID_SOURCE,
        assignment_id=assignment_id,
    )
    db.add(run)
    db.commit()
    return run


def _login(client: TestClient, username: str, password: str = "x") -> str:
    resp = client.post(
        "/api/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Problems: per-user solved state + best verdict -------------------------


def test_problems_listing_solved_flags(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    p1 = _make_problem(db_session, teacher, title="P1")
    p2 = _make_problem(db_session, teacher, title="P2")
    p3 = _make_problem(db_session, teacher, title="P3")
    alice = _make_user(db_session, "alice")
    _seed_run(db_session, alice, p1, verdict="AC")
    token = _login(client, "alice")
    resp = client.get("/api/problems", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    by_id = {p["id"]: p for p in body["items"]}
    assert by_id[p1.id]["is_solved"] is True
    assert by_id[p1.id]["best_verdict"] == "AC"
    assert by_id[p2.id]["is_solved"] is False
    assert by_id[p2.id]["best_verdict"] is None
    assert by_id[p3.id]["is_solved"] is False
    assert by_id[p3.id]["best_verdict"] is None


def test_problems_listing_best_verdict_ranking(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    p_wa = _make_problem(db_session, teacher, title="WA")
    p_ce = _make_problem(db_session, teacher, title="CE")
    p_none = _make_problem(db_session, teacher, title="None")
    alice = _make_user(db_session, "alice")
    _seed_run(db_session, alice, p_wa, verdict="TLE")
    _seed_run(db_session, alice, p_wa, verdict="WA")
    _seed_run(db_session, alice, p_ce, verdict="CE")
    token = _login(client, "alice")
    resp = client.get("/api/problems", headers=_auth(token))
    body = resp.json()
    by_id = {p["id"]: p for p in body["items"]}
    assert by_id[p_wa.id]["best_verdict"] == "WA"  # WA ranks above TLE
    assert by_id[p_wa.id]["is_solved"] is False
    assert by_id[p_ce.id]["best_verdict"] == "CE"
    assert by_id[p_none.id]["best_verdict"] is None


def test_problems_listing_requires_auth(client):
    resp = client.get("/api/problems")
    assert resp.status_code == 401


# --- Pagination -------------------------------------------------------------


def test_problems_pagination_25(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    for i in range(25):
        _make_problem(db_session, teacher, title=f"P{i}")
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    r1 = client.get("/api/problems?page=1&size=10", headers=_auth(token))
    assert r1.status_code == 200
    b1 = r1.json()
    assert len(b1["items"]) == 10
    assert b1["page"] == 1
    assert b1["size"] == 10
    assert b1["total"] == 25
    r2 = client.get("/api/problems?page=2&size=10", headers=_auth(token))
    b2 = r2.json()
    assert len(b2["items"]) == 10
    r3 = client.get("/api/problems?page=3&size=10", headers=_auth(token))
    b3 = r3.json()
    assert len(b3["items"]) == 5
    ids = {p["id"] for p in b1["items"] + b2["items"] + b3["items"]}
    assert len(ids) == 25  # pages are disjoint and cover everything


def test_problems_page_beyond_range_empty_200(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    for i in range(25):
        _make_problem(db_session, teacher, title=f"P{i}")
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.get("/api/problems?page=10&size=10", headers=_auth(token))
    assert resp.status_code == 200  # NOT 500 (plan QA scenario)
    assert resp.json() == {"items": [], "page": 10, "size": 10, "total": 25}


def test_problems_pagination_validation_422(client, db_session):
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    for qs in ("size=0", "size=200", "page=0"):
        resp = client.get(f"/api/problems?{qs}", headers=_auth(token))
        assert resp.status_code == 422, qs


# --- Assignments: status + best result + class scoping ----------------------


def test_assignments_listing_status_scope_and_best(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    cls1 = _make_class(db_session, teacher, code="C1")
    cls2 = _make_class(db_session, teacher, code="C2")
    p1 = _make_problem(db_session, teacher, title="P1")
    p2 = _make_problem(db_session, teacher, title="P2")
    p3 = _make_problem(db_session, teacher, title="P3")
    now = datetime.now(UTC)
    a_open = _make_assignment(
        db_session, cls1, p1, deadline=now + timedelta(hours=1)
    )
    a_closed = _make_assignment(
        db_session, cls1, p2, deadline=now - timedelta(hours=1)
    )
    a_other = _make_assignment(
        db_session, cls2, p3, deadline=now + timedelta(hours=1)
    )
    alice = _make_user(db_session, "alice")
    db_session.add(ClassMember(class_id=cls1.id, user_id=alice.id))
    db_session.commit()
    # Best on a_open: WA (10 steps), then AC (20), then AC (15) -> AC/15.
    _seed_run(db_session, alice, p1, verdict="WA", kind="assignment",
              assignment_id=a_open.id, steps=10)
    _seed_run(db_session, alice, p1, verdict="AC", kind="assignment",
              assignment_id=a_open.id, steps=20)
    _seed_run(db_session, alice, p1, verdict="AC", kind="assignment",
              assignment_id=a_open.id, steps=15)
    token = _login(client, "alice")
    resp = client.get("/api/assignments", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2  # a_other's class is not alice's
    by_id = {a["id"]: a for a in body["items"]}
    assert by_id[a_open.id]["status"] == "open"
    assert by_id[a_open.id]["best_verdict"] == "AC"
    assert by_id[a_open.id]["best_steps"] == 15
    assert by_id[a_closed.id]["status"] == "closed"
    assert by_id[a_closed.id]["best_verdict"] is None
    assert by_id[a_closed.id]["best_steps"] is None
    assert a_other.id not in by_id


# --- Contests: status + registered flag -------------------------------------


def test_contests_listing_status_and_registration(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    now = datetime.now(UTC)
    c_upcoming = _make_contest(
        db_session, teacher, title="Upcoming",
        start_at=now + timedelta(hours=2), end_at=now + timedelta(hours=3),
    )
    c_running = _make_contest(
        db_session, teacher, title="Running",
        start_at=now - timedelta(hours=1), end_at=now + timedelta(hours=1),
    )
    c_ended = _make_contest(
        db_session, teacher, title="Ended",
        start_at=now - timedelta(hours=3), end_at=now - timedelta(hours=2),
    )
    alice = _make_user(db_session, "alice")
    db_session.add(ContestParticipant(contest_id=c_running.id, user_id=alice.id))
    db_session.commit()
    token = _login(client, "alice")
    resp = client.get("/api/contests", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    by_id = {c["id"]: c for c in body["items"]}
    assert by_id[c_upcoming.id]["status"] == "upcoming"
    assert by_id[c_running.id]["status"] == "running"
    assert by_id[c_ended.id]["status"] == "ended"
    assert by_id[c_running.id]["is_registered"] is True
    assert by_id[c_upcoming.id]["is_registered"] is False
    assert by_id[c_ended.id]["is_registered"] is False


def test_contests_listing_team_registration(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    now = datetime.now(UTC)
    contest = _make_contest(
        db_session, teacher, title="Team", teams_enabled=True,
        start_at=now + timedelta(hours=2), end_at=now + timedelta(hours=3),
    )
    team = ContestTeam(contest_id=contest.id, name="Equipo A")
    db_session.add(team)
    db_session.commit()
    alice = _make_user(db_session, "alice")
    db_session.add(ContestTeamMember(team_id=team.id, user_id=alice.id))
    db_session.commit()
    token = _login(client, "alice")
    resp = client.get("/api/contests", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["is_registered"] is True
