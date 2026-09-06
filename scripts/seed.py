"""Seed script for pseint-judge (plan todo 41).

Populates the LOCAL Postgres (compose stack or ``pseint`` db) with a deterministic
fixture that exercises every visible feature of the platform:

* **Users (22 total)**: 1 admin (``admin``/``admin``), 1 teacher
  (``profe``/``profe``), 20 students (``student01``-``student20`` / shared
  ``student123``).
* **Class (1)**: ``Class Alpha`` with join code ``ABC123``, teacher = profe,
  all 20 students enrolled.
* **Problems (4)**: ``HolaMundo`` (O(1), practice), ``Suma`` (O(1), assignment),
  ``Primo`` (O(n), assignment), ``Fibonacci`` (O(n), contest problem).
  Three or more test cases each, exactly one marked ``is_sample``.
* **Assignments (2)**: ``Suma`` and ``Primo`` attached to ``Class Alpha``.
* **Contest (1)**: ``CF Round 1 — Fibonacci Sprint`` in CF mode, running
  now, with ``Fibonacci`` attached and all 20 students registered as
  participants.
* **Planted runs** for the planted-band demo + the planted copy pair the
  anticheat report (todo 25/39) is designed to surface:
  - O(n) reference Fibonacci from ``student01``
  - O(n^2) planted Fibonacci from ``student03`` (lands in ALTA band)
  - O(2^n) planted Fibonacci from ``student04`` (lands in EXCESIVA band)
  - Two near-identical Fibonacci solutions from ``student01`` and
    ``student02`` with renamed identifiers (the planted copy pair the
    anticheat diff viewer demos).

Idempotent: if any users already exist, the script is a no-op (prints the
current counts and exits 0).  Run with ``python scripts/seed.py`` after
``pip install -e web/api engine judge`` (the api install registers
``pseint_api`` on the venv).  Defaults to the compose-stack Postgres
(``postgresql+psycopg://pseint:pseint@localhost:5432/pseint``); override
with ``DATABASE_URL=...``.

Plan acceptance (todo 41):
    pip install -e web/api && python scripts/seed.py   -> exit 0
    Final line printed: [22, 1, 4, 1]
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pseint_api import config
from pseint_api.auth import hash_password
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
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

DEMO_PASSWORD = {
    "admin": "admin",
    "profe": "profe",
    "_students": "student123",
}

# 4 problems: (title, statement, expected_complexity, step_budget, compare_mode)
PROBLEM_SPECS: list[tuple[str, str, str, int | None, str]] = [
    (
        "HolaMundo",
        "Lee una cadena y la imprime de vuelta (eco).",
        "O(1)",
        50,
        "exact",
    ),
    (
        "Suma",
        "Lee dos enteros a y b e imprime a + b.",
        "O(1)",
        50,
        "exact",
    ),
    (
        "Primo",
        "Lee un entero n e imprime 'ES PRIMO' o 'NO ES PRIMO'.",
        "O(n)",
        None,
        "exact",
    ),
    (
        "Fibonacci",
        "Lee un entero n (n >= 0) e imprime el n-esimo numero de Fibonacci (F(0)=0, F(1)=1).",
        "O(n)",
        None,
        "exact",
    ),
]

# Test cases per problem: (input, expected_output, is_sample).
TEST_CASES: dict[str, list[tuple[str, str, bool]]] = {
    "HolaMundo": [
        ("Hola", "Hola\n", True),
        ("Mundo", "Mundo\n", False),
        ("PseInt", "PseInt\n", False),
    ],
    "Suma": [
        ("1 2", "3\n", True),
        ("10 20", "30\n", False),
        ("-5 5", "0\n", False),
        ("100 200", "300\n", False),
    ],
    "Primo": [
        ("7", "ES PRIMO\n", True),
        ("10", "NO ES PRIMO\n", False),
        ("2", "ES PRIMO\n", False),
        ("1", "NO ES PRIMO\n", False),
    ],
    "Fibonacci": [
        ("5", "5\n", True),
        ("10", "55\n", False),
        ("15", "610\n", False),
        ("0", "0\n", False),
    ],
}

# Reference O(n) Fibonacci (authoritative solver for the contest).
FIBONACCI_REFERENCE = (
    "Proceso Fibonacci\n"
    "    Definir n, a, b, c, i: Entero\n"
    "    Leer n\n"
    "    Si n <= 1 Entonces\n"
    "        Escribir n\n"
    "    Sino\n"
    "        a <- 0\n"
    "        b <- 1\n"
    "        Para i <- 2 Hasta n\n"
    "            c <- a + b\n"
    "            a <- b\n"
    "            b <- c\n"
    "        FinPara\n"
    "        Escribir b\n"
    "    FinSi\n"
    "FinProceso\n"
)

# Planted O(n^2) Fibonacci — same algorithm with a redundant inner loop
# whose iteration count grows with fib_b.  Steps land in the ALTA band for
# n >= 5 because the actual work scales quadratically.
FIBONACCI_PLANTED_N2 = (
    "Proceso Fibonacci\n"
    "    Definir n, i, j, fib_a, fib_b, tmp: Entero\n"
    "    Leer n\n"
    "    Si n <= 1 Entonces\n"
    "        Escribir n\n"
    "    Sino\n"
    "        fib_a <- 0\n"
    "        fib_b <- 1\n"
    "        Para i <- 2 Hasta n\n"
    "            Para j <- 1 Hasta fib_b\n"
    "                tmp <- fib_a + fib_b\n"
    "            FinPara\n"
    "            tmp <- fib_a + fib_b\n"
    "            fib_a <- fib_b\n"
    "            fib_b <- tmp\n"
    "        FinPara\n"
    "        Escribir fib_b\n"
    "    FinSi\n"
    "FinProceso\n"
)

# Planted O(2^n) Fibonacci — an iterative algorithm that performs 2^n
# iterations of dummy work before computing the answer.  Steps land in the
# EXCESIVA band for n >= 3 because the planted program does thousands of
# steps while the expected formula at n_estimate=1 is just 32.
FIBONACCI_PLANTED_2N = (
    "Proceso Fibonacci\n"
    "    Definir n, i, j, total, fib, tmp: Entero\n"
    "    Leer n\n"
    "    total <- 1\n"
    "    Para i <- 1 Hasta n\n"
    "        total <- total * 2\n"
    "    FinPara\n"
    "    Para i <- 1 Hasta total\n"
    "        Para j <- 1 Hasta 3\n"
    "            tmp <- fib + i\n"
    "        FinPara\n"
    "    FinPara\n"
    "    fib <- 0\n"
    "    tmp <- 1\n"
    "    Si n <= 1 Entonces\n"
    "        Escribir n\n"
    "    Sino\n"
    "        Para i <- 2 Hasta n\n"
    "            Definir s: Entero\n"
    "            s <- fib + tmp\n"
    "            fib <- tmp\n"
    "            tmp <- s\n"
    "        FinPara\n"
    "        Escribir tmp\n"
    "    FinSi\n"
    "FinProceso\n"
)

# Planted copy pair: same O(n) iterative Fibonacci algorithm with renamed
# identifiers (a/b/c/i -> previo/actual/siguiente/contador).  The anticheat
# engine's ``fold`` step collapses identifiers, so these two normalize to
# the same string and score 1.0.
FIBONACCI_COPY_A = (
    "Proceso Fibonacci\n"
    "    Definir n, previo, actual, siguiente, contador: Entero\n"
    "    Leer n\n"
    "    Si n <= 1 Entonces\n"
    "        Escribir n\n"
    "    Sino\n"
    "        previo <- 0\n"
    "        actual <- 1\n"
    "        Para contador <- 2 Hasta n\n"
    "            siguiente <- previo + actual\n"
    "            previo <- actual\n"
    "            actual <- siguiente\n"
    "        FinPara\n"
    "        Escribir actual\n"
    "    FinSi\n"
    "FinProceso\n"
)

FIBONACCI_COPY_B = (
    "Proceso Fibonacci\n"
    "    Definir n, primero, segundo, acumulado, paso: Entero\n"
    "    Leer n\n"
    "    Si n <= 1 Entonces\n"
    "        Escribir n\n"
    "    Sino\n"
    "        primero <- 0\n"
    "        segundo <- 1\n"
    "        Para paso <- 2 Hasta n\n"
    "            acumulado <- primero + segundo\n"
    "            primero <- segundo\n"
    "            segundo <- acumulado\n"
    "        FinPara\n"
    "        Escribir segundo\n"
    "    FinSi\n"
    "FinProceso\n"
)


def _engine():
    """Create a fresh engine bound to the env DATABASE_URL.

    A local engine makes the script usable with a custom DATABASE_URL set
    after the api package was already imported (e.g. from tests).
    """
    return create_engine(config.database_url(), pool_pre_ping=True)


def _table_counts(session: Session) -> list[int]:
    """Count rows in the four tables the plan acceptance gate asserts on."""
    return [
        session.scalar(select(func.count()).select_from(User)) or 0,
        session.scalar(select(func.count()).select_from(ClassModel)) or 0,
        session.scalar(select(func.count()).select_from(Problem)) or 0,
        session.scalar(select(func.count()).select_from(Contest)) or 0,
    ]


def _make_users(session: Session) -> dict[str, User]:
    """Create admin, teacher, and 20 students.  Returns username -> User."""
    users: dict[str, User] = {}

    admin = User(
        username="admin",
        display_name="Administrator",
        password_hash=hash_password(DEMO_PASSWORD["admin"]),
        role="admin",
    )
    session.add(admin)
    users["admin"] = admin

    profe = User(
        username="profe",
        display_name="Profesora Demo",
        password_hash=hash_password(DEMO_PASSWORD["profe"]),
        role="teacher",
    )
    session.add(profe)
    users["profe"] = profe

    student_pw_hash = hash_password(DEMO_PASSWORD["_students"])
    for i in range(1, 21):
        username = f"student{i:02d}"
        user = User(
            username=username,
            display_name=f"Estudiante {i:02d}",
            password_hash=student_pw_hash,
            role="student",
        )
        session.add(user)
        users[username] = user

    session.flush()
    return users


def _make_class(session: Session, teacher: User) -> ClassModel:
    cls = ClassModel(
        name="Class Alpha",
        code="ABC123",
        teacher_id=teacher.id,
        anticheat_threshold=0.85,
    )
    session.add(cls)
    session.flush()
    return cls


def _enroll_students(
    session: Session, cls: ClassModel, students: list[User]
) -> None:
    for student in students:
        session.add(ClassMember(class_id=cls.id, user_id=student.id))
    session.flush()


def _make_problems(session: Session, author: User) -> dict[str, Problem]:
    problems: dict[str, Problem] = {}
    for title, statement, expected, step_budget, compare_mode in PROBLEM_SPECS:
        problem = Problem(
            title=title,
            statement=statement,
            expected_complexity=expected,
            step_budget=step_budget,
            compare_mode=compare_mode,
            author_id=author.id,
        )
        session.add(problem)
        session.flush()
        problems[title] = problem

        for order, (inp, expected_output, is_sample) in enumerate(
            TEST_CASES[title]
        ):
            test_case = TestCase(
                problem_id=problem.id,
                input=inp,
                expected_output=expected_output,
                seed=0,
                points=1,
                order=order,
                is_public=is_sample,
                is_sample=is_sample,
            )
            session.add(test_case)
        session.flush()
    return problems


def _make_assignments(
    session: Session, cls: ClassModel, problems: dict[str, Problem]
) -> list[Assignment]:
    deadline = datetime.now(UTC) + timedelta(days=14)
    assignments: list[Assignment] = []
    for title in ("Suma", "Primo"):
        a = Assignment(
            class_id=cls.id,
            problem_id=problems[title].id,
            deadline=deadline,
        )
        session.add(a)
        assignments.append(a)
    session.flush()
    return assignments


def _make_contest(
    session: Session,
    teacher: User,
    fib_problem: Problem,
    students: list[User],
) -> Contest:
    now = datetime.now(UTC)
    contest = Contest(
        title="CF Round 1 — Fibonacci Sprint",
        start_at=now - timedelta(hours=1),
        end_at=now + timedelta(hours=2),
        scoring_mode="cf",
        teams_enabled=False,
        created_by=teacher.id,
    )
    session.add(contest)
    session.flush()

    session.add(
        ContestProblem(contest_id=contest.id, problem_id=fib_problem.id, order=0)
    )

    for student in students:
        session.add(
            ContestParticipant(contest_id=contest.id, user_id=student.id)
        )
    session.flush()
    return contest


def _plant_runs(
    session: Session,
    fib_problem: Problem,
    contest: Contest,
    students: dict[str, User],
) -> list[Run]:
    """Insert the planted runs the anticheat + band demos rely on."""
    now = datetime.now(UTC)
    planted: list[Run] = []

    def _add(
        user_key: str,
        source: str,
        summary_verdict: str,
        steps: int,
    ) -> Run:
        run = Run(
            user_id=students[user_key].id,
            problem_id=fib_problem.id,
            kind="contest",
            status="done",
            summary_verdict=summary_verdict,
            steps=steps,
            wall_ms=steps * 2,
            source=source,
            stdin="10\n",
            contest_id=contest.id,
            created_at=now,
        )
        session.add(run)
        planted.append(run)
        return run

    # O(n) reference solution — student01, AC, ~66 steps for n=10.
    _add("student01", FIBONACCI_REFERENCE, "AC", 66)

    # O(n^2) planted — student03, AC output but band ALTA (excess work).
    _add("student03", FIBONACCI_PLANTED_N2, "AC", 436)

    # O(2^n) planted — student04, EXCESIVA band demo.  Marked AC because
    # the output is correct; the band is the signal, not the verdict.
    _add("student04", FIBONACCI_PLANTED_2N, "AC", 24699)

    # Planted copy pair — student01 + student02, identical algorithm with
    # renamed identifiers.  Anticheat normalizes these to the same string
    # and scores them 1.0.
    _add("student01", FIBONACCI_COPY_A, "AC", 66)
    _add("student02", FIBONACCI_COPY_B, "AC", 66)

    session.flush()
    return planted


def seed() -> list[int]:
    """Idempotent seed.  Returns [users, classes, problems, contests] counts
    after the run (whether it actually seeded or was a no-op)."""
    engine = _engine()
    try:
        with Session(engine) as session:
            existing = session.scalar(select(func.count()).select_from(User))
            if existing:
                counts = _table_counts(session)
                print(
                    f"seed: already seeded (users={counts[0]}); "
                    f"counts={counts}"
                )
                return counts

            users = _make_users(session)
            students = [users[f"student{i:02d}"] for i in range(1, 21)]

            cls = _make_class(session, teacher=users["profe"])
            _enroll_students(session, cls, students)

            problems = _make_problems(session, author=users["profe"])
            _make_assignments(session, cls, problems)

            contest = _make_contest(
                session,
                teacher=users["profe"],
                fib_problem=problems["Fibonacci"],
                students=students,
            )

            _plant_runs(
                session,
                fib_problem=problems["Fibonacci"],
                contest=contest,
                students=users,
            )

            session.commit()
            return _table_counts(session)
    finally:
        engine.dispose()


def main() -> int:
    counts = seed()
    print(f"seed: counts={counts}")
    print(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
