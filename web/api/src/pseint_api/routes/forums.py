"""Forum endpoints for pseint-api (todo 18).

Per-problem threads with posts (D15).  Contest phase lock: while a contest
containing the problem is live (``now in [start_at, end_at]``), only
teachers/admins may post — students get 403; before/after the window any
authenticated user may post.  Threads created during a live contest record
the contest_id.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Generic, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db
from ..models import (
    Assignment,
    Class,
    ClassMember,
    Contest,
    ContestProblem,
    ForumPost,
    ForumThread,
    Problem,
    User,
)

router = APIRouter(prefix="/api")

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    page: int
    size: int
    total: int


class ThreadCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)


class PostCreateRequest(BaseModel):
    body: str = Field(min_length=1)
    parent_id: int | None = None


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


class ThreadIndexOut(BaseModel):
    """A thread as shown on the cross-problem forums index (todo forum tab).

    Richer than :class:`ThreadOut`: carries the owning problem's title, the
    thread author's username, the reply count and the most recent activity.
    """

    id: int
    problem_id: int
    problem_title: str
    contest_id: int | None
    title: str
    author_id: int
    author_username: str
    pinned: bool
    created_at: datetime
    reply_count: int
    last_activity_at: datetime | None


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


def _visible_problem_ids(db: Session, user: User) -> set[int]:
    """Problem ids whose threads the user may see on the forum index.

    Visibility mirrors the rest of the app (todo 21/23): a problem is visible
    when it belongs to a class the user can see (via Assignment), or when it
    has NO assignments at all (public / no-class problems).  Admins see every
    problem (every problem is in some class a teacher owns).
    """
    if user.role == "admin":
        class_ids = db.scalars(select(Class.id)).all()
    elif user.role == "teacher":
        class_ids = db.scalars(
            select(Class.id).where(Class.teacher_id == user.id)
        ).all()
    else:
        class_ids = db.scalars(
            select(ClassMember.class_id).where(ClassMember.user_id == user.id)
        ).all()

    class_ids = list(class_ids)
    assigned_visible = (
        set(
            db.scalars(
                select(Assignment.problem_id).where(
                    Assignment.class_id.in_(class_ids)
                )
            ).all()
        )
        if class_ids
        else set()
    )
    # Problems with no assignment anywhere are public / no-class.
    assigned_anywhere = set(db.scalars(select(Assignment.problem_id)).all())
    public_ids = set(db.scalars(select(Problem.id)).all()) - assigned_anywhere
    return assigned_visible | public_ids


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
    post = ForumPost(
        thread_id=thread_id,
        author_id=user.id,
        body=req.body,
        parent_id=req.parent_id,
    )
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


@router.get("/threads/{thread_id}", response_model=ThreadOut)
def get_thread(
    thread_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    thread = db.get(ForumThread, thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if thread.problem_id not in _visible_problem_ids(db, user):
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


@router.get("/threads", response_model=Page[ThreadIndexOut])
def list_all_threads(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    problem_id: int | None = Query(None),
    class_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Paginated forum index across all problems the user can see (todo forum).

    Joins threads on problems (for the problem title) and the thread author
    (for the username), restricts to the caller's visible problem set, then
    enriches with reply count + latest activity in ONE aggregate query
    (no N+1).  Optional ``problem_id`` / ``class_id`` filters narrow the set.
    """
    visible = _visible_problem_ids(db, user)

    # class_id filter: intersect with the problems assigned to that class.
    if class_id is not None:
        cls = db.get(Class, class_id)
        if cls is None:
            raise HTTPException(status_code=404, detail="Class not found")
        class_problem_ids = set(
            db.scalars(
                select(Assignment.problem_id).where(
                    Assignment.class_id == class_id
                )
            ).all()
        )
        visible &= class_problem_ids

    if problem_id is not None:
        if problem_id not in visible:
            raise HTTPException(status_code=404, detail="Thread not found")
        visible = {problem_id}

    visible = list(visible)
    if not visible:
        return Page(items=[], page=page, size=size, total=0)

    total = (
        db.scalar(
            select(func.count(ForumThread.id)).where(
                ForumThread.problem_id.in_(visible)
            )
        )
        or 0
    )

    rows = db.execute(
        select(
            ForumThread,
            Problem.title.label("problem_title"),
            User.username.label("author_username"),
        )
        .join(Problem, Problem.id == ForumThread.problem_id)
        .join(User, User.id == ForumThread.created_by)
        .where(ForumThread.problem_id.in_(visible))
        .order_by(ForumThread.pinned.desc(), ForumThread.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()

    thread_ids = [t.id for t, _, _ in rows]
    if not thread_ids:
        return Page(items=[], page=page, size=size, total=total)

    agg = db.execute(
        select(
            ForumPost.thread_id,
            func.count(ForumPost.id),
            func.max(ForumPost.created_at),
        )
        .where(ForumPost.thread_id.in_(thread_ids))
        .group_by(ForumPost.thread_id)
    ).all()
    counts = {tid: (count, last) for tid, count, last in agg}

    items = [
        ThreadIndexOut(
            id=thread.id,
            problem_id=thread.problem_id,
            problem_title=problem_title,
            contest_id=thread.contest_id,
            title=thread.title,
            author_id=thread.created_by,
            author_username=author_username,
            pinned=thread.pinned,
            created_at=thread.created_at,
            reply_count=counts.get(thread.id, (0, None))[0],
            last_activity_at=counts.get(thread.id, (0, None))[1],
        )
        for thread, problem_title, author_username in rows
    ]
    return Page(items=items, page=page, size=size, total=total)
