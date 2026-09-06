"""Run endpoints for pseint-api (todo 18).

POST /api/runs enqueues a submission (mode=assignment|contest|practice) and
returns 202 {run_id} — the API never judges; the worker (todo 35) consumes
the queued run.  Assignment mode enforces the deadline (422
ASSIGNMENT_CLOSED, teacher rejudge exempt); contest mode requires
participation; practice mode is never graded.  Source cap 64KB -> 413.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db
from ..models import (
    Assignment,
    Contest,
    ContestParticipant,
    ContestTeam,
    ContestTeamMember,
    Problem,
    Run,
    TestResult,
    User,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runs")

MAX_SOURCE_BYTES = 65536  # 64KB (M13 / todo 15 constants)


class RunCreateRequest(BaseModel):
    problem_id: int
    source: str
    mode: Literal["practice", "assignment", "contest"]
    assignment_id: int | None = None
    contest_id: int | None = None
    stdin: str | None = None


class TestResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_index: int
    verdict: str
    steps: int | None
    wall_ms: int | None
    output: str | None
    error: str | None


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    problem_id: int
    kind: str
    status: str
    summary_verdict: str | None
    steps: int | None
    wall_ms: int | None
    assignment_id: int | None
    contest_id: int | None
    created_at: datetime


class RunDetailOut(RunOut):
    test_results: list[TestResultOut] = []


def _enqueue_run(run_id: int) -> None:
    """Best-effort enqueue to Redis; the worker (todo 35) consumes the queue.

    If Redis is unreachable (or redis-py missing) the run simply stays
    ``queued`` in the DB and a warning is logged — tests never require Redis.
    """
    try:
        import redis

        client = redis.Redis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        )
        client.rpush("pseint:runs", str(run_id))
    except Exception:
        logger.warning("Redis unavailable; run %s left queued", run_id)


def _check_source_size(source: str) -> None:
    if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise HTTPException(
            status_code=413, detail="Source exceeds the 64KB limit"
        )


def _is_contest_member(db: Session, contest_id: int, user_id: int) -> bool:
    if db.get(ContestParticipant, (contest_id, user_id)) is not None:
        return True
    team_ids = set(
        db.scalars(
            select(ContestTeam.id).where(ContestTeam.contest_id == contest_id)
        ).all()
    )
    member_team_ids = set(
        db.scalars(
            select(ContestTeamMember.team_id).where(
                ContestTeamMember.user_id == user_id
            )
        ).all()
    )
    return bool(team_ids & member_team_ids)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def create_run(
    req: RunCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _check_source_size(req.source)
    if db.get(Problem, req.problem_id) is None:
        raise HTTPException(status_code=404, detail="Problem not found")

    run = Run(
        user_id=user.id,
        problem_id=req.problem_id,
        kind=req.mode,
        status="queued",
        source=req.source,
        stdin=req.stdin if req.stdin else None,
    )

    if req.mode == "assignment":
        if req.assignment_id is None:
            raise HTTPException(
                status_code=422, detail="assignment_id is required for assignment mode"
            )
        assignment = db.get(Assignment, req.assignment_id)
        if assignment is None:
            raise HTTPException(status_code=404, detail="Assignment not found")
        # Teacher rejudge is exempt from the deadline rule (plan todo 18).
        if (
            user.role not in ("teacher", "admin")
            and datetime.now(UTC) > assignment.deadline
        ):
            raise HTTPException(
                status_code=422, detail="ASSIGNMENT_CLOSED"
            )
        run.assignment_id = assignment.id
    elif req.mode == "contest":
        if req.contest_id is None:
            raise HTTPException(
                status_code=422, detail="contest_id is required for contest mode"
            )
        contest = db.get(Contest, req.contest_id)
        if contest is None:
            raise HTTPException(status_code=404, detail="Contest not found")
        if user.role not in ("teacher", "admin") and not _is_contest_member(
            db, contest.id, user.id
        ):
            raise HTTPException(
                status_code=403, detail="Not a participant of this contest"
            )
        run.contest_id = contest.id

    db.add(run)
    db.commit()
    _enqueue_run(run.id)
    return {"run_id": run.id}


@router.get("", response_model=list[RunOut])
def list_runs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return db.scalars(
        select(Run).where(Run.user_id == user.id).order_by(Run.created_at.desc())
    ).all()


@router.get("/{run_id}", response_model=RunDetailOut)
def get_run(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.user_id != user.id:
        # Teachers/admins may observe contest runs (contest observer).
        if user.role in ("teacher", "admin") and run.kind == "contest":
            pass
        else:
            raise HTTPException(
                status_code=403, detail="Not allowed to view this run"
            )
    results = db.scalars(
        select(TestResult)
        .where(TestResult.run_id == run.id)
        .order_by(TestResult.case_index)
    ).all()
    return RunDetailOut(
        **RunOut.model_validate(run).model_dump(), test_results=results
    )
