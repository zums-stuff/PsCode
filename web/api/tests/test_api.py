"""REST API v1 integration tests (todo 18).

Covers the plan's acceptance list: CRUD per resource (problems, test-cases,
classes, assignments, contests, teams, forums, similarity), the permission
matrix (401/403/404/409/422/413), submit -> 202 -> queued run row, validate
ok/errors + 64KB cap, assignment deadline 422, practice ungraded, scoreboard
GET shape per mode (cf/ioi), and the contest forum phase lock.

Runs against a dedicated ``pseint_test`` database on the same docker postgres
(reusing the test_models/test_auth fixture pattern).  This todo adds NO
tables, so the migration is unchanged and ``alembic check`` stays clean.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from pseint_api.models import (
    Assignment,
    Class,
    ClassMember,
    Contest,
    ContestParticipant,
    ContestProblem,
    ContestTeam,
    ContestTeamMember,
    ForumPost,
    ForumThread,
    Problem,
    Run,
    SimilarityPair,
    TestCase,
    TestResult,
    User,
)

TEST_DB_NAME = "pseint_test"
ADMIN_URL = "postgresql+psycopg://pseint:pseint@localhost:5432/postgres"

VALID_SOURCE = "Proceso P\n  Escribir 1\nFinProceso\n"
INVALID_SOURCE = "Proceso P\n  Si x Entonces\nFinProceso\n"


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
    statement: str = "Sumar dos números",
    complexity: str = "O(1)",
    compare_mode: str = "exact",
    step_budget: int | None = None,
) -> Problem:
    problem = Problem(
        title=title,
        statement=statement,
        expected_complexity=complexity,
        compare_mode=compare_mode,
        step_budget=step_budget,
        author_id=author.id,
    )
    db.add(problem)
    db.commit()
    return problem


def _make_test_case(
    db: Session,
    problem: Problem,
    input_text: str = "1 2",
    expected: str = "3",
    seed: int = 0,
    points: int = 1,
    order: int = 0,
    is_public: bool = False,
    is_sample: bool = False,
) -> TestCase:
    tc = TestCase(
        problem_id=problem.id,
        input=input_text,
        expected_output=expected,
        seed=seed,
        points=points,
        order=order,
        is_public=is_public,
        is_sample=is_sample,
    )
    db.add(tc)
    db.commit()
    return tc


def _make_assignment(
    db: Session, cls: Class, problem: Problem, deadline: datetime | None = None
) -> Assignment:
    assignment = Assignment(
        class_id=cls.id,
        problem_id=problem.id,
        deadline=deadline or datetime.now(UTC) + timedelta(hours=1),
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
    kind: str = "practice",
    contest: Contest | None = None,
    created_at: datetime | None = None,
    verdict: str | None = None,
    case_verdicts: list[str] | None = None,
    steps: int = 10,
    assignment: Assignment | None = None,
) -> Run:
    run = Run(
        user_id=user.id,
        problem_id=problem.id,
        kind=kind,
        status="done" if verdict is not None else "queued",
        summary_verdict=verdict,
        steps=steps if verdict is not None else None,
        wall_ms=5 if verdict is not None else None,
        source=VALID_SOURCE,
        contest_id=contest.id if contest is not None else None,
        assignment_id=assignment.id if assignment is not None else None,
        created_at=created_at or datetime.now(UTC),
    )
    db.add(run)
    db.flush()
    for i, v in enumerate(case_verdicts or []):
        db.add(
            TestResult(
                run_id=run.id, case_index=i, verdict=v, steps=1, wall_ms=1
            )
        )
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


# --- Validate ---------------------------------------------------------------


def test_validate_ok(client, db_session):
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.post(
        "/api/validate", json={"source": VALID_SOURCE}, headers=_auth(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["errors"] == []


def test_validate_syntax_error_shape(client, db_session):
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.post(
        "/api/validate", json={"source": INVALID_SOURCE}, headers=_auth(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert len(body["errors"]) == 1
    err = body["errors"][0]
    assert err["code"] == "ERR_SYNTAX"
    assert "message" in err
    assert err["line"] >= 1
    assert err["col"] >= 1


def test_validate_requires_auth(client):
    resp = client.post("/api/validate", json={"source": VALID_SOURCE})
    assert resp.status_code == 401


def test_validate_source_too_large_413(client, db_session):
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    big = "Proceso P\n" + "  Escribir 1\n" * 20000 + "FinProceso\n"
    assert len(big.encode()) > 65536
    resp = client.post(
        "/api/validate", json={"source": big}, headers=_auth(token)
    )
    assert resp.status_code == 413


# --- Problems ---------------------------------------------------------------


def _problem_payload(**overrides) -> dict:
    payload = {
        "title": "Suma",
        "statement": "Sumar dos números",
        "expected_complexity": "O(1)",
        "compare_mode": "exact",
        "step_budget": None,
    }
    payload.update(overrides)
    return payload


def test_create_problem_teacher_201(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    token = _login(client, "prof")
    resp = client.post(
        "/api/problems", json=_problem_payload(), headers=_auth(token)
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Suma"
    assert body["statement"] == "Sumar dos números"
    assert body["expected_complexity"] == "O(1)"
    assert body["compare_mode"] == "exact"
    assert body["step_budget"] is None
    assert body["author_id"] == teacher.id


def test_create_problem_admin_201(client, db_session):
    admin = _make_user(db_session, "admin", role="admin")
    token = _login(client, "admin")
    resp = client.post(
        "/api/problems", json=_problem_payload(), headers=_auth(token)
    )
    assert resp.status_code == 201
    assert resp.json()["author_id"] == admin.id


def test_create_problem_student_403(client, db_session):
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.post(
        "/api/problems", json=_problem_payload(), headers=_auth(token)
    )
    assert resp.status_code == 403


def test_create_problem_unauthenticated_401(client):
    resp = client.post("/api/problems", json=_problem_payload())
    assert resp.status_code == 401


def test_create_problem_empty_statement_422(client, db_session):
    _make_user(db_session, "prof", role="teacher")
    token = _login(client, "prof")
    resp = client.post(
        "/api/problems",
        json=_problem_payload(statement=""),
        headers=_auth(token),
    )
    assert resp.status_code == 422


def test_create_problem_invalid_complexity_422(client, db_session):
    _make_user(db_session, "prof", role="teacher")
    token = _login(client, "prof")
    resp = client.post(
        "/api/problems",
        json=_problem_payload(expected_complexity="O(n^2)"),
        headers=_auth(token),
    )
    assert resp.status_code == 422


def test_create_problem_invalid_compare_mode_422(client, db_session):
    _make_user(db_session, "prof", role="teacher")
    token = _login(client, "prof")
    resp = client.post(
        "/api/problems",
        json=_problem_payload(compare_mode="fuzzy"),
        headers=_auth(token),
    )
    assert resp.status_code == 422


def test_create_problem_step_budget_int_ok(client, db_session):
    _make_user(db_session, "prof", role="teacher")
    token = _login(client, "prof")
    resp = client.post(
        "/api/problems",
        json=_problem_payload(step_budget=5000),
        headers=_auth(token),
    )
    assert resp.status_code == 201
    assert resp.json()["step_budget"] == 5000


def test_list_problems(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    _make_problem(db_session, teacher, title="P1")
    _make_problem(db_session, teacher, title="P2")
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.get("/api/problems", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    titles = {p["title"] for p in body["items"]}
    assert titles == {"P1", "P2"}


def test_get_problem(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher, title="P1")
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.get(f"/api/problems/{problem.id}", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == problem.id
    assert body["title"] == "P1"


def test_get_problem_not_found_404(client, db_session):
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.get("/api/problems/9999", headers=_auth(token))
    assert resp.status_code == 404


def test_patch_problem_teacher_200(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher, title="P1")
    token = _login(client, "prof")
    resp = client.patch(
        f"/api/problems/{problem.id}",
        json={"title": "P1 v2", "step_budget": 100},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "P1 v2"
    assert body["step_budget"] == 100
    assert body["expected_complexity"] == "O(1)"  # untouched field preserved


def test_patch_problem_student_403(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher)
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.patch(
        f"/api/problems/{problem.id}",
        json={"title": "hacked"},
        headers=_auth(token),
    )
    assert resp.status_code == 403


def test_patch_problem_not_found_404(client, db_session):
    _make_user(db_session, "prof", role="teacher")
    token = _login(client, "prof")
    resp = client.patch(
        "/api/problems/9999", json={"title": "x"}, headers=_auth(token)
    )
    assert resp.status_code == 404


# --- Test cases -------------------------------------------------------------


def _case_payload(**overrides) -> dict:
    payload = {
        "input": "1 2",
        "expected_output": "3",
        "seed": 0,
        "points": 1,
        "order": 0,
        "is_public": False,
        "is_sample": False,
    }
    payload.update(overrides)
    return payload


def test_create_test_case_teacher_201(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher)
    token = _login(client, "prof")
    resp = client.post(
        f"/api/problems/{problem.id}/cases",
        json=_case_payload(),
        headers=_auth(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["problem_id"] == problem.id
    assert body["expected_output"] == "3"
    assert body["is_sample"] is False
    assert body["seed"] == 0


def test_create_test_case_student_403(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher)
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.post(
        f"/api/problems/{problem.id}/cases",
        json=_case_payload(),
        headers=_auth(token),
    )
    assert resp.status_code == 403


def test_create_second_sample_case_409(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher)
    _make_test_case(db_session, problem, is_sample=True)
    token = _login(client, "prof")
    resp = client.post(
        f"/api/problems/{problem.id}/cases",
        json=_case_payload(is_sample=True),
        headers=_auth(token),
    )
    assert resp.status_code == 409


def test_create_case_unknown_problem_404(client, db_session):
    _make_user(db_session, "prof", role="teacher")
    token = _login(client, "prof")
    resp = client.post(
        "/api/problems/9999/cases",
        json=_case_payload(),
        headers=_auth(token),
    )
    assert resp.status_code == 404


def test_list_cases(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher)
    _make_test_case(db_session, problem, expected="3", order=0)
    _make_test_case(db_session, problem, expected="5", order=1)
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.get(
        f"/api/problems/{problem.id}/cases", headers=_auth(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert [c["expected_output"] for c in body] == ["3", "5"]


def test_patch_case(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher)
    tc = _make_test_case(db_session, problem, expected="3")
    token = _login(client, "prof")
    resp = client.patch(
        f"/api/problems/{problem.id}/cases/{tc.id}",
        json={"expected_output": "4", "points": 2},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["expected_output"] == "4"
    assert body["points"] == 2


def test_patch_case_to_sample_when_another_exists_409(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher)
    _make_test_case(db_session, problem, is_sample=True)
    tc = _make_test_case(db_session, problem, is_sample=False)
    token = _login(client, "prof")
    resp = client.patch(
        f"/api/problems/{problem.id}/cases/{tc.id}",
        json={"is_sample": True},
        headers=_auth(token),
    )
    assert resp.status_code == 409


def test_delete_case(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher)
    tc = _make_test_case(db_session, problem)
    token = _login(client, "prof")
    resp = client.delete(
        f"/api/problems/{problem.id}/cases/{tc.id}", headers=_auth(token)
    )
    assert resp.status_code == 204
    assert (
        db_session.scalar(select(TestCase).where(TestCase.id == tc.id)) is None
    )


def test_delete_case_not_found_404(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher)
    token = _login(client, "prof")
    resp = client.delete(
        f"/api/problems/{problem.id}/cases/9999", headers=_auth(token)
    )
    assert resp.status_code == 404


# --- Classes ----------------------------------------------------------------


def test_create_class_admin_201_generates_unique_code(client, db_session):
    admin = _make_user(db_session, "admin", role="admin")
    token = _login(client, "admin")
    resp = client.post(
        "/api/classes",
        json={"name": "Intro", "teacher_id": admin.id},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Intro"
    assert len(body["code"]) == 6
    assert body["anticheat_threshold"] == 0.85
    resp2 = client.post(
        "/api/classes",
        json={"name": "Intro 2", "teacher_id": admin.id},
        headers=_auth(token),
    )
    assert resp2.status_code == 201
    assert resp2.json()["code"] != body["code"]


def test_create_class_teacher_403(client, db_session):
    _make_user(db_session, "prof", role="teacher")
    token = _login(client, "prof")
    resp = client.post(
        "/api/classes", json={"name": "Intro"}, headers=_auth(token)
    )
    assert resp.status_code == 403


def test_create_class_student_403(client, db_session):
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.post(
        "/api/classes", json={"name": "Intro"}, headers=_auth(token)
    )
    assert resp.status_code == 403


def test_get_class_by_code_for_join(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    cls = _make_class(db_session, teacher, code="ABC123")
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.get("/api/classes/ABC123", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == "ABC123"
    assert body["name"] == "Intro"
    assert body["id"] == cls.id


def test_get_class_by_code_not_found_404(client, db_session):
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.get("/api/classes/NOPE99", headers=_auth(token))
    assert resp.status_code == 404


def test_list_classes_teacher_sees_own(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    other = _make_user(db_session, "other", role="teacher")
    _make_class(db_session, teacher, code="C1")
    _make_class(db_session, other, code="C2")
    token = _login(client, "prof")
    resp = client.get("/api/classes", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["code"] == "C1"


def test_patch_class_own_teacher_200(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    cls = _make_class(db_session, teacher, code="C1")
    token = _login(client, "prof")
    resp = client.patch(
        f"/api/classes/{cls.id}",
        json={"name": "Intro v2", "anticheat_threshold": 0.9},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Intro v2"
    assert body["anticheat_threshold"] == 0.9


def test_patch_class_other_teacher_403(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    _make_user(db_session, "other", role="teacher")
    cls = _make_class(db_session, teacher, code="C1")
    token = _login(client, "other")
    resp = client.patch(
        f"/api/classes/{cls.id}", json={"name": "hacked"}, headers=_auth(token)
    )
    assert resp.status_code == 403


def test_patch_class_admin_200(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    cls = _make_class(db_session, teacher, code="C1")
    _make_user(db_session, "admin", role="admin")
    token = _login(client, "admin")
    resp = client.patch(
        f"/api/classes/{cls.id}", json={"name": "renamed"}, headers=_auth(token)
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "renamed"


def test_patch_class_student_403(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    cls = _make_class(db_session, teacher, code="C1")
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.patch(
        f"/api/classes/{cls.id}", json={"name": "hacked"}, headers=_auth(token)
    )
    assert resp.status_code == 403


# --- Assignments ------------------------------------------------------------


def test_create_assignment_teacher_own_class_201(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    cls = _make_class(db_session, teacher, code="C1")
    problem = _make_problem(db_session, teacher)
    token = _login(client, "prof")
    deadline = (datetime.now(UTC) + timedelta(days=7)).isoformat()
    resp = client.post(
        "/api/assignments",
        json={"class_id": cls.id, "problem_id": problem.id, "deadline": deadline},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["class_id"] == cls.id
    assert body["problem_id"] == problem.id


def test_create_assignment_teacher_other_class_403(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    other = _make_user(db_session, "other", role="teacher")
    cls = _make_class(db_session, other, code="C2")
    problem = _make_problem(db_session, teacher)
    token = _login(client, "prof")
    resp = client.post(
        "/api/assignments",
        json={
            "class_id": cls.id,
            "problem_id": problem.id,
            "deadline": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        },
        headers=_auth(token),
    )
    assert resp.status_code == 403


def test_create_assignment_admin_201(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    cls = _make_class(db_session, teacher, code="C1")
    problem = _make_problem(db_session, teacher)
    _make_user(db_session, "admin", role="admin")
    token = _login(client, "admin")
    resp = client.post(
        "/api/assignments",
        json={
            "class_id": cls.id,
            "problem_id": problem.id,
            "deadline": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201


def test_create_assignment_student_403(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    cls = _make_class(db_session, teacher, code="C1")
    problem = _make_problem(db_session, teacher)
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.post(
        "/api/assignments",
        json={
            "class_id": cls.id,
            "problem_id": problem.id,
            "deadline": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        },
        headers=_auth(token),
    )
    assert resp.status_code == 403


def test_create_assignment_unknown_problem_404(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    cls = _make_class(db_session, teacher, code="C1")
    token = _login(client, "prof")
    resp = client.post(
        "/api/assignments",
        json={
            "class_id": cls.id,
            "problem_id": 9999,
            "deadline": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        },
        headers=_auth(token),
    )
    assert resp.status_code == 404


def test_list_assignments_student_sees_own_class(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    cls = _make_class(db_session, teacher, code="C1")
    problem = _make_problem(db_session, teacher)
    _make_assignment(db_session, cls, problem)
    alice = _make_user(db_session, "alice")
    db_session.add(ClassMember(class_id=cls.id, user_id=alice.id))
    db_session.commit()
    token = _login(client, "alice")
    resp = client.get("/api/assignments", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["problem_id"] == problem.id


def test_list_assignments_teacher_sees_own(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    other = _make_user(db_session, "other", role="teacher")
    cls = _make_class(db_session, teacher, code="C1")
    other_cls = _make_class(db_session, other, code="C2")
    problem = _make_problem(db_session, teacher)
    mine = _make_assignment(db_session, cls, problem)
    _make_assignment(db_session, other_cls, problem)
    token = _login(client, "prof")
    resp = client.get("/api/assignments", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == mine.id


# --- Assignment submissions (todo 23) ---------------------------------------


def test_assignment_submissions_teacher_200(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    bob = _make_user(db_session, "bob")
    cls = _make_class(db_session, teacher, code="C1")
    db_session.add(ClassMember(class_id=cls.id, user_id=alice.id))
    db_session.add(ClassMember(class_id=cls.id, user_id=bob.id))
    db_session.commit()
    problem = _make_problem(db_session, teacher)
    assignment = _make_assignment(db_session, cls, problem)
    # alice: WA/20 then AC/10 -> best AC/10 (verdict priority, then steps)
    _seed_run(
        db_session, alice, problem, kind="assignment", assignment=assignment,
        verdict="WA", case_verdicts=["WA"], steps=20,
    )
    _seed_run(
        db_session, alice, problem, kind="assignment", assignment=assignment,
        verdict="AC", case_verdicts=["AC"], steps=10,
    )
    # bob: WA/5 only -> best WA/5
    _seed_run(
        db_session, bob, problem, kind="assignment", assignment=assignment,
        verdict="WA", case_verdicts=["WA"], steps=5,
    )
    token = _login(client, "prof")
    resp = client.get(
        f"/api/assignments/{assignment.id}/submissions", headers=_auth(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    by_user = {row["user_id"]: row for row in body}
    assert by_user[alice.id]["username"] == "alice"
    assert by_user[alice.id]["best_verdict"] == "AC"
    assert by_user[alice.id]["steps"] == 10
    assert by_user[alice.id]["source"] == VALID_SOURCE
    assert by_user[bob.id]["username"] == "bob"
    assert by_user[bob.id]["best_verdict"] == "WA"
    assert by_user[bob.id]["steps"] == 5


def test_assignment_submissions_admin_200(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    cls = _make_class(db_session, teacher, code="C1")
    db_session.add(ClassMember(class_id=cls.id, user_id=alice.id))
    db_session.commit()
    problem = _make_problem(db_session, teacher)
    assignment = _make_assignment(db_session, cls, problem)
    _seed_run(
        db_session, alice, problem, kind="assignment", assignment=assignment,
        verdict="AC", case_verdicts=["AC"],
    )
    _make_user(db_session, "admin", role="admin")
    token = _login(client, "admin")
    resp = client.get(
        f"/api/assignments/{assignment.id}/submissions", headers=_auth(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["best_verdict"] == "AC"


def test_assignment_submissions_student_403(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    cls = _make_class(db_session, teacher, code="C1")
    db_session.add(ClassMember(class_id=cls.id, user_id=alice.id))
    db_session.commit()
    problem = _make_problem(db_session, teacher)
    assignment = _make_assignment(db_session, cls, problem)
    token = _login(client, "alice")
    resp = client.get(
        f"/api/assignments/{assignment.id}/submissions", headers=_auth(token)
    )
    assert resp.status_code == 403


def test_assignment_submissions_other_teacher_403(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    _make_user(db_session, "other", role="teacher")
    cls = _make_class(db_session, teacher, code="C1")
    problem = _make_problem(db_session, teacher)
    assignment = _make_assignment(db_session, cls, problem)
    token = _login(client, "other")
    resp = client.get(
        f"/api/assignments/{assignment.id}/submissions", headers=_auth(token)
    )
    assert resp.status_code == 403


def test_assignment_submissions_not_found_404(client, db_session):
    _make_user(db_session, "prof", role="teacher")
    token = _login(client, "prof")
    resp = client.get(
        "/api/assignments/9999/submissions", headers=_auth(token)
    )
    assert resp.status_code == 404


# --- Contests ---------------------------------------------------------------


def _contest_payload(**overrides) -> dict:
    now = datetime.now(UTC)
    payload = {
        "title": "Concurso",
        "start_at": (now - timedelta(hours=1)).isoformat(),
        "end_at": (now + timedelta(hours=1)).isoformat(),
        "scoring_mode": "cf",
        "teams_enabled": False,
    }
    payload.update(overrides)
    return payload


def test_create_contest_teacher_201(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    token = _login(client, "prof")
    resp = client.post(
        "/api/contests", json=_contest_payload(), headers=_auth(token)
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Concurso"
    assert body["scoring_mode"] == "cf"
    assert body["teams_enabled"] is False
    assert body["created_by"] == teacher.id


def test_create_contest_student_403(client, db_session):
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.post(
        "/api/contests", json=_contest_payload(), headers=_auth(token)
    )
    assert resp.status_code == 403


def test_create_contest_invalid_times_422(client, db_session):
    _make_user(db_session, "prof", role="teacher")
    token = _login(client, "prof")
    now = datetime.now(UTC)
    resp = client.post(
        "/api/contests",
        json=_contest_payload(
            start_at=(now + timedelta(hours=1)).isoformat(),
            end_at=(now - timedelta(hours=1)).isoformat(),
        ),
        headers=_auth(token),
    )
    assert resp.status_code == 422


def test_list_contests(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    _make_contest(db_session, teacher, title="C1")
    _make_contest(db_session, teacher, title="C2")
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.get("/api/contests", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert {c["title"] for c in body["items"]} == {"C1", "C2"}


def test_get_contest(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    contest = _make_contest(db_session, teacher, title="C1")
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.get(f"/api/contests/{contest.id}", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["title"] == "C1"


def test_register_contest_201(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    contest = _make_contest(db_session, teacher)
    alice = _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.post(
        f"/api/contests/{contest.id}/register", headers=_auth(token)
    )
    assert resp.status_code == 201
    participant = db_session.get(ContestParticipant, (contest.id, alice.id))
    assert participant is not None


def test_register_contest_duplicate_409(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    contest = _make_contest(db_session, teacher)
    alice = _make_user(db_session, "alice")
    db_session.add(ContestParticipant(contest_id=contest.id, user_id=alice.id))
    db_session.commit()
    token = _login(client, "alice")
    resp = client.post(
        f"/api/contests/{contest.id}/register", headers=_auth(token)
    )
    assert resp.status_code == 409


def test_create_team_teacher_201(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    contest = _make_contest(db_session, teacher, teams_enabled=True)
    token = _login(client, "prof")
    resp = client.post(
        f"/api/contests/{contest.id}/teams",
        json={"name": "Equipo A"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Equipo A"
    assert body["contest_id"] == contest.id


def test_create_team_when_disabled_409(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    contest = _make_contest(db_session, teacher, teams_enabled=False)
    token = _login(client, "prof")
    resp = client.post(
        f"/api/contests/{contest.id}/teams",
        json={"name": "Equipo A"},
        headers=_auth(token),
    )
    assert resp.status_code == 409


def test_create_team_student_403(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    contest = _make_contest(db_session, teacher, teams_enabled=True)
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.post(
        f"/api/contests/{contest.id}/teams",
        json={"name": "Equipo A"},
        headers=_auth(token),
    )
    assert resp.status_code == 403


def test_join_team_student_201(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    contest = _make_contest(db_session, teacher, teams_enabled=True)
    team = ContestTeam(contest_id=contest.id, name="Equipo A")
    db_session.add(team)
    db_session.commit()
    alice = _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.post(
        f"/api/contests/{contest.id}/teams/{team.id}/members",
        json={"user_id": alice.id},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    member = db_session.get(ContestTeamMember, (team.id, alice.id))
    assert member is not None


def test_join_team_second_team_409(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    contest = _make_contest(db_session, teacher, teams_enabled=True)
    team_a = ContestTeam(contest_id=contest.id, name="A")
    team_b = ContestTeam(contest_id=contest.id, name="B")
    db_session.add_all([team_a, team_b])
    db_session.commit()
    alice = _make_user(db_session, "alice")
    db_session.add(ContestTeamMember(team_id=team_a.id, user_id=alice.id))
    db_session.commit()
    token = _login(client, "alice")
    resp = client.post(
        f"/api/contests/{contest.id}/teams/{team_b.id}/members",
        json={"user_id": alice.id},
        headers=_auth(token),
    )
    assert resp.status_code == 409


def test_list_teams(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    contest = _make_contest(db_session, teacher, teams_enabled=True)
    db_session.add(ContestTeam(contest_id=contest.id, name="A"))
    db_session.add(ContestTeam(contest_id=contest.id, name="B"))
    db_session.commit()
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.get(
        f"/api/contests/{contest.id}/teams", headers=_auth(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert {t["name"] for t in body} == {"A", "B"}


# --- Scoreboard -------------------------------------------------------------


def test_scoreboard_cf_shape(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    bob = _make_user(db_session, "bob")
    p1 = _make_problem(db_session, teacher, title="P1")
    p2 = _make_problem(db_session, teacher, title="P2")
    _make_test_case(db_session, p1, expected="1", order=0)
    _make_test_case(db_session, p2, expected="1", order=0)
    now = datetime.now(UTC)
    start_at = now - timedelta(hours=2)
    contest = _make_contest(
        db_session,
        teacher,
        title="CF",
        scoring_mode="cf",
        start_at=start_at,
        end_at=now + timedelta(hours=2),
    )
    db_session.add(ContestProblem(contest_id=contest.id, problem_id=p1.id, order=0))
    db_session.add(ContestProblem(contest_id=contest.id, problem_id=p2.id, order=1))
    db_session.add(ContestParticipant(contest_id=contest.id, user_id=alice.id))
    db_session.add(ContestParticipant(contest_id=contest.id, user_id=bob.id))
    db_session.commit()
    # alice: AC p1 at +10min, AC p2 at +30min -> 2 solves, penalty 40
    _seed_run(
        db_session, alice, p1, kind="contest", contest=contest,
        created_at=start_at + timedelta(minutes=10), verdict="AC", case_verdicts=["AC"],
    )
    _seed_run(
        db_session, alice, p2, kind="contest", contest=contest,
        created_at=start_at + timedelta(minutes=30), verdict="AC", case_verdicts=["AC"],
    )
    # bob: AC p1 at +5min -> 1 solve, penalty 5
    _seed_run(
        db_session, bob, p1, kind="contest", contest=contest,
        created_at=start_at + timedelta(minutes=5), verdict="AC", case_verdicts=["AC"],
    )
    token = _login(client, "alice")
    resp = client.get(
        f"/api/contests/{contest.id}/scoreboard", headers=_auth(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "cf"
    rows = body["rows"]
    assert len(rows) == 2
    assert rows[0]["participant_id"] == str(alice.id)
    assert rows[0]["solves"] == 2
    assert rows[0]["penalty"] == 40
    assert rows[1]["participant_id"] == str(bob.id)
    assert rows[1]["solves"] == 1
    assert rows[1]["penalty"] == 5


def test_scoreboard_ioi_shape(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    bob = _make_user(db_session, "bob")
    p1 = _make_problem(db_session, teacher, title="P1")
    _make_test_case(db_session, p1, expected="1", points=2, order=0)
    _make_test_case(db_session, p1, expected="2", points=3, order=1)
    now = datetime.now(UTC)
    contest = _make_contest(
        db_session,
        teacher,
        title="IOI",
        scoring_mode="ioi",
        start_at=now - timedelta(hours=1),
        end_at=now + timedelta(hours=1),
    )
    db_session.add(ContestProblem(contest_id=contest.id, problem_id=p1.id, order=0))
    db_session.add(ContestParticipant(contest_id=contest.id, user_id=alice.id))
    db_session.add(ContestParticipant(contest_id=contest.id, user_id=bob.id))
    db_session.commit()
    # alice: both cases AC -> 2 + 3 = 5 points
    _seed_run(
        db_session, alice, p1, kind="contest", contest=contest,
        created_at=now, verdict="AC", case_verdicts=["AC", "AC"],
    )
    # bob: first case only -> 2 points
    _seed_run(
        db_session, bob, p1, kind="contest", contest=contest,
        created_at=now, verdict="WA", case_verdicts=["AC", "WA"],
    )
    token = _login(client, "alice")
    resp = client.get(
        f"/api/contests/{contest.id}/scoreboard", headers=_auth(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "ioi"
    rows = body["rows"]
    assert len(rows) == 2
    assert rows[0]["participant_id"] == str(alice.id)
    assert rows[0]["points"] == 5
    assert rows[1]["participant_id"] == str(bob.id)
    assert rows[1]["points"] == 2


def test_scoreboard_non_participant_403(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    contest = _make_contest(db_session, teacher)
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.get(
        f"/api/contests/{contest.id}/scoreboard", headers=_auth(token)
    )
    assert resp.status_code == 403


# --- Runs -------------------------------------------------------------------


def test_submit_practice_202(client, db_session):
    alice = _make_user(db_session, "alice")
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher)
    token = _login(client, "alice")
    resp = client.post(
        "/api/runs",
        json={"problem_id": problem.id, "source": VALID_SOURCE, "mode": "practice"},
        headers=_auth(token),
    )
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]
    run = db_session.get(Run, run_id)
    assert run is not None
    assert run.kind == "practice"
    assert run.status == "queued"
    assert run.user_id == alice.id
    assert run.problem_id == problem.id


def test_submit_assignment_202(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    cls = _make_class(db_session, teacher, code="C1")
    db_session.add(ClassMember(class_id=cls.id, user_id=alice.id))
    db_session.commit()
    problem = _make_problem(db_session, teacher)
    assignment = _make_assignment(
        db_session, cls, problem, deadline=datetime.now(UTC) + timedelta(hours=1)
    )
    token = _login(client, "alice")
    resp = client.post(
        "/api/runs",
        json={
            "problem_id": problem.id,
            "source": VALID_SOURCE,
            "mode": "assignment",
            "assignment_id": assignment.id,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 202
    run = db_session.get(Run, resp.json()["run_id"])
    assert run.kind == "assignment"
    assert run.assignment_id == assignment.id


def test_submit_assignment_after_deadline_422(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    cls = _make_class(db_session, teacher, code="C1")
    db_session.add(ClassMember(class_id=cls.id, user_id=alice.id))
    db_session.commit()
    problem = _make_problem(db_session, teacher)
    assignment = _make_assignment(
        db_session, cls, problem, deadline=datetime.now(UTC) - timedelta(hours=1)
    )
    token = _login(client, "alice")
    resp = client.post(
        "/api/runs",
        json={
            "problem_id": problem.id,
            "source": VALID_SOURCE,
            "mode": "assignment",
            "assignment_id": assignment.id,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "ASSIGNMENT_CLOSED"


def test_submit_contest_202(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    problem = _make_problem(db_session, teacher)
    now = datetime.now(UTC)
    contest = _make_contest(
        db_session, teacher, start_at=now - timedelta(hours=1),
        end_at=now + timedelta(hours=1),
    )
    db_session.add(
        ContestProblem(contest_id=contest.id, problem_id=problem.id, order=0)
    )
    db_session.add(ContestParticipant(contest_id=contest.id, user_id=alice.id))
    db_session.commit()
    token = _login(client, "alice")
    resp = client.post(
        "/api/runs",
        json={
            "problem_id": problem.id,
            "source": VALID_SOURCE,
            "mode": "contest",
            "contest_id": contest.id,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 202
    run = db_session.get(Run, resp.json()["run_id"])
    assert run.kind == "contest"
    assert run.contest_id == contest.id


def test_submit_contest_not_participant_403(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    _make_user(db_session, "alice")
    problem = _make_problem(db_session, teacher)
    contest = _make_contest(db_session, teacher)
    db_session.add(
        ContestProblem(contest_id=contest.id, problem_id=problem.id, order=0)
    )
    db_session.commit()
    token = _login(client, "alice")
    resp = client.post(
        "/api/runs",
        json={
            "problem_id": problem.id,
            "source": VALID_SOURCE,
            "mode": "contest",
            "contest_id": contest.id,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 403


def test_submit_source_too_large_413(client, db_session):
    _make_user(db_session, "alice")
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher)
    token = _login(client, "alice")
    big = "Proceso P\n" + "  Escribir 1\n" * 20000 + "FinProceso\n"
    assert len(big.encode()) > 65536
    resp = client.post(
        "/api/runs",
        json={"problem_id": problem.id, "source": big, "mode": "practice"},
        headers=_auth(token),
    )
    assert resp.status_code == 413


def test_submit_unauthenticated_401(client):
    resp = client.post(
        "/api/runs",
        json={"problem_id": 1, "source": VALID_SOURCE, "mode": "practice"},
    )
    assert resp.status_code == 401


def test_submit_invalid_mode_422(client, db_session):
    _make_user(db_session, "alice")
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher)
    token = _login(client, "alice")
    resp = client.post(
        "/api/runs",
        json={"problem_id": problem.id, "source": VALID_SOURCE, "mode": "exam"},
        headers=_auth(token),
    )
    assert resp.status_code == 422


def test_submit_unknown_problem_404(client, db_session):
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.post(
        "/api/runs",
        json={"problem_id": 9999, "source": VALID_SOURCE, "mode": "practice"},
        headers=_auth(token),
    )
    assert resp.status_code == 404


def test_get_run_owner_with_results(client, db_session):
    _make_user(db_session, "alice")
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher)
    token = _login(client, "alice")
    resp = client.post(
        "/api/runs",
        json={"problem_id": problem.id, "source": VALID_SOURCE, "mode": "practice"},
        headers=_auth(token),
    )
    run_id = resp.json()["run_id"]
    # simulate the worker (todo 35): insert TestResult rows directly
    db_session.add(
        TestResult(run_id=run_id, case_index=0, verdict="AC", steps=3, wall_ms=2)
    )
    db_session.add(
        TestResult(run_id=run_id, case_index=1, verdict="WA", steps=4, wall_ms=2)
    )
    db_session.commit()
    resp = client.get(f"/api/runs/{run_id}", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == run_id
    assert body["kind"] == "practice"
    assert len(body["test_results"]) == 2
    assert body["test_results"][0]["verdict"] == "AC"
    assert body["test_results"][1]["verdict"] == "WA"


def test_get_run_other_user_403(client, db_session):
    _make_user(db_session, "alice")
    _make_user(db_session, "bob")
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher)
    token_alice = _login(client, "alice")
    resp = client.post(
        "/api/runs",
        json={"problem_id": problem.id, "source": VALID_SOURCE, "mode": "practice"},
        headers=_auth(token_alice),
    )
    run_id = resp.json()["run_id"]
    token_bob = _login(client, "bob")
    resp = client.get(f"/api/runs/{run_id}", headers=_auth(token_bob))
    assert resp.status_code == 403


def test_get_run_teacher_contest_observer_200(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    problem = _make_problem(db_session, teacher)
    now = datetime.now(UTC)
    contest = _make_contest(
        db_session, teacher, start_at=now - timedelta(hours=1),
        end_at=now + timedelta(hours=1),
    )
    db_session.add(
        ContestProblem(contest_id=contest.id, problem_id=problem.id, order=0)
    )
    db_session.add(ContestParticipant(contest_id=contest.id, user_id=alice.id))
    db_session.commit()
    token_alice = _login(client, "alice")
    resp = client.post(
        "/api/runs",
        json={
            "problem_id": problem.id,
            "source": VALID_SOURCE,
            "mode": "contest",
            "contest_id": contest.id,
        },
        headers=_auth(token_alice),
    )
    run_id = resp.json()["run_id"]
    token_teacher = _login(client, "prof")
    resp = client.get(f"/api/runs/{run_id}", headers=_auth(token_teacher))
    assert resp.status_code == 200
    assert resp.json()["id"] == run_id


def test_get_run_not_found_404(client, db_session):
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.get("/api/runs/9999", headers=_auth(token))
    assert resp.status_code == 404


def test_list_own_runs(client, db_session):
    alice = _make_user(db_session, "alice")
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher)
    token = _login(client, "alice")
    for _ in range(2):
        resp = client.post(
            "/api/runs",
            json={"problem_id": problem.id, "source": VALID_SOURCE, "mode": "practice"},
            headers=_auth(token),
        )
        assert resp.status_code == 202
    resp = client.get("/api/runs", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert all(r["user_id"] == alice.id for r in body)


def test_practice_run_has_no_test_results(client, db_session):
    _make_user(db_session, "alice")
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher)
    token = _login(client, "alice")
    resp = client.post(
        "/api/runs",
        json={"problem_id": problem.id, "source": VALID_SOURCE, "mode": "practice"},
        headers=_auth(token),
    )
    run_id = resp.json()["run_id"]
    results = db_session.scalars(
        select(TestResult).where(TestResult.run_id == run_id)
    ).all()
    assert results == []


# --- Forums -----------------------------------------------------------------


def test_create_thread_201(client, db_session):
    _make_user(db_session, "alice")
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher)
    token = _login(client, "alice")
    resp = client.post(
        f"/api/problems/{problem.id}/threads",
        json={"title": "Duda", "body": "¿Cómo se hace?"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Duda"
    assert body["problem_id"] == problem.id
    thread = db_session.get(ForumThread, body["id"])
    assert thread is not None
    posts = db_session.scalars(
        select(ForumPost).where(ForumPost.thread_id == thread.id)
    ).all()
    assert len(posts) == 1
    assert posts[0].body == "¿Cómo se hace?"


def test_create_thread_unauthenticated_401(client):
    resp = client.post(
        "/api/problems/1/threads", json={"title": "Duda", "body": "¿?"}
    )
    assert resp.status_code == 401


def test_list_threads(client, db_session):
    _make_user(db_session, "alice")
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher)
    token = _login(client, "alice")
    client.post(
        f"/api/problems/{problem.id}/threads",
        json={"title": "T1", "body": "b1"},
        headers=_auth(token),
    )
    client.post(
        f"/api/problems/{problem.id}/threads",
        json={"title": "T2", "body": "b2"},
        headers=_auth(token),
    )
    resp = client.get(
        f"/api/problems/{problem.id}/threads", headers=_auth(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert {t["title"] for t in body} == {"T1", "T2"}


def test_create_post_201(client, db_session):
    alice = _make_user(db_session, "alice")
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher)
    thread = ForumThread(problem_id=problem.id, title="Duda", created_by=alice.id)
    db_session.add(thread)
    db_session.commit()
    token = _login(client, "alice")
    resp = client.post(
        f"/api/threads/{thread.id}/posts",
        json={"body": "Respuesta"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["thread_id"] == thread.id
    assert body["body"] == "Respuesta"
    assert body["author_id"] == alice.id


def test_list_posts(client, db_session):
    alice = _make_user(db_session, "alice")
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher)
    thread = ForumThread(problem_id=problem.id, title="Duda", created_by=alice.id)
    db_session.add(thread)
    db_session.commit()
    token = _login(client, "alice")
    client.post(
        f"/api/threads/{thread.id}/posts", json={"body": "p1"}, headers=_auth(token)
    )
    client.post(
        f"/api/threads/{thread.id}/posts", json={"body": "p2"}, headers=_auth(token)
    )
    resp = client.get(f"/api/threads/{thread.id}/posts", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert [p["body"] for p in body] == ["p1", "p2"]


def test_contest_phase_lock_student_403(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    _make_user(db_session, "alice")
    problem = _make_problem(db_session, teacher)
    now = datetime.now(UTC)
    contest = _make_contest(
        db_session, teacher, start_at=now - timedelta(hours=1),
        end_at=now + timedelta(hours=1),
    )
    db_session.add(
        ContestProblem(contest_id=contest.id, problem_id=problem.id, order=0)
    )
    db_session.commit()
    token = _login(client, "alice")
    resp = client.post(
        f"/api/problems/{problem.id}/threads",
        json={"title": "Duda", "body": "¿?"},
        headers=_auth(token),
    )
    assert resp.status_code == 403


def test_contest_phase_lock_teacher_201(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher)
    now = datetime.now(UTC)
    contest = _make_contest(
        db_session, teacher, start_at=now - timedelta(hours=1),
        end_at=now + timedelta(hours=1),
    )
    db_session.add(
        ContestProblem(contest_id=contest.id, problem_id=problem.id, order=0)
    )
    db_session.commit()
    token = _login(client, "prof")
    resp = client.post(
        f"/api/problems/{problem.id}/threads",
        json={"title": "Anuncio", "body": "Reglas"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    assert resp.json()["contest_id"] == contest.id


def test_contest_before_window_student_ok(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    _make_user(db_session, "alice")
    problem = _make_problem(db_session, teacher)
    now = datetime.now(UTC)
    contest = _make_contest(
        db_session, teacher, start_at=now + timedelta(hours=2),
        end_at=now + timedelta(hours=3),
    )
    db_session.add(
        ContestProblem(contest_id=contest.id, problem_id=problem.id, order=0)
    )
    db_session.commit()
    token = _login(client, "alice")
    resp = client.post(
        f"/api/problems/{problem.id}/threads",
        json={"title": "Duda", "body": "¿?"},
        headers=_auth(token),
    )
    assert resp.status_code == 201


def test_contest_after_window_student_ok(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    _make_user(db_session, "alice")
    problem = _make_problem(db_session, teacher)
    now = datetime.now(UTC)
    contest = _make_contest(
        db_session, teacher, start_at=now - timedelta(hours=3),
        end_at=now - timedelta(hours=2),
    )
    db_session.add(
        ContestProblem(contest_id=contest.id, problem_id=problem.id, order=0)
    )
    db_session.commit()
    token = _login(client, "alice")
    resp = client.post(
        f"/api/problems/{problem.id}/threads",
        json={"title": "Duda", "body": "¿?"},
        headers=_auth(token),
    )
    assert resp.status_code == 201


# --- Similarity -------------------------------------------------------------


def test_similarity_report_teacher_200(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    bob = _make_user(db_session, "bob")
    cls = _make_class(db_session, teacher, code="C1")
    db_session.add(ClassMember(class_id=cls.id, user_id=alice.id))
    db_session.add(ClassMember(class_id=cls.id, user_id=bob.id))
    db_session.commit()
    problem = _make_problem(db_session, teacher)
    r1 = _seed_run(db_session, alice, problem)
    r2 = _seed_run(db_session, bob, problem)
    db_session.add(
        SimilarityPair(run_a_id=r1.id, run_b_id=r2.id, score=0.95, scope="class")
    )
    db_session.commit()
    token = _login(client, "prof")
    resp = client.get(f"/api/classes/{cls.id}/similarity", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["score"] == 0.95
    assert body[0]["scope"] == "class"
    assert body[0]["run_a_id"] == r1.id


def test_similarity_below_threshold_excluded(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    bob = _make_user(db_session, "bob")
    cls = _make_class(db_session, teacher, code="C1")
    db_session.add(ClassMember(class_id=cls.id, user_id=alice.id))
    db_session.add(ClassMember(class_id=cls.id, user_id=bob.id))
    db_session.commit()
    problem = _make_problem(db_session, teacher)
    r1 = _seed_run(db_session, alice, problem)
    r2 = _seed_run(db_session, bob, problem)
    db_session.add(
        SimilarityPair(run_a_id=r1.id, run_b_id=r2.id, score=0.50, scope="class")
    )
    db_session.commit()
    token = _login(client, "prof")
    resp = client.get(f"/api/classes/{cls.id}/similarity", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json() == []


def test_similarity_student_403(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    cls = _make_class(db_session, teacher, code="C1")
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.get(f"/api/classes/{cls.id}/similarity", headers=_auth(token))
    assert resp.status_code == 403


def test_similarity_other_teacher_403(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    _make_user(db_session, "other", role="teacher")
    cls = _make_class(db_session, teacher, code="C1")
    token = _login(client, "other")
    resp = client.get(f"/api/classes/{cls.id}/similarity", headers=_auth(token))
    assert resp.status_code == 403


def test_similarity_same_team_excluded(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    bob = _make_user(db_session, "bob")
    cls = _make_class(db_session, teacher, code="C1")
    db_session.add(ClassMember(class_id=cls.id, user_id=alice.id))
    db_session.add(ClassMember(class_id=cls.id, user_id=bob.id))
    now = datetime.now(UTC)
    contest = _make_contest(
        db_session, teacher, teams_enabled=True,
        start_at=now - timedelta(hours=1), end_at=now + timedelta(hours=1),
    )
    team = ContestTeam(contest_id=contest.id, name="Equipo A")
    db_session.add(team)
    db_session.flush()
    db_session.add(ContestTeamMember(team_id=team.id, user_id=alice.id))
    db_session.add(ContestTeamMember(team_id=team.id, user_id=bob.id))
    db_session.commit()
    problem = _make_problem(db_session, teacher)
    r1 = _seed_run(db_session, alice, problem, kind="contest", contest=contest)
    r2 = _seed_run(db_session, bob, problem, kind="contest", contest=contest)
    db_session.add(
        SimilarityPair(run_a_id=r1.id, run_b_id=r2.id, score=0.95, scope="contest")
    )
    db_session.commit()
    token = _login(client, "prof")
    resp = client.get(f"/api/classes/{cls.id}/similarity", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json() == []
