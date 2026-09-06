"""Auth endpoints for pseint-api (todo 17).

register/login/me are open or self-authenticated; teacher creation and
password reset are admin-only (D10: students self-register with a class code,
teachers are provisioned by a bootstrap admin).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import auth, config
from ..deps import get_current_user, get_db, require_admin
from ..models import Class, ClassMember, User

router = APIRouter(prefix="/api")


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8)
    class_code: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class TeacherCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8)


class PasswordResetRequest(BaseModel):
    password: str = Field(min_length=8)


def _user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
    }


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.username == req.username)) is not None:
        raise HTTPException(status_code=409, detail="Username already taken")

    cls = None
    if req.class_code is not None:
        cls = db.scalar(select(Class).where(Class.code == req.class_code))
        if cls is None:
            raise HTTPException(status_code=400, detail="Invalid class code")

    user = User(
        username=req.username,
        display_name=req.display_name,
        password_hash=auth.hash_password(req.password),
        role="student",
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username already taken")
    if cls is not None:
        db.add(ClassMember(class_id=cls.id, user_id=user.id))
    db.commit()
    return _user_dict(user)


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == req.username))
    if user is None or not auth.verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = auth.create_access_token(
        user.id, config.secret_key(), config.token_ttl_minutes()
    )
    return {"token_type": "bearer", "access_token": token}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _user_dict(user)


@router.post("/admin/teachers", status_code=status.HTTP_201_CREATED)
def create_teacher(
    req: TeacherCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if db.scalar(select(User).where(User.username == req.username)) is not None:
        raise HTTPException(status_code=409, detail="Username already taken")
    teacher = User(
        username=req.username,
        display_name=req.display_name,
        password_hash=auth.hash_password(req.password),
        role="teacher",
    )
    db.add(teacher)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username already taken")
    db.commit()
    return _user_dict(teacher)


@router.post("/admin/users/{user_id}/reset-password")
def reset_password(
    user_id: int,
    req: PasswordResetRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.password_hash = auth.hash_password(req.password)
    db.commit()
    return _user_dict(user)
