"""Run endpoints for pseint-api (todo 18).

POST /api/runs enqueues a submission (mode=assignment|contest|practice) and
returns 202 {run_id} — the API never judges; the worker (todo 35) consumes
the queued run.  Assignment mode enforces the deadline (422
ASSIGNMENT_CLOSED, teacher rejudge exempt); contest mode requires
participation; practice mode is never graded.  Source cap 64KB -> 413.

POST /api/runs/{run_id}/rejudge is the teacher/admin re-grading action:
it re-enqueues a copy of an existing run with the same source so the
engine re-evaluates it (e.g. after fixing an engine bug, or after the
seed is updated).  It is exempt from the per-user runs/submission rate
limits because it is an administrative action, not a student submission.
"""

import logging
import os
from datetime import UTC, datetime
from typing import Generic, Literal, TypeVar

import redis
from rq import Queue

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db, require_teacher
from ..models import (
    Assignment,
    Contest,
    ContestParticipant,
    ContestTeam,
    ContestTeamMember,
    Problem,
    Run,
    TestCase,
    TestResult,
    User,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runs")

MAX_SOURCE_BYTES = 65536  # 64KB (M13 / todo 15 constants)
HIDDEN_INPUT_PREFIX = 80  # hidden-case input truncation (todo 31 masking)

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    size: int
    total: int


class RunCreateRequest(BaseModel):
    problem_id: int | None = None
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
    problem_id: int | None
    kind: str
    status: str
    summary_verdict: str | None
    steps: int | None
    wall_ms: int | None
    assignment_id: int | None
    contest_id: int | None
    created_at: datetime


class RunDetailOut(RunOut):
    source: str = ""
    test_results: list[TestResultOut] = []


class RunDetailCaseOut(BaseModel):
    """One test case of a run, joined with the problem's TestCase.

    Visibility masking (plan todo 31, MUST NOT): hidden cases (not public,
    not sample) never expose ``expected_output`` and truncate ``input`` to
    the first 80 chars — students cannot reverse-engineer hidden cases from
    the payload.  ``diff_line`` is the 1-indexed first differing line for WA
    cases (safe subset: line number only, never the expected text).
    """

    case_index: int
    verdict: str
    steps: int | None
    wall_ms: int | None
    output: str | None
    error: str | None
    input: str | None
    expected_output: str | None
    diff_line: int | None
    is_sample: bool = False
    is_public: bool = False


class RunDetailResponse(BaseModel):
    run: RunDetailOut
    test_cases: list[RunDetailCaseOut]


def _enqueue_run(run_id: int) -> None:
    """Enqueue ``run_id`` directly to RQ's ``runs`` queue.

    RQ resolves the job by module path (``infra.worker.jobs.process_run``)
    so the function can run in a separate worker subprocess; this avoids
    the ``__main__``-function restriction that the legacy raw-list intake
    tripped over.  Failures (Redis unreachable, etc.) leave the run in
    ``queued`` status and emit a warning — the worker pool's health
    check + the user retrying the submission are the recovery paths.
    """
    try:
        from rq import Queue

        client = redis.Redis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        )
        queue_name = os.environ.get("RQ_QUEUE_NAME", "runs")
        q = Queue(queue_name, connection=client)
        q.enqueue("infra.worker.jobs.process_run", run_id)
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

    # Practice/sandbox mode allows no problem (free-form exploration). For
    # assignment/contest the problem must exist; the linked-id check below
    # raises 404 in those cases.
    if req.problem_id is not None and db.get(Problem, req.problem_id) is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    if req.problem_id is None and req.mode != "practice":
        raise HTTPException(
            status_code=422,
            detail="problem_id is required for non-practice runs",
        )

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


@router.post(
    "/{run_id}/rejudge",
    status_code=status.HTTP_202_ACCEPTED,
)
def rejudge_run(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
) -> dict[str, int]:
    """Re-enqueue ``run_id`` as a fresh run with the same source / stdin.

    Teacher/admin only.  Used after engine fixes, seed updates, or to
    verify a flaky verdict.  Exempt from the per-user runs/submission
    rate limits (handled by routing the request through a separate
    bucket — see ``RateLimitMiddleware``).
    """
    original = db.get(Run, run_id)
    if original is None:
        raise HTTPException(status_code=404, detail="Run not found")

    # Re-enqueue as a brand-new run row that copies the submission inputs.
    # We deliberately do NOT mutate the existing row — its verdict stays
    # as-is so the UI can show "rejudge in flight" vs the original verdict.
    rejudge = Run(
        user_id=original.user_id,
        problem_id=original.problem_id,
        kind=original.kind,
        status="queued",
        source=original.source,
        stdin=original.stdin,
        assignment_id=original.assignment_id,
        contest_id=original.contest_id,
    )
    db.add(rejudge)
    db.commit()
    _enqueue_run(rejudge.id)
    return {"run_id": rejudge.id, "original_run_id": original.id}


@router.get("", response_model=Page[RunOut])
def list_runs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    problem_id: int | None = None,
    contest_id: int | None = None,
    kind: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(Run).where(Run.user_id == user.id)
    if problem_id is not None:
        stmt = stmt.where(Run.problem_id == problem_id)
    if contest_id is not None:
        stmt = stmt.where(Run.contest_id == contest_id)
    if kind is not None:
        stmt = stmt.where(Run.kind == kind)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(
        stmt.order_by(Run.created_at.desc(), Run.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return Page[RunOut](
        items=[RunOut.model_validate(r) for r in items],
        page=page,
        size=size,
        total=total,
    )


def _first_diff_line(output: str, expected: str) -> int | None:
    out_lines = output.split("\n")
    exp_lines = expected.split("\n")
    for i, (a, b) in enumerate(zip(out_lines, exp_lines)):
        if a != b:
            return i + 1
    if len(out_lines) != len(exp_lines):
        return min(len(out_lines), len(exp_lines)) + 1
    return None


def _masked_input(input_text: str) -> str:
    """Hidden-case input: first 80 chars + '...' when longer (todo 31)."""
    if len(input_text) > HIDDEN_INPUT_PREFIX:
        return input_text[:HIDDEN_INPUT_PREFIX] + "..."
    return input_text


@router.get("/{run_id}/detail", response_model=RunDetailResponse)
def get_run_detail(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Run + per-case detail with hidden-case masking (todo 31).

    Ownership rule mirrors GET /api/runs/{id}: owner always; teachers/admins
    may observe contest runs.  Each TestResult is joined with its TestCase;
    hidden cases (``is_public=false AND is_sample=false``) get
    ``expected_output=null`` and a truncated ``input`` so students can never
    reverse-engineer them from the payload.
    """
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
    cases = db.scalars(
        select(TestCase)
        .where(TestCase.problem_id == run.problem_id)
        .order_by(TestCase.order, TestCase.id)
    ).all()
    case_by_index: dict[int, TestCase] = {}
    for i, tc in enumerate(cases):
        case_by_index.setdefault(i, tc)

    test_cases: list[RunDetailCaseOut] = []
    for tr in results:
        tc = case_by_index.get(tr.case_index)
        visible = tc is not None and (tc.is_public or tc.is_sample)
        expected = tc.expected_output if visible and tc is not None else None
        input_text = (
            tc.input if visible and tc is not None else _masked_input(tc.input)
            if tc is not None
            else None
        )
        diff_line = None
        if tr.verdict == "WA" and tr.output is not None and tc is not None:
            diff_line = _first_diff_line(tr.output, tc.expected_output)
        test_cases.append(
            RunDetailCaseOut(
                case_index=tr.case_index,
                verdict=tr.verdict,
                steps=tr.steps,
                wall_ms=tr.wall_ms,
                output=tr.output,
                error=tr.error,
                input=input_text,
                expected_output=expected,
                diff_line=diff_line,
                is_sample=tc.is_sample if tc is not None else False,
                is_public=tc.is_public if tc is not None else False,
            )
        )

    return RunDetailResponse(
        run=RunDetailOut.model_validate(run), test_cases=test_cases
    )


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
