"""Forum index API tests (forums tab).

Covers the ``GET /api/threads`` endpoint added for the forums landing page:
thread visibility per role (student sees class-membership + public problems,
teacher sees own-class + public, admin sees all), reply count + last activity
computed server-side, pagination, and the ``problem_id`` / ``class_id``
filters.

Runs against a dedicated ``pseint_test`` database on the same docker
Postgres (reusing the todo-18 fixture pattern).  This todo adds NO tables;
the existing migration is unchanged.
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
    ForumPost,
    ForumThread,
    Problem,
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


def _make_user(db, username="alice", role="student"):
    user = User(
        username=username,
        display_name=username.title(),
        password_hash="x",
        role=role,
    )
    db.add(user)
    db.commit()
    return user


def _make_class(db, teacher, code="C1", name="Intro"):
    cls = Class(name=name, code=code, teacher_id=teacher.id)
    db.add(cls)
    db.commit()
    return cls


def _make_problem(db, author, title="Suma"):
    problem = Problem(
        title=title,
        statement="Sumar dos números",
        expected_complexity="O(1)",
        compare_mode="exact",
        step_budget=None,
        author_id=author.id,
    )
    db.add(problem)
    db.commit()
    return problem


def _make_assignment(db, cls, problem):
    assignment = Assignment(
        class_id=cls.id,
        problem_id=problem.id,
        deadline=datetime.now(UTC) + timedelta(hours=1),
    )
    db.add(assignment)
    db.commit()
    return assignment


def _make_thread(db, problem, author, title="Duda"):
    thread = ForumThread(
        problem_id=problem.id, title=title, created_by=author.id
    )
    db.add(thread)
    db.commit()
    return thread


def _make_post(db, thread, author, body="respuesta", created_at=None):
    post = ForumPost(
        thread_id=thread.id,
        author_id=author.id,
        body=body,
        created_at=created_at or datetime.now(UTC),
    )
    db.add(post)
    db.commit()
    return post


def _login(client, username, password="x"):
    resp = client.post(
        "/api/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# --- Visibility per role ----------------------------------------------------


def test_student_sees_only_class_and_public_problem_threads(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    other = _make_user(db_session, "bob", role="teacher")

    cls = _make_class(db_session, teacher, code="C1")
    db_session.add(ClassMember(class_id=cls.id, user_id=alice.id))
    db_session.commit()

    visible = _make_problem(db_session, teacher, "Visible")
    hidden = _make_problem(db_session, other, "OtraClase")
    public = _make_problem(db_session, teacher, "Publico")

    _make_assignment(db_session, cls, visible)
    _make_assignment(db_session, _make_class(db_session, other, "C2"), hidden)

    # "Publico" has NO assignment -> no-class / public -> visible.
    t_visible = _make_thread(db_session, visible, teacher, "DelMio")
    _make_thread(db_session, hidden, other, "Ajeno")
    t_public = _make_thread(db_session, public, teacher, "Publico")

    token = _login(client, "alice")
    resp = client.get("/api/threads", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    titles = {t["title"] for t in body["items"]}
    assert titles == {"DelMio", "Publico"}
    assert t_visible.id in {t["id"] for t in body["items"]}
    assert t_public.id in {t["id"] for t in body["items"]}


def test_teacher_sees_own_class_problems(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    other = _make_user(db_session, "bob", role="teacher")

    cls = _make_class(db_session, teacher, "C1")
    other_cls = _make_class(db_session, other, "C2")

    mine = _make_problem(db_session, teacher, "Mio")
    theirs = _make_problem(db_session, other, "DeOtro")

    _make_assignment(db_session, cls, mine)
    _make_assignment(db_session, other_cls, theirs)

    _make_thread(db_session, mine, teacher, "EnMio")
    _make_thread(db_session, theirs, other, "EnOtro")

    token = _login(client, "prof")
    resp = client.get("/api/threads", headers=_auth(token))
    assert resp.status_code == 200
    titles = {t["title"] for t in resp.json()["items"]}
    assert titles == {"EnMio"}


def test_admin_sees_all_threads(client, db_session):
    admin = _make_user(db_session, "jefe", role="admin")
    teacher_a = _make_user(db_session, "profa", role="teacher")
    teacher_b = _make_user(db_session, "profb", role="teacher")

    cls_a = _make_class(db_session, teacher_a, "CA")
    cls_b = _make_class(db_session, teacher_b, "CB")
    pa = _make_problem(db_session, teacher_a, "A")
    pb = _make_problem(db_session, teacher_b, "B")
    _make_assignment(db_session, cls_a, pa)
    _make_assignment(db_session, cls_b, pb)
    _make_thread(db_session, pa, teacher_a, "TituloA")
    _make_thread(db_session, pb, teacher_b, "TituloB")

    # admin does not even need the class ids from membership to see everything.
    token = _login(client, "jefe")
    resp = client.get("/api/threads", headers=_auth(token))
    assert resp.status_code == 200
    titles = {t["title"] for t in resp.json()["items"]}
    assert titles == {"TituloA", "TituloB"}


# --- reply count + last activity --------------------------------------------


def test_reply_count_and_last_activity(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    problem = _make_problem(db_session, teacher, "Cuenta")
    cls = _make_class(db_session, teacher, "C1")
    db_session.add(ClassMember(class_id=cls.id, user_id=alice.id))
    db_session.commit()
    _make_assignment(db_session, cls, problem)

    thread = _make_thread(db_session, problem, teacher, "Hilo")
    # Opening post + 2 replies.
    _make_post(
        db_session, thread, teacher, "abre",
        created_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    _make_post(
        db_session, thread, alice, "r1",
        created_at=datetime.now(UTC) - timedelta(minutes=3),
    )
    last = _make_post(
        db_session, thread, alice, "r2",
        created_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    token = _login(client, "alice")
    resp = client.get("/api/threads", headers=_auth(token))
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["reply_count"] == 3
    assert item["problem_title"] == "Cuenta"
    assert item["author_username"] == "prof"
    got_last = datetime.fromisoformat(item["last_activity_at"].replace("Z", "+00:00"))
    assert got_last == _normalized(last.created_at)


def _normalized(dt: datetime) -> datetime:
    """Ensure tzinfo is UTC (Postgres round-trips the exact microseconds)."""
    return dt.astimezone(UTC)


# --- pagination + filters ---------------------------------------------------


def test_pagination(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    problem = _make_problem(db_session, teacher, "Pag")
    cls = _make_class(db_session, teacher, "C1")
    _make_assignment(db_session, cls, problem)
    for i in range(5):
        _make_thread(db_session, problem, teacher, f"Hilo{i + 1}")

    token = _login(client, "prof")
    resp = client.get(
        "/api/threads", params={"page": 1, "size": 2}, headers=_auth(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == 1
    assert body["size"] == 2
    assert body["total"] == 5
    assert len(body["items"]) == 2

    resp2 = client.get(
        "/api/threads", params={"page": 3, "size": 2}, headers=_auth(token)
    )
    assert len(resp2.json()["items"]) == 1


def test_filter_by_problem_id(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    cls = _make_class(db_session, teacher, "C1")
    pa = _make_problem(db_session, teacher, "A")
    pb = _make_problem(db_session, teacher, "B")
    _make_assignment(db_session, cls, pa)
    _make_assignment(db_session, cls, pb)
    _make_thread(db_session, pa, teacher, "SoloA")
    _make_thread(db_session, pb, teacher, "SoloB")

    token = _login(client, "prof")
    resp = client.get(
        "/api/threads", params={"problem_id": pa.id}, headers=_auth(token)
    )
    assert resp.status_code == 200
    assert [t["title"] for t in resp.json()["items"]] == ["SoloA"]


def test_filter_by_class_id(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    c1 = _make_class(db_session, teacher, "C1")
    c2 = _make_class(db_session, teacher, "C2")
    p1 = _make_problem(db_session, teacher, "P1")
    p2 = _make_problem(db_session, teacher, "P2")
    _make_assignment(db_session, c1, p1)
    _make_assignment(db_session, c2, p2)
    _make_thread(db_session, p1, teacher, "EnC1")
    _make_thread(db_session, p2, teacher, "EnC2")

    token = _login(client, "prof")
    resp = client.get(
        "/api/threads", params={"class_id": c1.id}, headers=_auth(token)
    )
    assert resp.status_code == 200
    assert [t["title"] for t in resp.json()["items"]] == ["EnC1"]


def test_requires_auth(client):
    resp = client.get("/api/threads")
    assert resp.status_code == 401


# --- nested replies (parent_id) ----------------------------------------------


def test_create_post_persists_parent_id(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    problem = _make_problem(db_session, teacher, "Anidado")
    thread = _make_thread(db_session, problem, teacher, "Hilo")
    root = _make_post(db_session, thread, teacher, "raiz")

    token = _login(client, "alice")
    resp = client.post(
        f"/api/threads/{thread.id}/posts",
        headers=_auth(token),
        json={"body": "respuesta anidada", "parent_id": root.id},
    )
    assert resp.status_code == 201
    assert resp.json()["parent_id"] == root.id
    assert resp.json()["body"] == "respuesta anidada"

    fetched = db_session.get(ForumPost, resp.json()["id"])
    assert fetched is not None
    assert fetched.parent_id == root.id


def test_create_post_without_parent_id_stores_null(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    problem = _make_problem(db_session, teacher, "SinPadre")
    thread = _make_thread(db_session, problem, teacher, "Hilo")

    token = _login(client, "alice")
    resp = client.post(
        f"/api/threads/{thread.id}/posts",
        headers=_auth(token),
        json={"body": "post nuevo de nivel superior"},
    )
    assert resp.status_code == 201
    assert resp.json()["parent_id"] is None


def test_list_posts_returns_threaded_structure(client, db_session):
    teacher = _make_user(db_session, "prof", role="teacher")
    alice = _make_user(db_session, "alice")
    problem = _make_problem(db_session, teacher, "Estructura")
    thread = _make_thread(db_session, problem, teacher, "Hilo")

    root = _make_post(db_session, thread, teacher, "abre")
    reply = _make_post(db_session, thread, alice, "responde")
    reply.parent_id = root.id
    db_session.commit()

    child = _make_post(db_session, thread, teacher, "a child")
    child.parent_id = reply.id
    db_session.commit()

    token = _login(client, "alice")
    resp = client.get(
        f"/api/threads/{thread.id}/posts", headers=_auth(token)
    )
    assert resp.status_code == 200
    posts = resp.json()
    by_id = {p["id"]: p for p in posts}
    assert by_id[root.id]["parent_id"] is None
    assert by_id[reply.id]["parent_id"] == root.id
    assert by_id[child.id]["parent_id"] == reply.id

    roots = [p for p in posts if p["parent_id"] is None]
    replies = [p for p in posts if p["parent_id"] is not None]
    assert len(roots) == 1
    assert len(replies) == 2
