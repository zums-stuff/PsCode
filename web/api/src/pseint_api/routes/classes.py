"""Class endpoints for pseint-api (todo 18).

Admin creates classes (generating a unique join code); teachers edit their
own classes only; any authenticated user can look up a class by code for
self-registration (the register endpoint consumes the code).
"""

from __future__ import annotations

import secrets
import string

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db, require_admin, require_teacher
from ..models import Class, User

router = APIRouter(prefix="/api/classes")

_CODE_ALPHABET = string.ascii_uppercase + string.digits
_CODE_LENGTH = 6


class ClassCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    teacher_id: int | None = None
    anticheat_threshold: float = Field(default=0.85, ge=0, le=1)


class ClassPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    anticheat_threshold: float | None = Field(default=None, ge=0, le=1)


class ClassOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    teacher_id: int
    anticheat_threshold: float


def _generate_code(db: Session) -> str:
    for _ in range(100):
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
        if db.scalar(select(Class).where(Class.code == code)) is None:
            return code
    raise HTTPException(
        status_code=500, detail="Could not generate a unique class code"
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ClassOut)
def create_class(
    req: ClassCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    cls = Class(
        name=req.name,
        code=_generate_code(db),
        teacher_id=req.teacher_id or admin.id,
        anticheat_threshold=req.anticheat_threshold,
    )
    db.add(cls)
    db.commit()
    return cls


@router.get("", response_model=list[ClassOut])
def list_classes(
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    query = select(Class).order_by(Class.id)
    if user.role != "admin":
        query = query.where(Class.teacher_id == user.id)
    return db.scalars(query).all()


@router.get("/{code}", response_model=ClassOut)
def get_class_by_code(
    code: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cls = db.scalar(select(Class).where(Class.code == code))
    if cls is None:
        raise HTTPException(status_code=404, detail="Class not found")
    return cls


@router.patch("/{class_id}", response_model=ClassOut)
def patch_class(
    class_id: int,
    req: ClassPatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    cls = db.get(Class, class_id)
    if cls is None:
        raise HTTPException(status_code=404, detail="Class not found")
    if user.role != "admin" and cls.teacher_id != user.id:
        raise HTTPException(
            status_code=403, detail="Only the owning teacher can edit this class"
        )
    for key, value in req.model_dump(exclude_unset=True).items():
        setattr(cls, key, value)
    db.commit()
    return cls
