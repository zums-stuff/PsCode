"""Similarity report endpoint for pseint-api (todo 18).

GET /api/classes/{class_id}/similarity — teacher of the class (or admin)
only.  Returns SimilarityPair rows with score >= the class's
``anticheat_threshold`` (default 0.85) where both runs belong to members of
the class.  Same-team pairs are excluded for ``scope=contest`` (D16: same-team
submissions are not compared).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db, require_teacher
from ..models import (
    Class,
    ClassMember,
    ContestTeam,
    ContestTeamMember,
    Run,
    SimilarityPair,
    User,
)

router = APIRouter(prefix="/api/classes/{class_id}")


class SimilarityPairOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_a_id: int
    run_b_id: int
    score: float
    scope: str
    created_at: datetime


def _same_team(db: Session, contest_id: int, user_a: int, user_b: int) -> bool:
    team_ids = set(
        db.scalars(
            select(ContestTeam.id).where(ContestTeam.contest_id == contest_id)
        ).all()
    )
    teams_a = set(
        db.scalars(
            select(ContestTeamMember.team_id).where(
                ContestTeamMember.user_id == user_a
            )
        ).all()
    )
    teams_b = set(
        db.scalars(
            select(ContestTeamMember.team_id).where(
                ContestTeamMember.user_id == user_b
            )
        ).all()
    )
    return bool((teams_a & teams_b) & team_ids)


@router.get("/similarity", response_model=list[SimilarityPairOut])
def class_similarity(
    class_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    cls = db.get(Class, class_id)
    if cls is None:
        raise HTTPException(status_code=404, detail="Class not found")
    if user.role != "admin" and cls.teacher_id != user.id:
        raise HTTPException(
            status_code=403, detail="Only the owning teacher can view this report"
        )

    member_ids = set(
        db.scalars(
            select(ClassMember.user_id).where(ClassMember.class_id == class_id)
        ).all()
    )
    pairs = db.scalars(
        select(SimilarityPair)
        .where(SimilarityPair.score >= cls.anticheat_threshold)
        .order_by(SimilarityPair.score.desc())
    ).all()

    result = []
    for pair in pairs:
        run_a = db.get(Run, pair.run_a_id)
        run_b = db.get(Run, pair.run_b_id)
        if run_a is None or run_b is None:
            continue
        if run_a.user_id not in member_ids or run_b.user_id not in member_ids:
            continue
        if pair.scope == "contest":
            contest_id = run_a.contest_id or run_b.contest_id
            if contest_id is not None and _same_team(
                db, contest_id, run_a.user_id, run_b.user_id
            ):
                continue
        result.append(pair)
    return result
