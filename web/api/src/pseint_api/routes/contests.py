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
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db, require_teacher
from ..models import Contest, ContestParticipant, ContestTeam, ContestTeamMember, User

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
