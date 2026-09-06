"""Contest scoreboard endpoint for pseint-api (todo 18).

GET /api/contests/{contest_id}/scoreboard delegates to the judge's
``compute_scoreboard`` (todo 14): cf mode ranks solves desc / penalty asc,
ioi mode ranks points desc.  Visible to participants (and team members) and
to teachers/admins.  Submissions are built from done runs + their per-case
TestResults; IOI points = sum of the AC test cases' ``points``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db
from ..models import (
    Contest,
    ContestParticipant,
    ContestTeam,
    ContestTeamMember,
    Run,
    TestCase,
    TestResult,
    User,
)
from .contests import _is_team_member

router = APIRouter(prefix="/api/contests/{contest_id}")


def _row_dict(row) -> dict:
    return {
        "participant_id": row.participant_id,
        "rank": row.rank,
        "solves": row.solves,
        "penalty": row.penalty,
        "points": row.points,
        "total_ac_cases": row.total_ac_cases,
        "problems": {
            pid: {
                "solved": pr.solved,
                "solve_time_min": pr.solve_time_min,
                "wrong_attempts": pr.wrong_attempts,
                "points": pr.points,
                "best_ac_cases": pr.best_ac_cases,
                "best_steps": pr.best_steps,
                "best_submission_id": pr.best_submission_id,
            }
            for pid, pr in row.problems.items()
        },
    }


@router.get("/scoreboard")
def get_scoreboard(
    contest_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    contest = db.get(Contest, contest_id)
    if contest is None:
        raise HTTPException(status_code=404, detail="Contest not found")
    if user.role not in ("teacher", "admin"):
        participant = db.get(ContestParticipant, (contest_id, user.id))
        if participant is None and not _is_team_member(db, contest_id, user.id):
            raise HTTPException(
                status_code=403, detail="Only participants can view the scoreboard"
            )

    runs = db.scalars(
        select(Run).where(Run.contest_id == contest_id).order_by(Run.id)
    ).all()

    # Test cases per problem (ordered) — IOI points resolve case_index -> points.
    problem_ids = {r.problem_id for r in runs}
    cases: dict[int, list[TestCase]] = {}
    for pid in problem_ids:
        cases[pid] = db.scalars(
            select(TestCase).where(TestCase.problem_id == pid).order_by(TestCase.order)
        ).all()

    # Team roster (locked once the contest starts — D16).
    roster: dict[str, set[str]] | None = None
    team_map: dict[int, str] = {}
    if contest.teams_enabled:
        roster = {}
        teams = db.scalars(
            select(ContestTeam).where(ContestTeam.contest_id == contest_id)
        ).all()
        for team in teams:
            member_ids = db.scalars(
                select(ContestTeamMember.user_id).where(
                    ContestTeamMember.team_id == team.id
                )
            ).all()
            roster[str(team.id)] = {str(m) for m in member_ids}
            for member_id in member_ids:
                team_map[member_id] = str(team.id)

    from pseint_judge.scoring import Submission, compute_scoreboard

    submissions = []
    for run in runs:
        if run.status != "done" or run.summary_verdict is None:
            continue
        results = db.scalars(
            select(TestResult)
            .where(TestResult.run_id == run.id)
            .order_by(TestResult.case_index)
        ).all()
        points = 0.0
        ac_cases = 0
        problem_cases = cases.get(run.problem_id, [])
        for result in results:
            if result.verdict == "AC":
                ac_cases += 1
                if result.case_index < len(problem_cases):
                    points += problem_cases[result.case_index].points
        submissions.append(
            Submission(
                id=str(run.id),
                user_id=str(run.user_id),
                problem_id=str(run.problem_id),
                submitted_at=run.created_at,
                verdict=run.summary_verdict,
                points=points,
                ac_cases=ac_cases,
                steps=run.steps or 0,
                team_id=team_map.get(run.user_id),
            )
        )

    scoreboard = compute_scoreboard(
        submissions,
        mode=contest.scoring_mode,
        start_at=contest.start_at,
        roster=roster,
    )
    return {
        "mode": scoreboard.mode,
        "rows": [_row_dict(row) for row in scoreboard.rows],
    }
