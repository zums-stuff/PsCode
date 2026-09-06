"""Listing endpoints for pseint-api (todo 21).

Paginated problemset / assignments / contests lists with per-user state:

- ``GET /api/problems`` — ``{id, title, expected_complexity, compare_mode,
  is_solved, best_verdict}``; ``is_solved`` = any AC run by the user,
  ``best_verdict`` = highest-priority verdict among the user's runs
  (AC > WA > TLE > RE > CE), null when the user has no runs.
- ``GET /api/assignments`` — ``{id, problem_id, deadline, status,
  best_verdict, best_steps}`` for the classes the user belongs to (admin:
  all, teacher: own classes, student: ClassMember); ``status`` = open when
  ``now < deadline`` else closed; best result from the user's runs on that
  assignment (best verdict, fewest steps as tiebreak).
- ``GET /api/contests`` — ``{id, title, start_at, end_at, status,
  scoring_mode, teams_enabled, is_registered}``; ``status`` =
  upcoming/running/ended from start/end; ``is_registered`` = direct
  ContestParticipant OR member of any team in the contest.

All lists share the ``{items, page, size, total}`` envelope with
``page >= 1`` and ``1 <= size <= 100`` (422 otherwise); a page beyond the
range returns an empty ``items`` list with 200, never 500.

N+1 avoidance: per-user state is computed from ONE aggregate query per list
(verdicts grouped in Python), never a per-row lookup.  The response items
only reference columns, so no relationship is lazy-loaded at all — the
``assignment.class``/``assignment.problem`` objects the plan mentions are
not part of the response shape and are never touched.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Generic, TypeVar

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db
from ..models import (
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

router = APIRouter(prefix="/api")

# Verdict priority for "best" (highest wins): AC > WA > TLE > RE > CE.
VERDICT_PRIORITY = {"AC": 4, "WA": 3, "TLE": 2, "RE": 1, "CE": 0}

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    size: int
    total: int


class ProblemListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    expected_complexity: str
    compare_mode: str
    is_solved: bool
    best_verdict: str | None


class AssignmentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    problem_id: int
    deadline: datetime
    status: str
    best_verdict: str | None
    best_steps: int | None


class ContestListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    start_at: datetime
    end_at: datetime
    status: str
    scoring_mode: str
    teams_enabled: bool
    is_registered: bool


def _best_verdict(verdicts: set[str]) -> str | None:
    """Highest-priority verdict present, or None for an empty set."""
    if not verdicts:
        return None
    return max(verdicts, key=lambda v: VERDICT_PRIORITY[v])


def _visible_class_ids(db: Session, user: User) -> list[int]:
    """Class ids whose assignments the user may see (admin: all)."""
    if user.role == "admin":
        return db.scalars(select(Class.id)).all()
    if user.role == "teacher":
        return db.scalars(
            select(Class.id).where(Class.teacher_id == user.id)
        ).all()
    return db.scalars(
        select(ClassMember.class_id).where(ClassMember.user_id == user.id)
    ).all()


def _contest_status(contest: Contest, now: datetime) -> str:
    if now < contest.start_at:
        return "upcoming"
    if now <= contest.end_at:
        return "running"
    return "ended"


@router.get("/problems", response_model=Page[ProblemListItem])
def list_problems(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    total = db.scalar(select(func.count(Problem.id))) or 0
    problems = db.scalars(
        select(Problem)
        .order_by(Problem.id)
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    # One aggregate query for the user's verdicts across ALL problems.
    rows = db.execute(
        select(Run.problem_id, Run.summary_verdict).where(
            Run.user_id == user.id, Run.summary_verdict.is_not(None)
        )
    ).all()
    verdicts_by_problem: dict[int, set[str]] = {}
    for problem_id, verdict in rows:
        verdicts_by_problem.setdefault(problem_id, set()).add(verdict)
    items = [
        ProblemListItem(
            id=p.id,
            title=p.title,
            expected_complexity=p.expected_complexity,
            compare_mode=p.compare_mode,
            is_solved="AC" in verdicts_by_problem.get(p.id, set()),
            best_verdict=_best_verdict(verdicts_by_problem.get(p.id, set())),
        )
        for p in problems
    ]
    return Page(items=items, page=page, size=size, total=total)


@router.get("/assignments", response_model=Page[AssignmentListItem])
def list_assignments(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    class_ids = _visible_class_ids(db, user)
    total = (
        db.scalar(
            select(func.count(Assignment.id)).where(
                Assignment.class_id.in_(class_ids)
            )
        )
        or 0
    )
    assignments = db.scalars(
        select(Assignment)
        .where(Assignment.class_id.in_(class_ids))
        .order_by(Assignment.id)
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    # One aggregate query for the user's assignment-run results.
    rows = db.execute(
        select(Run.assignment_id, Run.summary_verdict, Run.steps).where(
            Run.user_id == user.id,
            Run.assignment_id.is_not(None),
            Run.summary_verdict.is_not(None),
        )
    ).all()
    best_by_assignment: dict[int, tuple[str, int | None]] = {}
    for assignment_id, verdict, steps in rows:
        current = best_by_assignment.get(assignment_id)
        # Higher verdict priority wins; fewer steps breaks ties.
        if current is None or (
            VERDICT_PRIORITY[verdict],
            -(steps or 0),
        ) > (VERDICT_PRIORITY[current[0]], -(current[1] or 0)):
            best_by_assignment[assignment_id] = (verdict, steps)
    now = datetime.now(UTC)
    items = [
        AssignmentListItem(
            id=a.id,
            problem_id=a.problem_id,
            deadline=a.deadline,
            status="open" if now < a.deadline else "closed",
            best_verdict=best_by_assignment.get(a.id, (None, None))[0],
            best_steps=best_by_assignment.get(a.id, (None, None))[1],
        )
        for a in assignments
    ]
    return Page(items=items, page=page, size=size, total=total)


@router.get("/contests", response_model=Page[ContestListItem])
def list_contests(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    total = db.scalar(select(func.count(Contest.id))) or 0
    contests = db.scalars(
        select(Contest)
        .order_by(Contest.id)
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    # Registered = direct participant OR member of any team in the contest.
    participant_ids = set(
        db.scalars(
            select(ContestParticipant.contest_id).where(
                ContestParticipant.user_id == user.id
            )
        ).all()
    )
    team_contest_ids = set(
        db.scalars(
            select(ContestTeam.contest_id)
            .join(ContestTeamMember, ContestTeamMember.team_id == ContestTeam.id)
            .where(ContestTeamMember.user_id == user.id)
        ).all()
    )
    registered_ids = participant_ids | team_contest_ids
    now = datetime.now(UTC)
    items = [
        ContestListItem(
            id=c.id,
            title=c.title,
            start_at=c.start_at,
            end_at=c.end_at,
            status=_contest_status(c, now),
            scoring_mode=c.scoring_mode,
            teams_enabled=c.teams_enabled,
            is_registered=c.id in registered_ids,
        )
        for c in contests
    ]
    return Page(items=items, page=page, size=size, total=total)
