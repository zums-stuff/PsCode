"""Assignment endpoints for pseint-api (todo 18).

Teachers create assignments (problem + deadline) for their OWN classes only;
admin may create for any class.  Students see the assignments of the classes
they belong to; teachers see their own classes' assignments.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db, require_teacher
from ..models import Assignment, Class, ClassMember, Problem, User

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


@router.get("", response_model=list[AssignmentOut])
def list_assignments(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role == "admin":
        return db.scalars(select(Assignment).order_by(Assignment.id)).all()
    if user.role == "teacher":
        class_ids = db.scalars(
            select(Class.id).where(Class.teacher_id == user.id)
        ).all()
        return db.scalars(
            select(Assignment)
            .where(Assignment.class_id.in_(class_ids))
            .order_by(Assignment.id)
        ).all()
    class_ids = db.scalars(
        select(ClassMember.class_id).where(ClassMember.user_id == user.id)
    ).all()
    return db.scalars(
        select(Assignment)
        .where(Assignment.class_id.in_(class_ids))
        .order_by(Assignment.id)
    ).all()
