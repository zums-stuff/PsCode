"""Forum endpoints for pseint-api (todo 18).

Per-problem threads with posts (D15).  Contest phase lock: while a contest
containing the problem is live (``now in [start_at, end_at]``), only
teachers/admins may post — students get 403; before/after the window any
authenticated user may post.  Threads created during a live contest record
the contest_id.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db
from ..models import Contest, ContestProblem, ForumPost, ForumThread, Problem, User

router = APIRouter(prefix="/api")


class ThreadCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)


class PostCreateRequest(BaseModel):
    body: str = Field(min_length=1)


class ThreadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    problem_id: int
    contest_id: int | None
    title: str
    created_by: int
    pinned: bool
    created_at: datetime


class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    thread_id: int
    parent_id: int | None
    author_id: int
    body: str
    created_at: datetime


def _get_problem_or_404(db: Session, problem_id: int) -> Problem:
    problem = db.get(Problem, problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    return problem


def _running_contest_for_problem(
    db: Session, problem_id: int
) -> Contest | None:
    """The live contest containing ``problem_id``, or None (D15 phase lock)."""
    now = datetime.now(UTC)
    return db.scalar(
        select(Contest)
        .join(ContestProblem, ContestProblem.contest_id == Contest.id)
        .where(
            ContestProblem.problem_id == problem_id,
            Contest.start_at <= now,
            Contest.end_at >= now,
        )
    )


def _check_contest_lock(db: Session, problem_id: int, user: User) -> Contest | None:
    """Raise 403 for students during a live contest; return the contest."""
    contest = _running_contest_for_problem(db, problem_id)
    if contest is not None and user.role not in ("teacher", "admin"):
        raise HTTPException(
            status_code=403,
            detail="Contest in progress: only teachers can post",
        )
    return contest


@router.post(
    "/problems/{problem_id}/threads",
    status_code=status.HTTP_201_CREATED,
    response_model=ThreadOut,
)
def create_thread(
    problem_id: int,
    req: ThreadCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_problem_or_404(db, problem_id)
    contest = _check_contest_lock(db, problem_id, user)
    thread = ForumThread(
        problem_id=problem_id,
        contest_id=contest.id if contest is not None else None,
        title=req.title,
        created_by=user.id,
    )
    db.add(thread)
    db.flush()
    db.add(ForumPost(thread_id=thread.id, author_id=user.id, body=req.body))
    db.commit()
    return thread


@router.get("/problems/{problem_id}/threads", response_model=list[ThreadOut])
def list_threads(
    problem_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_problem_or_404(db, problem_id)
    return db.scalars(
        select(ForumThread)
        .where(ForumThread.problem_id == problem_id)
        .order_by(ForumThread.created_at.desc())
    ).all()


@router.post(
    "/threads/{thread_id}/posts",
    status_code=status.HTTP_201_CREATED,
    response_model=PostOut,
)
def create_post(
    thread_id: int,
    req: PostCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    thread = db.get(ForumThread, thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    _check_contest_lock(db, thread.problem_id, user)
    post = ForumPost(thread_id=thread_id, author_id=user.id, body=req.body)
    db.add(post)
    db.commit()
    return post


@router.get("/threads/{thread_id}/posts", response_model=list[PostOut])
def list_posts(
    thread_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    thread = db.get(ForumThread, thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return db.scalars(
        select(ForumPost)
        .where(ForumPost.thread_id == thread_id)
        .order_by(ForumPost.created_at)
    ).all()
