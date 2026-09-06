"""Tests for scripts/seed.py (todo 41).

The seed is the on-ramp fixture for the LOCAL stack: every Playwright
journey (todo 42) and the load test (todo 37) start from this seeded state.
The tests pin three invariants:

1. **Idempotency** — calling ``seed.seed()`` twice produces the same
   row counts the second time.  No duplicate rows, no extra contests.
2. **Count assertion** — the [users, classes, problems, contests] tuple
   matches the plan's gate: ``[22, 1, 4, 1]``.  This is the line that
   the acceptance command (``python scripts/seed.py``) prints.
3. **Planted copy pair normalizes to the same string** — the anticheat
   engine relies on identifier folding; a seed change that breaks the
   pair's normalize-equality silently breaks the todo-25/39 demos.

Runs against a dedicated ``pseint_test_seed`` database on the same docker
Postgres (reusing the test_auth.py / test_similarity_api.py fixture
pattern).  The seed import adds no new tables — only rows.

The fixture bootstraps a fresh DB per test module: seed is idempotent
across calls within a single session, but the second call needs the
same DB the first call wrote to.  Module-scoped fixtures keep the
seeding cost low.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from pseint_api.models import (
    Assignment,
    ClassMember,
    Contest,
    ContestParticipant,
    ContestProblem,
    Problem,
    Run,
    TestCase,
    User,
)
from pseint_api.models import (
    Class as ClassModel,
)
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

TEST_DB_NAME = "pseint_test_seed"
ADMIN_URL = "postgresql+psycopg://pseint:pseint@localhost:5432/postgres"
EXPECTED_COUNTS = [22, 1, 4, 1]

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_PATH = REPO_ROOT / "scripts"
SEED_PATH = SCRIPTS_PATH / "seed.py"


def _admin_engine():
    return create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")


def _drop_test_db() -> None:
    with _admin_engine().connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)"))


def _load_seed_module():
    """Load scripts/seed.py as an importable module.

    scripts/ has no ``__init__.py``; load the file by path and register it
    in ``sys.modules`` so relative imports inside seed.py resolve.
    """
    spec = importlib.util.spec_from_file_location("pseint_seed", SEED_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["pseint_seed"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def test_engine():
    """Create a fresh DB on the local docker Postgres and migrate to head.

    ``DATABASE_URL`` is set for the duration of the fixture so the seed
    module's ``config.database_url()`` reads the test DB URL (the seed
    runs after this fixture's migrations complete).
    """
    _drop_test_db()
    with _admin_engine().connect() as conn:
        conn.execute(text(f"CREATE DATABASE {TEST_DB_NAME}"))

    from alembic import command
    from alembic.config import Config

    url = f"postgresql+psycopg://pseint:pseint@localhost:5432/{TEST_DB_NAME}"
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("DATABASE_URL", url)
    try:
        command.upgrade(
            Config(str(REPO_ROOT / "web" / "api" / "alembic.ini")), "head"
        )
    finally:
        monkeypatch.undo()

    engine = create_engine(url)
    yield engine
    engine.dispose()
    _drop_test_db()


@pytest.fixture(scope="module")
def seeded_engine(test_engine):
    """Run the seed against the test DB and yield the engine.

    ``DATABASE_URL`` is set BEFORE ``_load_seed_module()`` runs so the
    seed's ``config.database_url()`` call inside ``_engine()`` picks up
    the test URL.
    """
    url = (
        f"postgresql+psycopg://pseint:pseint@localhost:5432/{TEST_DB_NAME}"
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("DATABASE_URL", url)
    try:
        module = _load_seed_module()
        counts = module.seed()
    finally:
        monkeypatch.undo()

    assert counts == EXPECTED_COUNTS, (
        f"first seed() call must produce {EXPECTED_COUNTS}, got {counts}"
    )

    yield test_engine


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


def test_first_seed_produces_expected_counts(seeded_engine) -> None:
    """The first ``seed()`` call must populate exactly [22, 1, 4, 1]."""
    with Session(seeded_engine) as s:
        counts = [
            s.scalar(select(func.count()).select_from(User)) or 0,
            s.scalar(select(func.count()).select_from(ClassModel)) or 0,
            s.scalar(select(func.count()).select_from(Problem)) or 0,
            s.scalar(select(func.count()).select_from(Contest)) or 0,
        ]
    assert counts == EXPECTED_COUNTS, (
        f"plan acceptance gate failed: expected {EXPECTED_COUNTS}, got {counts}"
    )


def test_seed_is_idempotent(seeded_engine) -> None:
    """A second ``seed()`` call MUST be a no-op (counts unchanged)."""
    url = (
        f"postgresql+psycopg://pseint:pseint@localhost:5432/{TEST_DB_NAME}"
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("DATABASE_URL", url)
    try:
        module = _load_seed_module()
        counts2 = module.seed()
    finally:
        monkeypatch.undo()

    assert counts2 == EXPECTED_COUNTS, (
        f"second seed() call must keep counts at {EXPECTED_COUNTS}, got {counts2}"
    )

    with Session(seeded_engine) as s:
        users = s.scalar(select(func.count()).select_from(User))
        classes = s.scalar(select(func.count()).select_from(ClassModel))
        problems = s.scalar(select(func.count()).select_from(Problem))
        contests = s.scalar(select(func.count()).select_from(Contest))
    assert users == EXPECTED_COUNTS[0]
    assert classes == EXPECTED_COUNTS[1]
    assert problems == EXPECTED_COUNTS[2]
    assert contests == EXPECTED_COUNTS[3]


def test_users_have_expected_roles(seeded_engine) -> None:
    """1 admin + 1 teacher + 20 students = 22 total users."""
    with Session(seeded_engine) as s:
        admins = s.scalar(
            select(func.count()).select_from(User).where(User.role == "admin")
        )
        teachers = s.scalar(
            select(func.count()).select_from(User).where(User.role == "teacher")
        )
        students = s.scalar(
            select(func.count()).select_from(User).where(User.role == "student")
        )
    assert admins == 1, "seed must create exactly one admin user"
    assert teachers == 1, "seed must create exactly one teacher user"
    assert students == 20, "seed must create exactly 20 student users"


def test_class_enrolls_all_students(seeded_engine) -> None:
    """Class Alpha with code ABC123 has 20 enrolled members."""
    with Session(seeded_engine) as s:
        cls = s.scalar(
            select(ClassModel).where(ClassModel.code == "ABC123")
        )
        assert cls is not None, "seed must create class with code ABC123"
        assert cls.name == "Class Alpha"

        enrolled = s.scalar(
            select(func.count()).select_from(ClassMember).where(
                ClassMember.class_id == cls.id
            )
        )
    assert enrolled == 20, (
        "all 20 students must be enrolled in Class Alpha"
    )


def test_four_problems_with_three_or_more_cases_each(seeded_engine) -> None:
    """Each of the 4 problems has at least 3 test cases, exactly one sample."""
    with Session(seeded_engine) as s:
        problems = s.scalars(select(Problem)).all()
        assert len(problems) == 4
        titles = {p.title for p in problems}
        assert titles == {"HolaMundo", "Suma", "Primo", "Fibonacci"}

        for problem in problems:
            cases = s.scalars(
                select(TestCase).where(TestCase.problem_id == problem.id)
            ).all()
            assert len(cases) >= 3, (
                f"problem {problem.title} has only {len(cases)} test cases; "
                f"the brief requires at least 3"
            )
            sample_count = sum(1 for c in cases if c.is_sample)
            assert sample_count == 1, (
                f"problem {problem.title} must have exactly one sample case "
                f"(found {sample_count})"
            )


def test_assignments_attach_suma_and_primo(seeded_engine) -> None:
    """Suma and Primo are tied to the class via Assignment rows."""
    with Session(seeded_engine) as s:
        cls = s.scalar(
            select(ClassModel).where(ClassModel.code == "ABC123")
        )
        assignments = s.scalars(
            select(Assignment).where(Assignment.class_id == cls.id)
        ).all()
        problem_titles = {
            s.get(Problem, a.problem_id).title for a in assignments
        }
    assert problem_titles == {"Suma", "Primo"}, (
        f"class Alpha must have assignments for Suma and Primo; got {problem_titles}"
    )


def test_contest_has_fibonacci_and_all_students(seeded_engine) -> None:
    """The single contest is CF-mode, has Fibonacci, and 20 participants."""
    with Session(seeded_engine) as s:
        contests = s.scalars(select(Contest)).all()
        assert len(contests) == 1
        contest = contests[0]
        assert contest.scoring_mode == "cf"

        cp = s.scalars(
            select(ContestProblem).where(ContestProblem.contest_id == contest.id)
        ).all()
        assert len(cp) == 1
        assert s.get(Problem, cp[0].problem_id).title == "Fibonacci"

        participants = s.scalar(
            select(func.count())
            .select_from(ContestParticipant)
            .where(ContestParticipant.contest_id == contest.id)
        )
    assert participants == 20, (
        f"all 20 students must be participants in the contest; got {participants}"
    )


def test_planted_runs_exist(seeded_engine) -> None:
    """5 planted runs: 1 reference + 2 planted bands + 2 planted copy pair."""
    with Session(seeded_engine) as s:
        runs = s.scalars(select(Run)).all()
    assert len(runs) == 5, f"expected 5 planted runs, found {len(runs)}"


def test_planted_copy_pair_normalizes_identically() -> None:
    """The planted pair must collapse to the same normalized string.

    Without this, the anticheat demo silently fails — the pair scores
    below 0.85 and the report returns nothing.
    """
    from pseint_judge.similarity import normalize

    sys.path.insert(0, str(SCRIPTS_PATH))
    if "pseint_seed" in sys.modules:
        seed_mod = sys.modules["pseint_seed"]
    else:
        seed_mod = _load_seed_module()

    assert normalize(seed_mod.FIBONACCI_COPY_A) == normalize(seed_mod.FIBONACCI_COPY_B), (
        "planted copy pair must normalize to the same string for the "
        "anticheat report to surface it"
    )


def test_demo_passwords_authenticate(seeded_engine) -> None:
    """admin/admin, profe/profe, student01/student123 all log in successfully.

    ``pseint_api.auth.verify_password`` accepts argon2 hashes via pwdlib
    (the same library the seed uses).  Spinning the verify path proves
    the password-hashing seam is wired end-to-end.
    """
    from pseint_api.auth import verify_password

    with Session(seeded_engine) as s:
        admin = s.scalar(select(User).where(User.username == "admin"))
        profe = s.scalar(select(User).where(User.username == "profe"))
        student = s.scalar(select(User).where(User.username == "student01"))

    assert verify_password("admin", admin.password_hash)
    assert verify_password("profe", profe.password_hash)
    assert verify_password("student123", student.password_hash)
