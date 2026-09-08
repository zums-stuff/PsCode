"""Assignment endpoints for pseint-api (todo 18).

Teachers create assignments (problem + deadline) for their OWN classes only;
admin may create for any class.  Students see the assignments of the classes
they belong to; teachers see their own classes' assignments.

Todo 23 adds ``GET /api/assignments/{id}/submissions`` — the per-student best
run on an assignment, visible to the owning teacher (or admin) only.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db, require_teacher
from ..models import Assignment, Class, Problem, Run, User
from .listings import VERDICT_PRIORITY

router = APIRouter(prefix="/api/assignments")


class AssignmentCreateRequest(BaseModel):
    class_id: int
    problem_id: int
    deadline: datetime


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    class_id: int
    problem_id: int
    deadline: datetime
    created_at: datetime


@router.post("", status_code=status.HTTP_201_CREATED, response_model=AssignmentOut)
def create_assignment(
    req: AssignmentCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    cls = db.get(Class, req.class_id)
    if cls is None:
        raise HTTPException(status_code=404, detail="Class not found")
    if user.role != "admin" and cls.teacher_id != user.id:
        raise HTTPException(
            status_code=403, detail="Only the owning teacher can assign to this class"
        )
    if db.get(Problem, req.problem_id) is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    assignment = Assignment(
        class_id=req.class_id,
        problem_id=req.problem_id,
        deadline=req.deadline,
    )
    db.add(assignment)
    db.commit()
    return assignment


class AssignmentSubmissionOut(BaseModel):
    user_id: int
    username: str
    best_verdict: str | None
    steps: int | None
    source: str
    best_run_id: int | None = None  # the run_id of the best submission, for rejudge


@router.get(
    "/{assignment_id}/submissions", response_model=list[AssignmentSubmissionOut]
)
def list_assignment_submissions(
    assignment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    """Per-student best run on an assignment (owning teacher or admin only)."""
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    cls = db.get(Class, assignment.class_id)
    if user.role != "admin" and cls.teacher_id != user.id:
        raise HTTPException(
            status_code=403, detail="Only the owning teacher can view submissions"
        )
    runs = db.scalars(
        select(Run)
        .where(
            Run.assignment_id == assignment.id,
            Run.summary_verdict.is_not(None),
        )
        .order_by(Run.id)
    ).all()
    best: dict[int, Run] = {}
    for run in runs:
        current = best.get(run.user_id)
        if current is None or (
            VERDICT_PRIORITY[run.summary_verdict],
            -(run.steps or 0),
        ) > (VERDICT_PRIORITY[current.summary_verdict], -(current.steps or 0)):
            best[run.user_id] = run
    usernames = {
        u.id: u.username
        for u in db.scalars(select(User).where(User.id.in_(best.keys()))).all()
    }
    return [
        AssignmentSubmissionOut(
            user_id=run.user_id,
            username=usernames[run.user_id],
            best_verdict=run.summary_verdict,
            steps=run.steps,
            source=run.source,
            best_run_id=run.id,
        )
        for run in best.values()
    ]
