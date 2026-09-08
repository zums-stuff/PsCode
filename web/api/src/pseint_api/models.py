"""SQLAlchemy 2.x ORM models for pseint-api (todo 16).

All 15 tables from Scope C5 + M12 additions.  Column choices follow the plan
(todo 16) and the SPEC (complexity enum, verdict taxonomy, compare modes).

Tables:
  users, classes, class_members, problems, test_cases, assignments,
  contests, contest_problems, contest_participants, contest_teams,
  contest_team_members, runs, test_results, forum_threads, forum_posts,
  similarity_pairs
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# --- Enums (SPEC §(k) + verdict taxonomy + compare modes) -------------------

# Superscript forms MUST match judge complexity.py + SPEC §(k) — the judge
# compares these exact strings, so a mismatch breaks grading.
COMPLEXITY_VALUES = [
    "O(1)",
    "O(log n)",
    "O(n)",
    "O(n log n)",
    "O(n²)",
    "O(n³)",
    "O(2ⁿ)",
    "other",
]

VERDICT_VALUES = ["AC", "WA", "TLE", "RE", "CE"]

COMPARE_MODE_VALUES = ["exact", "token"]

ROLE_VALUES = ["admin", "teacher", "student"]

RUN_KIND_VALUES = ["practice", "assignment", "contest"]

RUN_STATUS_VALUES = ["queued", "running", "done", "failed"]

SCORING_MODE_VALUES = ["cf", "ioi"]

SIMILARITY_SCOPE_VALUES = ["class", "contest", "problem"]


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        Enum(*ROLE_VALUES, name="user_role"), nullable=False, default="student"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Class(Base):
    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    anticheat_threshold: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.85
    )

    teacher: Mapped[User] = relationship()


class ClassMember(Base):
    __tablename__ = "class_members"

    class_id: Mapped[int] = mapped_column(
        ForeignKey("classes.id"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), primary_key=True
    )


class Problem(Base):
    __tablename__ = "problems"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    expected_complexity: Mapped[str] = mapped_column(
        Enum(*COMPLEXITY_VALUES, name="complexity"), nullable=False
    )
    step_budget: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compare_mode: Mapped[str] = mapped_column(
        Enum(*COMPARE_MODE_VALUES, name="compare_mode"),
        nullable=False,
        default="exact",
    )
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    author: Mapped[User] = relationship()


class TestCase(Base):
    __tablename__ = "test_cases"
    __test__ = False  # pytest: model class, not a test class

    id: Mapped[int] = mapped_column(primary_key=True)
    problem_id: Mapped[int] = mapped_column(
        ForeignKey("problems.id"), nullable=False
    )
    input: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expected_output: Mapped[str] = mapped_column(Text, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_sample: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    problem: Mapped[Problem] = relationship()


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(
        ForeignKey("classes.id"), nullable=False
    )
    problem_id: Mapped[int] = mapped_column(
        ForeignKey("problems.id"), nullable=False
    )
    deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Contest(Base):
    __tablename__ = "contests"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    scoring_mode: Mapped[str] = mapped_column(
        Enum(*SCORING_MODE_VALUES, name="scoring_mode"),
        nullable=False,
        default="cf",
    )
    teams_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )


class ContestProblem(Base):
    __tablename__ = "contest_problems"

    contest_id: Mapped[int] = mapped_column(
        ForeignKey("contests.id"), primary_key=True
    )
    problem_id: Mapped[int] = mapped_column(
        ForeignKey("problems.id"), primary_key=True
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ContestParticipant(Base):
    __tablename__ = "contest_participants"

    contest_id: Mapped[int] = mapped_column(
        ForeignKey("contests.id"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), primary_key=True
    )


class ContestTeam(Base):
    __tablename__ = "contest_teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    contest_id: Mapped[int] = mapped_column(
        ForeignKey("contests.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ContestTeamMember(Base):
    __tablename__ = "contest_team_members"

    team_id: Mapped[int] = mapped_column(
        ForeignKey("contest_teams.id"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), primary_key=True
    )


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    problem_id: Mapped[int | None] = mapped_column(
        ForeignKey("problems.id"), nullable=True
    )
    kind: Mapped[str] = mapped_column(
        Enum(*RUN_KIND_VALUES, name="run_kind"),
        nullable=False,
        default="practice",
    )
    status: Mapped[str] = mapped_column(
        Enum(*RUN_STATUS_VALUES, name="run_status"),
        nullable=False,
        default="queued",
    )
    summary_verdict: Mapped[str | None] = mapped_column(
        Enum(*VERDICT_VALUES, name="verdict"), nullable=True
    )
    steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wall_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    stdin: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignment_id: Mapped[int | None] = mapped_column(
        ForeignKey("assignments.id"), nullable=True
    )
    contest_id: Mapped[int | None] = mapped_column(
        ForeignKey("contests.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TestResult(Base):
    __tablename__ = "test_results"
    __test__ = False  # pytest: model class, not a test class

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("runs.id"), nullable=False
    )
    case_index: Mapped[int] = mapped_column(Integer, nullable=False)
    verdict: Mapped[str] = mapped_column(
        Enum(*VERDICT_VALUES, name="verdict"), nullable=False
    )
    steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wall_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[Run] = relationship()


class ForumThread(Base):
    __tablename__ = "forum_threads"

    id: Mapped[int] = mapped_column(primary_key=True)
    problem_id: Mapped[int] = mapped_column(
        ForeignKey("problems.id"), nullable=False
    )
    contest_id: Mapped[int | None] = mapped_column(
        ForeignKey("contests.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ForumPost(Base):
    __tablename__ = "forum_posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[int] = mapped_column(
        ForeignKey("forum_threads.id"), nullable=False
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("forum_posts.id"), nullable=True
    )
    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SimilarityPair(Base):
    __tablename__ = "similarity_pairs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_a_id: Mapped[int] = mapped_column(
        ForeignKey("runs.id"), nullable=False
    )
    run_b_id: Mapped[int] = mapped_column(
        ForeignKey("runs.id"), nullable=False
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    scope: Mapped[str] = mapped_column(
        Enum(*SIMILARITY_SCOPE_VALUES, name="similarity_scope"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
