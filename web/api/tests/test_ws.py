"""WebSocket live-results tests for pseint-api (todo 19).

Covers the plan's acceptance list: handshake with/without token (4408 close
for missing/invalid/expired), replay-on-connect (M8: last 20 runs of the
user, per_case ordered by case_index), broadcast to the run owner, contest
observer (D12: teacher/admin or contest creator sees participant runs;
student observer -> 4408), and reconnect -> replay again.

Event design (documented choice): the worker emits ONE ``run`` event per run
after all per_case entries are filled; ``per_case`` is always ordered by
case_index.  Tests simulate worker events by calling
``broadcast_run_event`` directly through the TestClient portal (the app runs
in a separate event loop).

Runs against a dedicated ``pseint_test`` database on the same docker
postgres (reusing the test_models/test_auth fixture pattern).  This todo
adds NO tables, so the migration is unchanged and ``alembic check`` stays
clean.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from pseint_api import auth, config
from pseint_api.events import make_run_event, make_submission_event
from pseint_api.models import Contest, Problem, Run, TestResult, User
from pseint_api.ws import broadcast_run_event

TEST_DB_NAME = "pseint_test"
ADMIN_URL = "postgresql+psycopg://pseint:pseint@localhost:5432/postgres"

SOURCE = "Proceso P\n  Escribir 1\nFinProceso\n"


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
    """Direct session for seeding users/runs before WS calls."""
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


def _token(user_id: int, ttl_minutes: int = 60) -> str:
    return auth.create_access_token(user_id, config.secret_key(), ttl_minutes)


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


def _make_contest(db: Session, created_by: int, title: str = "CF Round 1") -> Contest:
    contest = Contest(
        title=title,
        start_at=datetime.now(UTC) - timedelta(hours=1),
        end_at=datetime.now(UTC) + timedelta(hours=2),
        scoring_mode="cf",
        teams_enabled=False,
        created_by=created_by,
    )
    db.add(contest)
    db.commit()
    return contest


def _make_run(
    db: Session,
    user_id: int,
    problem_id: int,
    contest_id: int | None = None,
    status: str = "done",
    created_at: datetime | None = None,
) -> Run:
    run = Run(
        user_id=user_id,
        problem_id=problem_id,
        kind="contest" if contest_id is not None else "practice",
        status=status,
        source=SOURCE,
        contest_id=contest_id,
        created_at=created_at,
    )
    db.add(run)
    db.commit()
    return run


# --- Handshake --------------------------------------------------------------


def test_handshake_without_token_4408(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/submissions"):
            pass
    assert exc.value.code == 4408


def test_handshake_invalid_token_4408(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/submissions?token=not-a-jwt"):
            pass
    assert exc.value.code == 4408


def test_handshake_expired_token_4408(client, db_session):
    user = _make_user(db_session)
    token = _token(user.id, ttl_minutes=-1)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws/submissions?token={token}"):
            pass
    assert exc.value.code == 4408


def test_handshake_valid_token_connects_empty_replay(client, db_session):
    user = _make_user(db_session)
    token = _token(user.id)
    # Entering the context means the handshake succeeded; no runs -> no events.
    with client.websocket_connect(f"/ws/submissions?token={token}"):
        pass


# --- Replay on connect (M8) -------------------------------------------------


def test_replay_last_20_runs_ordered_by_created_at(client, db_session):
    user = _make_user(db_session)
    problem = _make_problem(db_session, author_id=user.id)
    base = datetime.now(UTC)
    runs = []
    for i in range(25):
        runs.append(
            _make_run(
                db_session,
                user_id=user.id,
                problem_id=problem.id,
                created_at=base - timedelta(minutes=i),
            )
        )
    # Out-of-order TestResult rows on the most recent run: replay must sort
    # per_case by case_index (event design: one event per run, cases sorted).
    db_session.add_all(
        [
            TestResult(
                run_id=runs[0].id, case_index=2, verdict="WA", steps=3, wall_ms=1
            ),
            TestResult(
                run_id=runs[0].id, case_index=0, verdict="AC", steps=5, wall_ms=2
            ),
            TestResult(
                run_id=runs[0].id, case_index=1, verdict="AC", steps=4, wall_ms=1
            ),
        ]
    )
    db_session.commit()

    token = _token(user.id)
    with client.websocket_connect(f"/ws/submissions?token={token}") as ws:
        received = [ws.receive_json() for _ in range(20)]

    assert [e["run_id"] for e in received] == [runs[i].id for i in range(20)]
    assert [e["type"] for e in received] == ["run"] * 20
    assert [e["status"] for e in received] == ["done"] * 20
    first = received[0]
    assert [c["case_index"] for c in first["per_case"]] == [0, 1, 2]
    assert first["per_case"][0] == {
        "case_index": 0,
        "verdict": "AC",
        "steps": 5,
        "wall_ms": 2,
    }


def test_reconnect_replays_runs_again(client, db_session):
    user = _make_user(db_session)
    problem = _make_problem(db_session, author_id=user.id)
    run = _make_run(db_session, user_id=user.id, problem_id=problem.id)
    token = _token(user.id)

    with client.websocket_connect(f"/ws/submissions?token={token}") as ws:
        assert ws.receive_json()["run_id"] == run.id
    with client.websocket_connect(f"/ws/submissions?token={token}") as ws:
        assert ws.receive_json()["run_id"] == run.id


# --- Live broadcast to owner -------------------------------------------------


def test_broadcast_run_event_delivers_to_owner(client, db_session):
    user = _make_user(db_session)
    token = _token(user.id)
    event = make_run_event(
        1,
        "done",
        per_case=[{"case_index": 0, "verdict": "AC", "steps": 10, "wall_ms": 5}],
    )
    with client.websocket_connect(f"/ws/submissions?token={token}") as ws:
        client.portal.call(broadcast_run_event, 1, user.id, event)
        assert ws.receive_json() == event


def test_broadcast_does_not_multicast_to_other_users(client, db_session):
    owner = _make_user(db_session, username="owner")
    other = _make_user(db_session, username="other")
    token = _token(other.id)
    with client.websocket_connect(f"/ws/submissions?token={token}") as ws:
        client.portal.call(
            broadcast_run_event, 1, owner.id, make_run_event(1, "done")
        )
        # No message must arrive for the other user's run; a second broadcast
        # to the connected user proves the first one was skipped.
        client.portal.call(
            broadcast_run_event, 2, other.id, make_run_event(2, "done")
        )
        assert ws.receive_json()["run_id"] == 2


# --- Contest observer (D12) --------------------------------------------------


def test_contest_observer_teacher_sees_participant_runs(client, db_session):
    teacher = _make_user(db_session, username="prof", role="teacher")
    student = _make_user(db_session, username="stu")
    contest = _make_contest(db_session, created_by=teacher.id)
    problem = _make_problem(db_session, author_id=teacher.id)
    run = _make_run(
        db_session,
        user_id=student.id,
        problem_id=problem.id,
        contest_id=contest.id,
    )
    # A practice run (no contest) must NOT reach the observer.
    other_run = _make_run(
        db_session, user_id=student.id, problem_id=problem.id
    )
    token = _token(teacher.id)
    event = make_run_event(
        run.id,
        "done",
        per_case=[{"case_index": 0, "verdict": "AC", "steps": 4, "wall_ms": 2}],
    )
    with client.websocket_connect(
        f"/ws/submissions?token={token}&contest_id={contest.id}"
    ) as ws:
        client.portal.call(
            broadcast_run_event, other_run.id, student.id,
            make_run_event(other_run.id, "done"),
        )
        client.portal.call(
            broadcast_run_event, run.id, student.id, event, contest.id
        )
        received = ws.receive_json()
    assert received == event


def test_contest_observer_limited_to_own_contest(client, db_session):
    teacher = _make_user(db_session, username="prof", role="teacher")
    student = _make_user(db_session, username="stu")
    contest_a = _make_contest(db_session, created_by=teacher.id, title="A")
    contest_b = _make_contest(db_session, created_by=teacher.id, title="B")
    problem = _make_problem(db_session, author_id=teacher.id)
    run_b = _make_run(
        db_session,
        user_id=student.id,
        problem_id=problem.id,
        contest_id=contest_b.id,
    )
    run_a = _make_run(
        db_session,
        user_id=student.id,
        problem_id=problem.id,
        contest_id=contest_a.id,
    )
    token = _token(teacher.id)
    with client.websocket_connect(
        f"/ws/submissions?token={token}&contest_id={contest_a.id}"
    ) as ws:
        client.portal.call(
            broadcast_run_event, run_b.id, student.id,
            make_run_event(run_b.id, "done"), contest_b.id,
        )
        client.portal.call(
            broadcast_run_event, run_a.id, student.id,
            make_run_event(run_a.id, "done"), contest_a.id,
        )
        assert ws.receive_json()["run_id"] == run_a.id


def test_contest_observer_student_4408(client, db_session):
    teacher = _make_user(db_session, username="prof", role="teacher")
    student = _make_user(db_session, username="stu")
    contest = _make_contest(db_session, created_by=teacher.id)
    token = _token(student.id)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(
            f"/ws/submissions?token={token}&contest_id={contest.id}"
        ):
            pass
    assert exc.value.code == 4408


def test_contest_observer_unknown_contest_4408(client, db_session):
    teacher = _make_user(db_session, username="prof", role="teacher")
    token = _token(teacher.id)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(
            f"/ws/submissions?token={token}&contest_id=999"
        ):
            pass
    assert exc.value.code == 4408


# --- Event payload helpers ---------------------------------------------------


def test_run_event_shape():
    ev = make_run_event(
        7,
        "done",
        per_case=[{"case_index": 0, "verdict": "AC", "steps": 1, "wall_ms": 2}],
    )
    assert ev == {
        "type": "run",
        "run_id": 7,
        "status": "done",
        "per_case": [{"case_index": 0, "verdict": "AC", "steps": 1, "wall_ms": 2}],
    }


def test_submission_event_shape():
    assert make_submission_event(7) == {
        "type": "submission",
        "run_id": 7,
        "status": "queued",
        "per_case": [],
    }
