"""Contest endpoints for pseint-api (todo 18).

Teacher+admin create contests; any authenticated user lists/reads them and
self-registers as a participant.  Teams are optional per contest
(``teams_enabled``, D16): teachers create teams and manage members, students
join a team (at most one per contest).  The scoreboard lives in
``routes/scoreboard.py``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db, require_teacher
from ..models import (
    Class,
    ClassMember,
    Contest,
    ContestParticipant,
    ContestProblem,
    ContestTeam,
    ContestTeamMember,
    Problem,
    User,
)

router = APIRouter(prefix="/api/contests")


class ContestCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    start_at: datetime
    end_at: datetime
    scoring_mode: Literal["cf", "ioi"] = "cf"
    teams_enabled: bool = False


class TeamCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class TeamMemberRequest(BaseModel):
    user_id: int


class ContestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    start_at: datetime
    end_at: datetime
    scoring_mode: str
    teams_enabled: bool
    created_by: int


class ContestTeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contest_id: int
    name: str
    created_at: datetime


def _get_contest_or_404(db: Session, contest_id: int) -> Contest:
    contest = db.get(Contest, contest_id)
    if contest is None:
        raise HTTPException(status_code=404, detail="Contest not found")
    return contest


def _is_team_member(db: Session, contest_id: int, user_id: int) -> bool:
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


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ContestOut)
def create_contest(
    req: ContestCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    if req.start_at >= req.end_at:
        raise HTTPException(
            status_code=422, detail="start_at must be before end_at"
        )
    contest = Contest(
        title=req.title,
        start_at=req.start_at,
        end_at=req.end_at,
        scoring_mode=req.scoring_mode,
        teams_enabled=req.teams_enabled,
        created_by=user.id,
    )
    db.add(contest)
    db.commit()
    return contest


@router.get("/{contest_id}", response_model=ContestOut)
def get_contest(
    contest_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _get_contest_or_404(db, contest_id)


@router.post("/{contest_id}/register", status_code=status.HTTP_201_CREATED)
def register_contest(
    contest_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_contest_or_404(db, contest_id)
    if db.get(ContestParticipant, (contest_id, user.id)) is not None:
        raise HTTPException(
            status_code=409, detail="Already registered for this contest"
        )
    db.add(ContestParticipant(contest_id=contest_id, user_id=user.id))
    db.commit()
    return {"contest_id": contest_id, "user_id": user.id}


@router.get("/{contest_id}/teams", response_model=list[ContestTeamOut])
def list_teams(
    contest_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_contest_or_404(db, contest_id)
    return db.scalars(
        select(ContestTeam)
        .where(ContestTeam.contest_id == contest_id)
        .order_by(ContestTeam.id)
    ).all()


@router.post(
    "/{contest_id}/teams",
    status_code=status.HTTP_201_CREATED,
    response_model=ContestTeamOut,
)
def create_team(
    contest_id: int,
    req: TeamCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    contest = _get_contest_or_404(db, contest_id)
    if not contest.teams_enabled:
        raise HTTPException(
            status_code=409, detail="Teams are not enabled for this contest"
        )
    team = ContestTeam(contest_id=contest_id, name=req.name)
    db.add(team)
    db.commit()
    return team


@router.post(
    "/{contest_id}/teams/{team_id}/members", status_code=status.HTTP_201_CREATED
)
def add_team_member(
    contest_id: int,
    team_id: int,
    req: TeamMemberRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    contest = _get_contest_or_404(db, contest_id)
    if not contest.teams_enabled:
        raise HTTPException(
            status_code=409, detail="Teams are not enabled for this contest"
        )
    team = db.get(ContestTeam, team_id)
    if team is None or team.contest_id != contest_id:
        raise HTTPException(status_code=404, detail="Team not found")
    # Students may only add themselves; teachers/admins may add anyone.
    if user.role not in ("teacher", "admin") and req.user_id != user.id:
        raise HTTPException(
            status_code=403, detail="Students can only join a team themselves"
        )
    if db.get(ContestTeamMember, (team_id, req.user_id)) is not None:
        raise HTTPException(
            status_code=409, detail="User is already a member of this team"
        )
    # D16: each participant in at most one team per contest.
    other_team_ids = set(
        db.scalars(
            select(ContestTeamMember.team_id).where(
                ContestTeamMember.user_id == req.user_id
            )
        ).all()
    )
    contest_team_ids = set(
        db.scalars(
            select(ContestTeam.id).where(ContestTeam.contest_id == contest_id)
        ).all()
    )
    if other_team_ids & contest_team_ids:
        raise HTTPException(
            status_code=409, detail="User already belongs to a team in this contest"
        )
    db.add(ContestTeamMember(team_id=team_id, user_id=req.user_id))
    db.commit()
    return {"team_id": team_id, "user_id": req.user_id}


class ContestPatchRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    start_at: datetime | None = None
    end_at: datetime | None = None


@router.patch("/{contest_id}", response_model=ContestOut)
def patch_contest(
    contest_id: int,
    req: ContestPatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    """Update contest metadata (title/dates). Admin or owning teacher only.

    scoring_mode / teams_enabled are intentionally NOT editable here — a
    contest edit must never change persisted verdicts (plan todo 24).
    """
    contest = _get_contest_or_404(db, contest_id)
    if user.role != "admin" and contest.created_by != user.id:
        raise HTTPException(
            status_code=403, detail="Only the owning teacher can edit this contest"
        )
    data = req.model_dump(exclude_unset=True)
    if "start_at" in data and "end_at" in data:
        if data["start_at"] >= data["end_at"]:
            raise HTTPException(
                status_code=422, detail="start_at must be before end_at"
            )
    elif "start_at" in data and data["start_at"] >= contest.end_at:
        raise HTTPException(
            status_code=422, detail="start_at must be before end_at"
        )
    elif "end_at" in data and contest.start_at >= data["end_at"]:
        raise HTTPException(
            status_code=422, detail="start_at must be before end_at"
        )
    for key, value in data.items():
        setattr(contest, key, value)
    db.commit()
    return contest


class ContestParticipantOut(BaseModel):
    user_id: int
    username: str


@router.get("/{contest_id}/participants", response_model=list[ContestParticipantOut])
def list_participants(
    contest_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    """List contest participants with usernames (admin or owning teacher)."""
    contest = _get_contest_or_404(db, contest_id)
    if user.role != "admin" and contest.created_by != user.id:
        raise HTTPException(
            status_code=403, detail="Only the owning teacher can view participants"
        )
    rows = db.execute(
        select(ContestParticipant.user_id, User.username)
        .join(User, User.id == ContestParticipant.user_id)
        .where(ContestParticipant.contest_id == contest_id)
        .order_by(User.username)
    ).all()
    return [
        ContestParticipantOut(user_id=user_id, username=username)
        for user_id, username in rows
    ]


@router.post(
    "/{contest_id}/participants/user/{user_id}",
    status_code=status.HTTP_201_CREATED,
)
def add_participant_user(
    contest_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    """Add an individual user as a contest participant (admin/owning teacher)."""
    contest = _get_contest_or_404(db, contest_id)
    if user.role != "admin" and contest.created_by != user.id:
        raise HTTPException(
            status_code=403, detail="Only the owning teacher can add participants"
        )
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    if db.get(ContestParticipant, (contest_id, user_id)) is not None:
        raise HTTPException(
            status_code=409, detail="User is already a participant"
        )
    db.add(ContestParticipant(contest_id=contest_id, user_id=user_id))
    db.commit()
    return {"contest_id": contest_id, "user_id": user_id}


@router.post(
    "/{contest_id}/participants/class/{class_id}",
    status_code=status.HTTP_201_CREATED,
)
def add_participant_class(
    contest_id: int,
    class_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    """Bulk-add all members of a class as contest participants."""
    contest = _get_contest_or_404(db, contest_id)
    if user.role != "admin" and contest.created_by != user.id:
        raise HTTPException(
            status_code=403, detail="Only the owning teacher can add participants"
        )
    cls = db.get(Class, class_id)
    if cls is None:
        raise HTTPException(status_code=404, detail="Class not found")
    if user.role != "admin" and cls.teacher_id != user.id:
        raise HTTPException(
            status_code=403, detail="Only the owning teacher can add this class"
        )
    member_ids = db.scalars(
        select(ClassMember.user_id).where(ClassMember.class_id == class_id)
    ).all()
    added = 0
    for member_id in member_ids:
        if db.get(ContestParticipant, (contest_id, member_id)) is None:
            db.add(ContestParticipant(contest_id=contest_id, user_id=member_id))
            added += 1
    db.commit()
    return {"contest_id": contest_id, "class_id": class_id, "added": added}


class ContestProblemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    contest_id: int
    problem_id: int
    order: int
    title: str


class ContestProblemAddRequest(BaseModel):
    problem_id: int


class ContestProblemPatchRequest(BaseModel):
    order: int


@router.get(
    "/{contest_id}/contest-problems", response_model=list[ContestProblemOut]
)
def list_contest_problems(
    contest_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List the contest's problem set ordered by ``order``."""
    _get_contest_or_404(db, contest_id)
    rows = db.execute(
        select(ContestProblem, Problem.title)
        .join(Problem, Problem.id == ContestProblem.problem_id)
        .where(ContestProblem.contest_id == contest_id)
        .order_by(ContestProblem.order, ContestProblem.problem_id)
    ).all()
    return [
        ContestProblemOut(
            contest_id=cp.contest_id,
            problem_id=cp.problem_id,
            order=cp.order,
            title=title,
        )
        for cp, title in rows
    ]


@router.post(
    "/{contest_id}/contest-problems",
    status_code=status.HTTP_201_CREATED,
    response_model=ContestProblemOut,
)
def add_contest_problem(
    contest_id: int,
    req: ContestProblemAddRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    """Add a problem to the contest (admin/owning teacher)."""
    contest = _get_contest_or_404(db, contest_id)
    if user.role != "admin" and contest.created_by != user.id:
        raise HTTPException(
            status_code=403, detail="Only the owning teacher can edit the problem set"
        )
    if db.get(Problem, req.problem_id) is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    if db.get(ContestProblem, (contest_id, req.problem_id)) is not None:
        raise HTTPException(
            status_code=409, detail="Problem is already in the contest"
        )
    max_order = db.scalar(
        select(func.max(ContestProblem.order)).where(
            ContestProblem.contest_id == contest_id
        )
    )
    if max_order is None:
        max_order = -1
    cp = ContestProblem(
        contest_id=contest_id, problem_id=req.problem_id, order=max_order + 1
    )
    db.add(cp)
    db.commit()
    title = db.get(Problem, req.problem_id).title
    return ContestProblemOut(
        contest_id=contest_id, problem_id=req.problem_id, order=cp.order, title=title
    )


@router.patch(
    "/{contest_id}/contest-problems/{problem_id}",
    response_model=ContestProblemOut,
)
def patch_contest_problem(
    contest_id: int,
    problem_id: int,
    req: ContestProblemPatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    """Update a contest problem's ``order`` (reorder the problem set)."""
    contest = _get_contest_or_404(db, contest_id)
    if user.role != "admin" and contest.created_by != user.id:
        raise HTTPException(
            status_code=403, detail="Only the owning teacher can edit the problem set"
        )
    cp = db.get(ContestProblem, (contest_id, problem_id))
    if cp is None:
        raise HTTPException(status_code=404, detail="Problem not in contest")
    cp.order = req.order
    db.commit()
    title = db.get(Problem, problem_id).title
    return ContestProblemOut(
        contest_id=contest_id, problem_id=problem_id, order=cp.order, title=title
    )


@router.delete(
    "/{contest_id}/contest-problems/{problem_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_contest_problem(
    contest_id: int,
    problem_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    """Remove a problem from the contest (admin/owning teacher)."""
    contest = _get_contest_or_404(db, contest_id)
    if user.role != "admin" and contest.created_by != user.id:
        raise HTTPException(
            status_code=403, detail="Only the owning teacher can edit the problem set"
        )
    cp = db.get(ContestProblem, (contest_id, problem_id))
    if cp is None:
        raise HTTPException(status_code=404, detail="Problem not in contest")
    db.delete(cp)
    db.commit()
