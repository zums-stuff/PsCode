"""Test-case endpoints for pseint-api (todo 18).

Nested under ``/api/problems/{problem_id}/cases``.  Teacher+admin manage
cases; any authenticated user can list them.  Enforces the plan's
exactly-one ``is_sample`` constraint per problem at create and at
patch-to-sample.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db, require_teacher
from ..models import Problem, TestCase, User

router = APIRouter(prefix="/api/problems/{problem_id}/cases")


class TestCaseCreateRequest(BaseModel):
    input: str = ""
    expected_output: str = Field(min_length=1)
    seed: int = 0
    points: int = Field(default=1, ge=0)
    order: int = 0
    is_public: bool = False
    is_sample: bool = False


class TestCasePatchRequest(BaseModel):
    input: str | None = None
    expected_output: str | None = Field(default=None, min_length=1)
    seed: int | None = None
    points: int | None = Field(default=None, ge=0)
    order: int | None = None
    is_public: bool | None = None
    is_sample: bool | None = None


class TestCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    problem_id: int
    input: str
    expected_output: str
    seed: int
    points: int
    order: int
    is_public: bool
    is_sample: bool


def _get_problem_or_404(db: Session, problem_id: int) -> Problem:
    problem = db.get(Problem, problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    return problem


def _sample_exists(db: Session, problem_id: int, exclude_id: int | None = None) -> bool:
    query = select(TestCase).where(
        TestCase.problem_id == problem_id, TestCase.is_sample.is_(True)
    )
    if exclude_id is not None:
        query = query.where(TestCase.id != exclude_id)
    return db.scalar(query) is not None


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TestCaseOut)
def create_case(
    problem_id: int,
    req: TestCaseCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    _get_problem_or_404(db, problem_id)
    if req.is_sample and _sample_exists(db, problem_id):
        raise HTTPException(
            status_code=409, detail="Problem already has a sample test case"
        )
    case = TestCase(problem_id=problem_id, **req.model_dump())
    db.add(case)
    db.commit()
    return case


@router.get("", response_model=list[TestCaseOut])
def list_cases(
    problem_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_problem_or_404(db, problem_id)
    return db.scalars(
        select(TestCase)
        .where(TestCase.problem_id == problem_id)
        .order_by(TestCase.order, TestCase.id)
    ).all()


@router.patch("/{case_id}", response_model=TestCaseOut)
def patch_case(
    problem_id: int,
    case_id: int,
    req: TestCasePatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    _get_problem_or_404(db, problem_id)
    case = db.get(TestCase, case_id)
    if case is None or case.problem_id != problem_id:
        raise HTTPException(status_code=404, detail="Test case not found")
    data = req.model_dump(exclude_unset=True)
    if data.get("is_sample") is True and not case.is_sample and _sample_exists(
        db, problem_id, exclude_id=case.id
    ):
        raise HTTPException(
            status_code=409, detail="Problem already has a sample test case"
        )
    for key, value in data.items():
        setattr(case, key, value)
    db.commit()
    return case


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case(
    problem_id: int,
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    _get_problem_or_404(db, problem_id)
    case = db.get(TestCase, case_id)
    if case is None or case.problem_id != problem_id:
        raise HTTPException(status_code=404, detail="Test case not found")
    db.delete(case)
    db.commit()
