"""Problem endpoints for pseint-api (todo 18).

CRUD for problems.  Creation/editing is teacher+admin (``require_teacher``);
listing and detail are open to any authenticated user.  Validation follows the
plan: statement non-empty, ``expected_complexity`` in the SPEC enum,
``compare_mode`` in {exact, token}, ``step_budget`` int or null.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db, require_teacher
from ..models import Problem, User

router = APIRouter(prefix="/api/problems")


class ProblemCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    statement: str = Field(min_length=1)
    expected_complexity: Literal[
        "O(1)",
        "O(log n)",
        "O(n)",
        "O(n log n)",
        "O(n²)",
        "O(n³)",
        "O(2ⁿ)",
        "other",
    ]
    compare_mode: Literal["exact", "token"] = "exact"
    step_budget: int | None = None


class ProblemPatchRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    statement: str | None = Field(default=None, min_length=1)
    expected_complexity: Literal[
        "O(1)",
        "O(log n)",
        "O(n)",
        "O(n log n)",
        "O(n²)",
        "O(n³)",
        "O(2ⁿ)",
        "other",
    ] | None = None
    compare_mode: Literal["exact", "token"] | None = None
    step_budget: int | None = None


class ProblemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    statement: str
    expected_complexity: str
    step_budget: int | None
    compare_mode: str
    author_id: int
    created_at: datetime


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ProblemOut)
def create_problem(
    req: ProblemCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    problem = Problem(
        title=req.title,
        statement=req.statement,
        expected_complexity=req.expected_complexity,
        compare_mode=req.compare_mode,
        step_budget=req.step_budget,
        author_id=user.id,
    )
    db.add(problem)
    db.commit()
    return problem


@router.get("", response_model=list[ProblemOut])
def list_problems(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return db.scalars(select(Problem).order_by(Problem.id)).all()


@router.get("/{problem_id}", response_model=ProblemOut)
def get_problem(
    problem_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    problem = db.get(Problem, problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    return problem


@router.patch("/{problem_id}", response_model=ProblemOut)
def patch_problem(
    problem_id: int,
    req: ProblemPatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    problem = db.get(Problem, problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    for key, value in req.model_dump(exclude_unset=True).items():
        setattr(problem, key, value)
    db.commit()
    return problem
