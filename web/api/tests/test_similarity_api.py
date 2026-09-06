"""Similarity report API tests (todo 39).

Covers the plan §39 acceptance: list pairs above threshold, below-threshold
filter, student 403, cross-teacher 403, POST threshold validation (out of
range -> 422), pair endpoint returns originals only (no normalization leak),
contest scope respects ``teams_enabled``, admin can access any class.

The persistence half is covered too: the table is populated by the worker
(todo 35) in production; this module seeds ``similarity_pairs`` directly
and ALSO exercises the on-demand compute branch (empty table -> engine
``find_pairs`` -> persisted rows visible on the next request).

Runs against a dedicated ``pseint_test`` database on the same Postgres
(reusing the todo-18 fixture pattern).  Todo 39 adds NO tables; the
existing migration is unchanged.
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
    ContestTeam,
    ContestTeamMember,
    Problem,
    Run,
    SimilarityPair,
    User,
)
from pseint_api.ratelimit import InMemoryRateLimiter

TEST_DB_NAME = "pseint_test"
ADMIN_URL = "postgresql+psycopg://pseint:pseint@localhost:5432/postgres"


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


# --- Seeding helpers --------------------------------------------------------


def _make_user(
    db: Session, username: str = "alice", role: str = "student"
) -> User:
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
    db: Session, author: User, title: str = "Suma"
) -> Problem:
    problem = Problem(
        title=title,
        statement="Sumar dos numeros",
        expected_complexity="O(1)",
        compare_mode="exact",
        author_id=author.id,
    )
    db.add(problem)
    db.commit()
    return problem


def _make_run(
    db: Session,
    user: User,
    problem: Problem,
    source: str = "Proceso P\n  Escribir 1\nFinProceso\n",
    kind: str = "practice",
    contest: Contest | None = None,
    assignment: Assignment | None = None,
) -> Run:
    run = Run(
        user_id=user.id,
        problem_id=problem.id,
        kind=kind,
        status="done",
        source=source,
        contest_id=contest.id if contest is not None else None,
        assignment_id=assignment.id if assignment is not None else None,
    )
    db.add(run)
    db.commit()
    return run


def _make_assignment(
    db: Session, cls: Class, problem: Problem
) -> Assignment:
    assignment = Assignment(
        class_id=cls.id,
        problem_id=problem.id,
        deadline=datetime.now(UTC) + timedelta(hours=1),
    )
    db.add(assignment)
    db.commit()
    return assignment


def _make_contest(
    db: Session,
    teacher: User,
    title: str = "Concurso",
    teams_enabled: bool = False,
) -> Contest:
    now = datetime.now(UTC)
    contest = Contest(
        title=title,
        start_at=now - timedelta(hours=1),
        end_at=now + timedelta(hours=1),
        scoring_mode="cf",
        teams_enabled=teams_enabled,
        created_by=teacher.id,
    )
    db.add(contest)
    db.commit()
    return contest


def _login(client: TestClient, username: str, password: str = "x") -> str:
    resp = client.post(
        "/api/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Acceptance tests -------------------------------------------------------


def test_seeded_pair_appears_above_threshold(client, db_session):
    """Seeded pair with score >= default threshold appears in GET response."""
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    bob = _make_user(db_session, "bob")
    cls = _make_class(db_session, teacher, code="C1")
    db_session.add(ClassMember(class_id=cls.id, user_id=alice.id))
    db_session.add(ClassMember(class_id=cls.id, user_id=bob.id))
    db_session.commit()
    problem = _make_problem(db_session, teacher)
    r1 = _make_run(db_session, alice, problem)
    r2 = _make_run(db_session, bob, problem)
    db_session.add(
        SimilarityPair(run_a_id=r1.id, run_b_id=r2.id, score=0.95, scope="class")
    )
    db_session.commit()

    token = _login(client, "prof")
    resp = client.get(
        f"/api/admin/anticheat?scope=class&scope_id={cls.id}",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["score"] == 0.95
    assert body[0]["scope"] == "class"
    assert body[0]["user_a_username"] == "alice"
    assert body[0]["user_b_username"] == "bob"
    assert body[0]["flagged"] is True


def test_below_threshold_filtered_out(client, db_session):
    """Pair below the (class default 0.85) threshold is dropped from response."""
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    bob = _make_user(db_session, "bob")
    cls = _make_class(db_session, teacher, code="C1")
    db_session.add(ClassMember(class_id=cls.id, user_id=alice.id))
    db_session.add(ClassMember(class_id=cls.id, user_id=bob.id))
    db_session.commit()
    problem = _make_problem(db_session, teacher)
    r1 = _make_run(db_session, alice, problem)
    r2 = _make_run(db_session, bob, problem)
    db_session.add(
        SimilarityPair(run_a_id=r1.id, run_b_id=r2.id, score=0.50, scope="class")
    )
    db_session.commit()

    token = _login(client, "prof")
    resp = client.get(
        f"/api/admin/anticheat?scope=class&scope_id={cls.id}",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_threshold_query_override(client, db_session):
    """``?threshold=`` overrides the class default."""
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    bob = _make_user(db_session, "bob")
    cls = _make_class(db_session, teacher, code="C1")
    db_session.add(ClassMember(class_id=cls.id, user_id=alice.id))
    db_session.add(ClassMember(class_id=cls.id, user_id=bob.id))
    db_session.commit()
    problem = _make_problem(db_session, teacher)
    r1 = _make_run(db_session, alice, problem)
    r2 = _make_run(db_session, bob, problem)
    # 0.70 is below the class default 0.85 but above the override 0.60.
    db_session.add(
        SimilarityPair(run_a_id=r1.id, run_b_id=r2.id, score=0.70, scope="class")
    )
    db_session.commit()

    token = _login(client, "prof")
    resp_default = client.get(
        f"/api/admin/anticheat?scope=class&scope_id={cls.id}",
        headers=_auth(token),
    )
    assert resp_default.status_code == 200
    assert resp_default.json() == []

    resp_low = client.get(
        f"/api/admin/anticheat?scope=class&scope_id={cls.id}&threshold=0.60",
        headers=_auth(token),
    )
    assert resp_low.status_code == 200
    assert len(resp_low.json()) == 1


def test_student_get_returns_403(client, db_session):
    """Students cannot read the anticheat report."""
    teacher = _make_user(db_session, "prof", role="teacher")
    _make_user(db_session, "alice")
    cls = _make_class(db_session, teacher, code="C1")

    token = _login(client, "alice")
    resp = client.get(
        f"/api/admin/anticheat?scope=class&scope_id={cls.id}",
        headers=_auth(token),
    )
    assert resp.status_code == 403


def test_other_teacher_class_returns_403(client, db_session):
    """Teacher B cannot view Teacher A's class scope (cross-teacher guard)."""
    teacher_a = _make_user(db_session, "profA", role="teacher")
    _make_user(db_session, "profB", role="teacher")
    cls = _make_class(db_session, teacher_a, code="A1")

    token_b = _login(client, "profB")
    resp = client.get(
        f"/api/admin/anticheat?scope=class&scope_id={cls.id}",
        headers=_auth(token_b),
    )
    assert resp.status_code == 403

    token_a = _login(client, "profA")
    resp_a = client.get(
        f"/api/admin/anticheat?scope=class&scope_id={cls.id}",
        headers=_auth(token_a),
    )
    assert resp_a.status_code == 200


def test_admin_can_access_any_class(client, db_session):
    """Admin bypasses the owning-teacher guard."""
    _make_user(db_session, "root", role="admin")
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    bob = _make_user(db_session, "bob")
    cls = _make_class(db_session, teacher, code="C1")
    db_session.add(ClassMember(class_id=cls.id, user_id=alice.id))
    db_session.add(ClassMember(class_id=cls.id, user_id=bob.id))
    db_session.commit()
    problem = _make_problem(db_session, teacher)
    r1 = _make_run(db_session, alice, problem)
    r2 = _make_run(db_session, bob, problem)
    db_session.add(
        SimilarityPair(run_a_id=r1.id, run_b_id=r2.id, score=0.95, scope="class")
    )
    db_session.commit()

    token_admin = _login(client, "root")
    resp = client.get(
        f"/api/admin/anticheat?scope=class&scope_id={cls.id}",
        headers=_auth(token_admin),
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_post_threshold_validation_422_for_out_of_range(client, db_session):
    """Pydantic Field(ge=0.0, le=1.0) rejects out-of-range with 422."""
    teacher = _make_user(db_session, "prof", role="teacher")
    cls = _make_class(db_session, teacher, code="C1")
    token = _login(client, "prof")

    resp_low = client.post(
        f"/api/admin/classes/{cls.id}/anticheat-threshold",
        json={"threshold": -0.1},
        headers=_auth(token),
    )
    assert resp_low.status_code == 422

    resp_high = client.post(
        f"/api/admin/classes/{cls.id}/anticheat-threshold",
        json={"threshold": 1.5},
        headers=_auth(token),
    )
    assert resp_high.status_code == 422


def test_post_threshold_updates_value(client, db_session):
    """Valid threshold is persisted and reflected in the response."""
    teacher = _make_user(db_session, "prof", role="teacher")
    cls = _make_class(db_session, teacher, code="C1")
    token = _login(client, "prof")

    resp = client.post(
        f"/api/admin/classes/{cls.id}/anticheat-threshold",
        json={"threshold": 0.92},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["anticheat_threshold"] == 0.92

    # Verify GET reflects the new value.
    listing = client.get(
        f"/api/admin/anticheat?scope=class&scope_id={cls.id}",
        headers=_auth(token),
    )
    assert listing.status_code == 200


def test_post_threshold_student_403(client, db_session):
    """Students cannot update the class threshold."""
    teacher = _make_user(db_session, "prof", role="teacher")
    cls = _make_class(db_session, teacher, code="C1")
    _make_user(db_session, "alice")
    token = _login(client, "alice")
    resp = client.post(
        f"/api/admin/classes/{cls.id}/anticheat-threshold",
        json={"threshold": 0.5},
        headers=_auth(token),
    )
    assert resp.status_code == 403


def test_pair_endpoint_returns_originals_no_normalization_leak(
    client, db_session
):
    """The pair endpoint returns ORIGINAL sources verbatim.

    The D13 normalization internals (folded identifiers, stripped
    whitespace) MUST NOT be exposed over the wire (plan §39, MUST NOT).
    Asserting the literal source text is preserved is the test.
    """
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    bob = _make_user(db_session, "bob")
    cls = _make_class(db_session, teacher, code="C1")
    db_session.add(ClassMember(class_id=cls.id, user_id=alice.id))
    db_session.add(ClassMember(class_id=cls.id, user_id=bob.id))
    db_session.commit()
    problem = _make_problem(db_session, teacher)
    src_a = (
        "Proceso Alice\n  Definir x Como Entero\n  x <- 7\n  Escribir x\nFinProceso\n"
    )
    src_b = (
        "Proceso Bob\n  Definir y Como Entero\n  y <- 7\n  Escribir y\nFinProceso\n"
    )
    r1 = _make_run(db_session, alice, problem, source=src_a)
    r2 = _make_run(db_session, bob, problem, source=src_b)
    db_session.add(
        SimilarityPair(run_a_id=r1.id, run_b_id=r2.id, score=0.92, scope="class")
    )
    db_session.commit()

    token = _login(client, "prof")
    resp = client.get(
        f"/api/admin/anticheat/pair/{r1.id}/{r2.id}",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    # Originals preserved byte-for-byte.
    assert body["source_a"] == src_a
    assert body["source_b"] == src_b
    # No normalization leak fields.
    forbidden_keys = {"normalized_a", "normalized_b", "tokens_a", "tokens_b"}
    assert forbidden_keys.isdisjoint(body.keys())
    assert "flagged" in body
    assert "score" in body


def test_pair_endpoint_computes_on_demand_and_persists(client, db_session):
    """When the pair is NOT in similarity_pairs, the API computes it."""
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    bob = _make_user(db_session, "bob")
    cls = _make_class(db_session, teacher, code="C1")
    db_session.add(ClassMember(class_id=cls.id, user_id=alice.id))
    db_session.add(ClassMember(class_id=cls.id, user_id=bob.id))
    db_session.commit()
    problem = _make_problem(db_session, teacher)
    # Same algorithm, renamed vars -> normalized forms match -> score 1.0.
    src_a = "Proceso A\n  Definir x Como Entero\n  x <- 7\n  Escribir x\nFinProceso\n"
    src_b = "Proceso B\n  Definir y Como Entero\n  y <- 7\n  Escribir y\nFinProceso\n"
    r1 = _make_run(db_session, alice, problem, source=src_a)
    r2 = _make_run(db_session, bob, problem, source=src_b)
    db_session.commit()

    token = _login(client, "prof")
    resp = client.get(
        f"/api/admin/anticheat/pair/{r1.id}/{r2.id}",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["score"] == 1.0
    assert body["flagged"] is True

    # The pair must now be in the table.
    persisted = db_session.scalar(
        select(SimilarityPair).where(
            SimilarityPair.run_a_id == min(r1.id, r2.id),
            SimilarityPair.run_b_id == max(r1.id, r2.id),
        )
    )
    assert persisted is not None
    assert persisted.score == 1.0


def test_pair_endpoint_student_403(client, db_session):
    """Students cannot fetch pair detail."""
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    bob = _make_user(db_session, "bob")
    cls = _make_class(db_session, teacher, code="C1")
    db_session.add(ClassMember(class_id=cls.id, user_id=alice.id))
    db_session.add(ClassMember(class_id=cls.id, user_id=bob.id))
    db_session.commit()
    problem = _make_problem(db_session, teacher)
    r1 = _make_run(db_session, alice, problem)
    r2 = _make_run(db_session, bob, problem)
    db_session.add(
        SimilarityPair(run_a_id=r1.id, run_b_id=r2.id, score=0.95, scope="class")
    )
    db_session.commit()

    _make_user(db_session, "eve")
    token = _login(client, "eve")
    resp = client.get(
        f"/api/admin/anticheat/pair/{r1.id}/{r2.id}",
        headers=_auth(token),
    )
    assert resp.status_code == 403


def test_contest_scope_respects_teams_enabled(client, db_session):
    """Same-team pairs are excluded ONLY when contest.teams_enabled is true.

    With ``teams_enabled=False`` there are no teams, so the exclusion
    predicate is a no-op (the pair is preserved).
    """
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    bob = _make_user(db_session, "bob")
    contest = _make_contest(db_session, teacher, teams_enabled=False)
    db_session.add(ContestParticipant(contest_id=contest.id, user_id=alice.id))
    db_session.add(ContestParticipant(contest_id=contest.id, user_id=bob.id))
    db_session.commit()
    problem = _make_problem(db_session, teacher)
    r1 = _make_run(db_session, alice, problem, kind="contest", contest=contest)
    r2 = _make_run(db_session, bob, problem, kind="contest", contest=contest)
    db_session.add(
        SimilarityPair(run_a_id=r1.id, run_b_id=r2.id, score=0.95, scope="contest")
    )
    db_session.commit()

    token = _login(client, "prof")
    resp = client.get(
        f"/api/admin/anticheat?scope=contest&scope_id={contest.id}",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_contest_scope_excludes_same_team_when_enabled(client, db_session):
    """teams_enabled=True + same team -> pair is excluded (M12/D16)."""
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    bob = _make_user(db_session, "bob")
    carol = _make_user(db_session, "carol")
    contest = _make_contest(db_session, teacher, teams_enabled=True)
    for u in (alice, bob, carol):
        db_session.add(ContestParticipant(contest_id=contest.id, user_id=u.id))
    team = ContestTeam(contest_id=contest.id, name="Equipo A")
    db_session.add(team)
    db_session.flush()
    db_session.add(ContestTeamMember(team_id=team.id, user_id=alice.id))
    db_session.add(ContestTeamMember(team_id=team.id, user_id=bob.id))
    db_session.commit()
    problem = _make_problem(db_session, teacher)
    r_alice = _make_run(
        db_session, alice, problem, kind="contest", contest=contest
    )
    r_bob = _make_run(db_session, bob, problem, kind="contest", contest=contest)
    r_carol = _make_run(
        db_session, carol, problem, kind="contest", contest=contest
    )
    db_session.add(
        SimilarityPair(
            run_a_id=r_alice.id, run_b_id=r_bob.id, score=0.95, scope="contest"
        )
    )
    db_session.add(
        SimilarityPair(
            run_a_id=r_alice.id,
            run_b_id=r_carol.id,
            score=0.93,
            scope="contest",
        )
    )
    db_session.commit()

    token = _login(client, "prof")
    resp = client.get(
        f"/api/admin/anticheat?scope=contest&scope_id={contest.id}",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    pairs = resp.json()
    # Only the cross-team pair (alice/carol) survives; alice/bob share a
    # team and are excluded.
    assert len(pairs) == 1
    assert pairs[0]["user_a_id"] in (alice.id, carol.id)
    assert pairs[0]["user_b_id"] in (alice.id, carol.id)
    assert pairs[0]["score"] == 0.93


def test_contest_scope_other_teacher_403(client, db_session):
    """Teacher B cannot view Teacher A's contest."""
    teacher_a = _make_user(db_session, "profA", role="teacher")
    _make_user(db_session, "profB", role="teacher")
    contest = _make_contest(db_session, teacher_a)

    token_b = _login(client, "profB")
    resp = client.get(
        f"/api/admin/anticheat?scope=contest&scope_id={contest.id}",
        headers=_auth(token_b),
    )
    assert resp.status_code == 403


def test_anticheat_pair_404_for_missing_run(client, db_session):
    """Pair endpoint 404s if either run is missing."""
    teacher = _make_user(db_session, "prof", role="teacher")
    _make_class(db_session, teacher, code="C1")
    token = _login(client, "prof")
    resp = client.get(
        "/api/admin/anticheat/pair/9999/8888",
        headers=_auth(token),
    )
    assert resp.status_code == 404


def test_on_demand_compute_persists_pairs(client, db_session):
    """Empty similarity_pairs triggers on-demand compute; rows persist."""
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    bob = _make_user(db_session, "bob")
    cls = _make_class(db_session, teacher, code="C1")
    db_session.add(ClassMember(class_id=cls.id, user_id=alice.id))
    db_session.add(ClassMember(class_id=cls.id, user_id=bob.id))
    db_session.commit()
    problem = _make_problem(db_session, teacher)
    # Two renamed copies -> score 1.0; should appear above the 0.85 threshold.
    src_a = "Proceso A\n  Definir suma Como Entero\n  suma <- 0\nFinProceso\n"
    src_b = "Proceso B\n  Definir total Como Entero\n  total <- 0\nFinProceso\n"
    _make_run(db_session, alice, problem, source=src_a)
    _make_run(db_session, bob, problem, source=src_b)

    token = _login(client, "prof")
    resp = client.get(
        f"/api/admin/anticheat?scope=class&scope_id={cls.id}",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["score"] == 1.0

    # The pair must now be in the table.
    rows = db_session.scalars(select(SimilarityPair)).all()
    assert len(rows) == 1
    assert rows[0].scope == "class"
