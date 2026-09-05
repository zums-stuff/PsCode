"""Model tests for pseint-api (todo 16).

Runs against a dedicated ``pseint_test`` database on the same docker postgres
(the plan's acceptance DB is postgres — no SQLite anywhere).  The fixture
creates the test DB, runs the alembic migration to head, and drops the DB
after the session.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pseint_api.bootstrap import bootstrap_admin
from pseint_api.db import Base
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


@pytest.fixture()
def session(test_engine):
    """Fresh transaction per test (rollback after)."""
    with Session(test_engine) as s:
        yield s
        s.rollback()


def _make_user(
    session: Session, username: str = "alice", role: str = "student"
) -> User:
    user = User(
        username=username,
        display_name="Alice",
        password_hash="x",
        role=role,
    )
    session.add(user)
    session.flush()
    return user


def _make_class(session: Session, teacher: User, code: str = "C1") -> Class:
    cls = Class(name="Intro", code=code, teacher_id=teacher.id)
    session.add(cls)
    session.flush()
    return cls


def _make_problem(session: Session, author: User) -> Problem:
    problem = Problem(
        title="Suma",
        statement="Sumar dos números",
        expected_complexity="O(1)",
        compare_mode="exact",
        author_id=author.id,
    )
    session.add(problem)
    session.flush()
    return problem


# --- CRUD round-trips -------------------------------------------------------


def test_user_crud_roundtrip(session):
    user = _make_user(session)
    assert user.id is not None
    assert user.role == "student"

    fetched = session.get(User, user.id)
    assert fetched.username == "alice"
    assert fetched.display_name == "Alice"

    fetched.display_name = "Alicia"
    session.flush()
    assert session.get(User, user.id).display_name == "Alicia"

    session.delete(fetched)
    session.flush()
    assert session.get(User, user.id) is None


def test_class_crud_roundtrip(session):
    teacher = _make_user(session, username="teacher1", role="teacher")
    cls = _make_class(session, teacher)
    assert cls.id is not None
    assert cls.anticheat_threshold == 0.85

    fetched = session.get(Class, cls.id)
    assert fetched.code == "C1"
    assert fetched.teacher_id == teacher.id


def test_problem_crud_roundtrip(session):
    author = _make_user(session, username="author1", role="teacher")
    problem = _make_problem(session, author)
    assert problem.id is not None
    assert problem.expected_complexity == "O(1)"
    assert problem.compare_mode == "exact"
    assert problem.step_budget is None

    fetched = session.get(Problem, problem.id)
    assert fetched.title == "Suma"
    assert fetched.author_id == author.id


def test_test_case_crud_roundtrip(session):
    author = _make_user(session, username="author2", role="teacher")
    problem = _make_problem(session, author)
    tc = TestCase(
        problem_id=problem.id,
        input="1 2",
        expected_output="3",
        seed=0,
        points=1,
        order=0,
        is_public=False,
        is_sample=True,
    )
    session.add(tc)
    session.flush()

    fetched = session.get(TestCase, tc.id)
    assert fetched.input == "1 2"
    assert fetched.expected_output == "3"
    assert fetched.seed == 0
    assert fetched.points == 1
    assert fetched.is_public is False
    assert fetched.is_sample is True


def test_assignment_crud_roundtrip(session):
    teacher = _make_user(session, username="teacher2", role="teacher")
    cls = _make_class(session, teacher)
    problem = _make_problem(session, teacher)
    assignment = Assignment(
        class_id=cls.id,
        problem_id=problem.id,
        deadline=datetime.now(UTC) + timedelta(days=1),
    )
    session.add(assignment)
    session.flush()

    fetched = session.get(Assignment, assignment.id)
    assert fetched.class_id == cls.id
    assert fetched.problem_id == problem.id
    assert fetched.deadline is not None


def test_contest_crud_roundtrip(session):
    creator = _make_user(session, username="creator1", role="teacher")
    now = datetime.now(UTC)
    contest = Contest(
        title="CF Round",
        start_at=now,
        end_at=now + timedelta(hours=2),
        scoring_mode="cf",
        teams_enabled=False,
        created_by=creator.id,
    )
    session.add(contest)
    session.flush()

    fetched = session.get(Contest, contest.id)
    assert fetched.scoring_mode == "cf"
    assert fetched.teams_enabled is False
    assert fetched.start_at is not None
    assert fetched.end_at is not None


def test_run_crud_roundtrip(session):
    student = _make_user(session)
    author = _make_user(session, username="author3", role="teacher")
    problem = _make_problem(session, author)
    run = Run(
        user_id=student.id,
        problem_id=problem.id,
        kind="practice",
        status="queued",
        source="Proceso P\nFinProceso",
    )
    session.add(run)
    session.flush()

    fetched = session.get(Run, run.id)
    assert fetched.kind == "practice"
    assert fetched.status == "queued"
    assert fetched.summary_verdict is None
    assert fetched.steps is None
    assert fetched.wall_ms is None


def test_test_result_crud_roundtrip(session):
    student = _make_user(session)
    author = _make_user(session, username="author4", role="teacher")
    problem = _make_problem(session, author)
    run = Run(
        user_id=student.id,
        problem_id=problem.id,
        kind="practice",
        status="done",
        summary_verdict="AC",
        steps=10,
        wall_ms=5,
        source="Proceso P\nFinProceso",
    )
    session.add(run)
    session.flush()
    result = TestResult(
        run_id=run.id,
        case_index=0,
        verdict="AC",
        steps=10,
        wall_ms=5,
        output="3",
        error=None,
    )
    session.add(result)
    session.flush()

    fetched = session.get(TestResult, result.id)
    assert fetched.verdict == "AC"
    assert fetched.steps == 10
    assert fetched.wall_ms == 5
    assert fetched.output == "3"


def test_forum_thread_and_post_crud_roundtrip(session):
    author = _make_user(session, username="author5", role="teacher")
    problem = _make_problem(session, author)
    thread = ForumThread(
        problem_id=problem.id,
        contest_id=None,
        title="Duda",
        created_by=author.id,
        pinned=False,
    )
    session.add(thread)
    session.flush()
    post = ForumPost(
        thread_id=thread.id,
        parent_id=None,
        author_id=author.id,
        body="¿Cómo se suma?",
    )
    session.add(post)
    session.flush()

    fetched_thread = session.get(ForumThread, thread.id)
    assert fetched_thread.contest_id is None
    assert fetched_thread.pinned is False
    fetched_post = session.get(ForumPost, post.id)
    assert fetched_post.body == "¿Cómo se suma?"
    assert fetched_post.parent_id is None


def test_similarity_pair_crud_roundtrip(session):
    student = _make_user(session)
    author = _make_user(session, username="author6", role="teacher")
    problem = _make_problem(session, author)
    run_a = Run(
        user_id=student.id,
        problem_id=problem.id,
        kind="assignment",
        status="done",
        summary_verdict="AC",
        source="Proceso P\nFinProceso",
    )
    run_b = Run(
        user_id=student.id,
        problem_id=problem.id,
        kind="assignment",
        status="done",
        summary_verdict="WA",
        source="Proceso Q\nFinProceso",
    )
    session.add_all([run_a, run_b])
    session.flush()
    pair = SimilarityPair(
        run_a_id=run_a.id, run_b_id=run_b.id, score=0.9, scope="class"
    )
    session.add(pair)
    session.flush()

    fetched = session.get(SimilarityPair, pair.id)
    assert fetched.score == 0.9
    assert fetched.scope == "class"


def test_join_tables_roundtrip(session):
    teacher = _make_user(session, username="teacher3", role="teacher")
    student = _make_user(session, username="student1")
    cls = _make_class(session, teacher)
    session.add(ClassMember(class_id=cls.id, user_id=student.id))
    session.flush()

    now = datetime.now(UTC)
    contest = Contest(
        title="IOI Test",
        start_at=now,
        end_at=now + timedelta(hours=2),
        scoring_mode="ioi",
        teams_enabled=True,
        created_by=teacher.id,
    )
    session.add(contest)
    session.flush()
    session.add(ContestParticipant(contest_id=contest.id, user_id=student.id))
    problem = _make_problem(session, teacher)
    session.add(ContestProblem(contest_id=contest.id, problem_id=problem.id, order=0))
    team = ContestTeam(contest_id=contest.id, name="Equipo 1")
    session.add(team)
    session.flush()
    session.add(ContestTeamMember(team_id=team.id, user_id=student.id))
    session.flush()

    assert session.get(ClassMember, (cls.id, student.id)) is not None
    assert session.get(ContestParticipant, (contest.id, student.id)) is not None
    assert session.get(ContestProblem, (contest.id, problem.id)) is not None
    assert session.get(ContestTeamMember, (team.id, student.id)) is not None


# --- Unique constraints -----------------------------------------------------


def test_duplicate_class_code_raises_integrity_error(session):
    teacher = _make_user(session, username="teacher4", role="teacher")
    _make_class(session, teacher, code="DUP")
    with pytest.raises(IntegrityError):
        _make_class(session, teacher, code="DUP")


def test_duplicate_username_raises_integrity_error(session):
    _make_user(session, username="dupuser")
    with pytest.raises(IntegrityError):
        _make_user(session, username="dupuser")


# --- FK integrity -----------------------------------------------------------


def test_orphan_class_raises_integrity_error(session):
    with pytest.raises(IntegrityError):
        cls = Class(name="Orphan", code="ORPH", teacher_id=999999)
        session.add(cls)
        session.flush()


def test_orphan_problem_raises_integrity_error(session):
    with pytest.raises(IntegrityError):
        problem = Problem(
            title="Orphan",
            statement="x",
            expected_complexity="O(1)",
            compare_mode="exact",
            author_id=999999,
        )
        session.add(problem)
        session.flush()


# --- Bootstrap admin --------------------------------------------------------


def test_bootstrap_admin_creates_admin_row(monkeypatch, test_engine):
    monkeypatch.setenv("ADMIN_USERNAME", "root")
    monkeypatch.setenv("ADMIN_PASSWORD", "root-secret-123")
    with Session(test_engine) as s:
        created = bootstrap_admin(s)
        s.commit()
        assert created is not None
        assert created.role == "admin"

        row = s.scalar(select(User).where(User.username == "root"))
        assert row is not None
        assert row.role == "admin"
        assert row.password_hash != "root-secret-123"  # hashed, not plaintext


def test_bootstrap_admin_idempotent(monkeypatch, test_engine):
    monkeypatch.setenv("ADMIN_USERNAME", "root2")
    monkeypatch.setenv("ADMIN_PASSWORD", "root-secret-456")
    with Session(test_engine) as s:
        first = bootstrap_admin(s)
        s.commit()
        second = bootstrap_admin(s)
        s.commit()
        assert first is not None
        assert second is None  # already exists -> no-op

        count = len(s.scalars(select(User).where(User.username == "root2")).all())
        assert count == 1


def test_bootstrap_admin_noop_without_env(monkeypatch, test_engine):
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    with Session(test_engine) as s:
        assert bootstrap_admin(s) is None


def test_models_match_migration_tables(test_engine):
    """Every model table exists in the migrated DB (no drift)."""
    from sqlalchemy import inspect

    inspector = inspect(test_engine)
    db_tables = set(inspector.get_table_names())
    model_tables = set(Base.metadata.tables.keys())
    assert model_tables <= db_tables
    assert len(model_tables) == 16
