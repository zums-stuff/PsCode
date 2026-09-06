"""Similarity report endpoints for pseint-api (todo 18 + todo 39).

This module carries two surfaces:

* Class-scoped report (todo 18): ``GET /api/classes/{class_id}/similarity``
  — teacher of the class or admin only.
* Admin anticheat surface (todo 39): ``/api/admin/anticheat`` (list, pair
  detail) and ``/api/admin/classes/{id}/anticheat-threshold`` (config
  update).

The admin surface is the report-only anticheat UI (D13).  Pairs come
from the ``similarity_pairs`` table when populated by the worker (todo
35); when the table is empty for a scope, the API computes pairs
on-demand via ``pseint_judge.similarity.find_pairs`` and PERSISTS them
(batched insert, dedupe by ``(run_a_id, run_b_id)``) so subsequent
requests hit the cache.

Same-team pairs are excluded for ``scope=contest`` ONLY when
``contest.teams_enabled`` is true (M12/D16): when teams are disabled,
teams simply do not exist, so the predicate is a no-op.

The pair-detail endpoint (``/api/admin/anticheat/pair/:a/:b``) returns
the ORIGINAL sources plus a flag/score.  The D13 normalization
internals are deliberately NEVER exposed over the wire (MUST NOT,
plan §39): the diff UI (todo 25) renders the diff on the originals;
the server-side similarity score is the only signal it needs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pseint_judge.similarity import (
    DEFAULT_THRESHOLD as ENGINE_DEFAULT_THRESHOLD,
)
from pseint_judge.similarity import (
    TextSubmission,
    find_pairs,
)
from pseint_judge.similarity import (
    similarity as engine_similarity,
)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db, require_teacher
from ..models import (
    Assignment,
    Class,
    ClassMember,
    Contest,
    ContestTeam,
    ContestTeamMember,
    Run,
    SimilarityPair,
    User,
)

router = APIRouter(prefix="/api/classes/{class_id}")
admin_router = APIRouter(prefix="/api/admin")


# --- Response schemas --------------------------------------------------------


class SimilarityPairOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_a_id: int
    run_b_id: int
    score: float
    scope: str
    created_at: datetime


class AnticheatPairOut(BaseModel):
    """One pair from the anticheat report (todo 39).

    ``flagged`` is True iff the pair's score meets the effective
    threshold (caller's ``?threshold=`` override, falling back to the
    class default 0.85).  UI uses ``flagged`` to colour-code rows.
    """

    run_a_id: int
    run_b_id: int
    user_a_id: int
    user_a_username: str
    user_b_id: int
    user_b_username: str
    score: float
    scope: str
    flagged: bool


class AnticheatPairDetailRun(BaseModel):
    id: int
    user_id: int
    username: str
    problem_id: int
    kind: str


class AnticheatPairDetailOut(BaseModel):
    """Pair diff payload consumed by the teacher anticheat UI (todo 25).

    MUST NOT expose the D13 normalization internals over the wire (plan
    §39, MUST NOT).  The diff UI renders on the ORIGINAL sources
    verbatim; the server-side score and flag are the only signals the
    UI needs to colour the diff.
    """

    run_a: AnticheatPairDetailRun
    run_b: AnticheatPairDetailRun
    source_a: str
    source_b: str
    score: float
    flagged: bool
    threshold: float


class ThresholdUpdateRequest(BaseModel):
    threshold: float = Field(ge=0.0, le=1.0)


class ClassThresholdOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    teacher_id: int
    anticheat_threshold: float


# --- Internal pair-record shape (engine -> persistence) ----------------------


class _PairRow:
    """Lightweight bag used to feed ``_persist_pairs`` uniformly.

    The engine returns ``SimilarityPair`` dataclasses with string ids;
    the on-demand branch in ``get_anticheat_pair`` constructs one
    directly.  This avoids building SQLAlchemy ``SimilarityPair`` rows
    before persistence (which would prematurely commit).
    """

    __slots__ = ("run_a_id", "run_b_id", "score", "scope")

    def __init__(self, run_a_id: int, run_b_id: int, score: float, scope: str) -> None:
        self.run_a_id = run_a_id
        self.run_b_id = run_b_id
        self.score = score
        self.scope = scope


# --- Helpers -----------------------------------------------------------------


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


def _user_may_view_class(user: User, cls: Class) -> bool:
    return user.role == "admin" or cls.teacher_id == user.id


def _user_may_view_contest(user: User, contest: Contest) -> bool:
    return user.role == "admin" or contest.created_by == user.id


def _resolve_threshold(
    class_threshold: float | None, override: float | None
) -> float:
    """Threshold resolution (override > class default > engine default)."""
    if override is not None:
        return override
    if class_threshold is not None:
        return class_threshold
    return ENGINE_DEFAULT_THRESHOLD


def _user_team_in_contest(db: Session, user_id: int, contest_id: int) -> int | None:
    """Team id the user belongs to within ``contest_id`` (None if not in a team)."""
    team_id = db.scalar(
        select(ContestTeamMember.team_id)
        .join(ContestTeam, ContestTeam.id == ContestTeamMember.team_id)
        .where(
            ContestTeamMember.user_id == user_id,
            ContestTeam.contest_id == contest_id,
        )
    )
    return team_id


def _runs_to_subs(
    db: Session, runs: list[Run], contest_id: int | None
) -> list[TextSubmission]:
    """Map ORM ``Run`` rows to ``TextSubmission`` for the engine.

    ``team_id`` is the contest-team id the user belongs to (if any) so
    the engine's same-team exclusion (M12/D16) can skip teammates.  For
    class scope and contests without teams_enabled, ``team_id`` is None.
    """
    subs: list[TextSubmission] = []
    for run in runs:
        team_id: str | None = None
        if contest_id is not None:
            tid = _user_team_in_contest(db, run.user_id, contest_id)
            if tid is not None:
                team_id = str(tid)
        subs.append(
            TextSubmission(
                id=str(run.id),
                source=run.source,
                user_id=str(run.user_id),
                team_id=team_id,
            )
        )
    return subs


def _scope_runs(db: Session, scope: str, scope_id: int) -> list[Run]:
    """All runs participating in ``scope`` (``class`` or ``contest``)."""
    if scope == "class":
        member_ids = set(
            db.scalars(
                select(ClassMember.user_id).where(ClassMember.class_id == scope_id)
            ).all()
        )
        if not member_ids:
            return []
        return list(
            db.scalars(
                select(Run).where(Run.user_id.in_(member_ids)).order_by(Run.id)
            ).all()
        )
    if scope == "contest":
        return list(
            db.scalars(
                select(Run).where(Run.contest_id == scope_id).order_by(Run.id)
            ).all()
        )
    return []


def _persist_pairs(db: Session, pairs: list[_PairRow]) -> int:
    """Batch-insert ``pairs`` into ``similarity_pairs``, dedupe on (run_a, run_b).

    Returns the number of rows newly inserted; existing pairs are
    skipped (the plan §39 contract is "batch insert with dedupe").
    """
    if not pairs:
        return 0
    existing = {
        (row.run_a_id, row.run_b_id)
        for row in db.scalars(
            select(SimilarityPair.run_a_id, SimilarityPair.run_b_id)
        ).all()
    }
    inserted = 0
    for pair in pairs:
        key = (pair.run_a_id, pair.run_b_id)
        if key in existing:
            continue
        db.add(
            SimilarityPair(
                run_a_id=pair.run_a_id,
                run_b_id=pair.run_b_id,
                score=pair.score,
                scope=pair.scope,
            )
        )
        existing.add(key)
        inserted += 1
    if inserted:
        db.commit()
    return inserted


def _rows_to_pair_outs(
    db: Session, scope: str, score_threshold: float
) -> list[AnticheatPairOut]:
    """Read persisted pairs joined with run + user metadata; sort desc."""
    rows = db.execute(
        select(SimilarityPair)
        .where(SimilarityPair.scope == scope)
        .where(SimilarityPair.score >= score_threshold)
        .order_by(SimilarityPair.score.desc(), SimilarityPair.run_a_id)
    ).scalars().all()
    out: list[AnticheatPairOut] = []
    user_cache: dict[int, User] = {}
    for pair in rows:
        run_a = db.get(Run, pair.run_a_id)
        run_b = db.get(Run, pair.run_b_id)
        if run_a is None or run_b is None:
            continue
        user_a = user_cache.get(run_a.user_id)
        if user_a is None:
            user_a = db.get(User, run_a.user_id)
            if user_a is None:
                continue
            user_cache[run_a.user_id] = user_a
        user_b = user_cache.get(run_b.user_id)
        if user_b is None:
            user_b = db.get(User, run_b.user_id)
            if user_b is None:
                continue
            user_cache[run_b.user_id] = user_b
        out.append(
            AnticheatPairOut(
                run_a_id=run_a.id,
                run_b_id=run_b.id,
                user_a_id=user_a.id,
                user_a_username=user_a.username,
                user_b_id=user_b.id,
                user_b_username=user_b.username,
                score=pair.score,
                scope=pair.scope,
                flagged=pair.score >= score_threshold,
            )
        )
    return out


def _compute_and_persist(
    db: Session, scope: str, scope_id: int, threshold: float
) -> list[AnticheatPairOut]:
    """Compute pairs on-demand via the engine and persist; return as response rows."""
    runs = _scope_runs(db, scope, scope_id)
    contest_id: int | None = scope_id if scope == "contest" else None
    subs = _runs_to_subs(db, runs, contest_id)
    engine_pairs = find_pairs(subs, scope=scope, threshold=threshold)
    persistable = [
        _PairRow(
            run_a_id=int(p.run_a_id),
            run_b_id=int(p.run_b_id),
            score=p.score,
            scope=p.scope,
        )
        for p in engine_pairs
    ]
    _persist_pairs(db, persistable)
    return _rows_to_pair_outs(db, scope, threshold)


def _ensure_pairs(
    db: Session, scope: str, scope_id: int, threshold: float
) -> list[AnticheatPairOut]:
    """Return persisted pairs if any, else compute + persist, then read."""
    has_any = db.scalar(
        select(SimilarityPair.id).where(SimilarityPair.scope == scope).limit(1)
    )
    if has_any is not None:
        return _rows_to_pair_outs(db, scope, threshold)
    return _compute_and_persist(db, scope, scope_id, threshold)


# --- Class-scoped route (todo 18) -------------------------------------------


@router.get("/similarity", response_model=list[SimilarityPairOut])
def class_similarity(
    class_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    cls = db.get(Class, class_id)
    if cls is None:
        raise HTTPException(status_code=404, detail="Class not found")
    if not _user_may_view_class(user, cls):
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


# --- Admin anticheat routes (todo 39) ---------------------------------------


@admin_router.get("/anticheat", response_model=list[AnticheatPairOut])
def list_anticheat_pairs(
    scope: Literal["class", "contest"] = Query(...),
    scope_id: int = Query(..., ge=1),
    threshold: float | None = Query(default=None, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    """List anticheat pairs within a class or contest scope.

    ``threshold`` overrides the class default (plan §39, ``?threshold=``);
    when omitted, the class's ``anticheat_threshold`` is used (default
    0.85).  Pairs are returned in score-desc order so the strongest
    signal surfaces first in the teacher UI.

    Teacher access is scoped: a teacher may only view scopes they own
    (the class they teach, the contest they created); admins see all.
    """
    cls_threshold: float | None = None
    if scope == "class":
        cls = db.get(Class, scope_id)
        if cls is None:
            raise HTTPException(status_code=404, detail="Class not found")
        if not _user_may_view_class(user, cls):
            raise HTTPException(
                status_code=403,
                detail="Only the owning teacher can view this class",
            )
        cls_threshold = cls.anticheat_threshold
    else:
        contest = db.get(Contest, scope_id)
        if contest is None:
            raise HTTPException(status_code=404, detail="Contest not found")
        if not _user_may_view_contest(user, contest):
            raise HTTPException(
                status_code=403,
                detail="Only the owning teacher can view this contest",
            )

    effective_threshold = _resolve_threshold(cls_threshold, threshold)
    pairs = _ensure_pairs(db, scope, scope_id, effective_threshold)

    # Contest + teams_enabled → drop same-team pairs (defence-in-depth on
    # the cached table; the engine already excludes on compute).
    if scope == "contest":
        contest = db.get(Contest, scope_id)
        if contest is not None and contest.teams_enabled:
            pairs = [
                p
                for p in pairs
                if not _same_team(db, scope_id, p.user_a_id, p.user_b_id)
            ]
    return pairs


def _pair_scope_from_runs(db: Session, run_a: Run, run_b: Run) -> str:
    """Infer the ``similarity_pairs.scope`` value for a freshly computed pair.

    Any contest-bound run wins (matches the worker contract, todo 35).
    """
    if run_a.contest_id is not None or run_b.contest_id is not None:
        return "contest"
    return "class"


def _user_owns_pair(
    user: User, db: Session, run_a: Run, run_b: Run
) -> tuple[bool, Class | None, Contest | None]:
    """Resolve the access owner of a pair: class owner or contest owner.

    Returns ``(may_view, owning_class, owning_contest)``.  Admin is
    always ``may_view=True`` (handled at the call site).  Three paths
    grant access:

    1. The pair belongs to a contest the teacher created.
    2. The pair is bound to an assignment in a class the teacher teaches.
    3. Both runs' users are members of at least one class the teacher
       teaches (practice-mode fallback — runs with no assignment_id
       still surface in the report when both authors are the teacher's
       students).
    """
    for run in (run_a, run_b):
        if run.contest_id is not None:
            contest = db.get(Contest, run.contest_id)
            if contest is not None and _user_may_view_contest(user, contest):
                return True, None, contest

    for run in (run_a, run_b):
        if run.assignment_id is None:
            continue
        assignment = db.get(Assignment, run.assignment_id)
        if assignment is None:
            continue
        cls = db.get(Class, assignment.class_id)
        if cls is not None and _user_may_view_class(user, cls):
            return True, cls, None

    if user.role == "teacher":
        teacher_classes = list(
            db.scalars(select(Class).where(Class.teacher_id == user.id)).all()
        )
        if teacher_classes:
            for cls in teacher_classes:
                member_ids = set(
                    db.scalars(
                        select(ClassMember.user_id).where(
                            ClassMember.class_id == cls.id
                        )
                    ).all()
                )
                if (
                    run_a.user_id in member_ids
                    and run_b.user_id in member_ids
                ):
                    return True, cls, None

    return False, None, None


@admin_router.get(
    "/anticheat/pair/{run_a_id}/{run_b_id}", response_model=AnticheatPairDetailOut
)
def get_anticheat_pair(
    run_a_id: int,
    run_b_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    """Pair diff payload (todo 25 consumer).

    Returns the ORIGINAL sources (verbatim, never normalized) plus the
    server-computed score and a flag (above class default threshold).
    The D13 normalization internals are deliberately not exposed over
    the wire (MUST NOT, plan §39): the diff UI renders on the originals.

    Access rule: the teacher who owns the run's class or contest, or
    admin.  For contest runs, the contest creator; for class runs (via
    assignment), the assignment's class's teacher.
    """
    run_a = db.get(Run, run_a_id)
    run_b = db.get(Run, run_b_id)
    if run_a is None or run_b is None:
        raise HTTPException(status_code=404, detail="Run not found")

    may_view, owning_class, _owning_contest = _user_owns_pair(user, db, run_a, run_b)
    if user.role != "admin" and not may_view:
        raise HTTPException(
            status_code=403,
            detail="Not allowed to view this pair",
        )

    # Look up persisted pair (canonical order: lex-smaller id first).
    lo, hi = sorted((run_a_id, run_b_id))
    pair = db.scalar(
        select(SimilarityPair).where(
            SimilarityPair.run_a_id == lo,
            SimilarityPair.run_b_id == hi,
        )
    )
    if pair is not None:
        score = pair.score
    else:
        score = engine_similarity(run_a.source, run_b.source)
        scope = _pair_scope_from_runs(db, run_a, run_b)
        _persist_pairs(
            db,
            [_PairRow(run_a_id=lo, run_b_id=hi, score=score, scope=scope)],
        )

    threshold = (
        owning_class.anticheat_threshold
        if owning_class is not None
        else ENGINE_DEFAULT_THRESHOLD
    )

    user_a = db.get(User, run_a.user_id)
    user_b = db.get(User, run_b.user_id)
    if user_a is None or user_b is None:
        raise HTTPException(status_code=404, detail="User not found")

    return AnticheatPairDetailOut(
        run_a=AnticheatPairDetailRun(
            id=run_a.id,
            user_id=run_a.user_id,
            username=user_a.username,
            problem_id=run_a.problem_id,
            kind=run_a.kind,
        ),
        run_b=AnticheatPairDetailRun(
            id=run_b.id,
            user_id=run_b.user_id,
            username=user_b.username,
            problem_id=run_b.problem_id,
            kind=run_b.kind,
        ),
        source_a=run_a.source,
        source_b=run_b.source,
        score=score,
        flagged=score >= threshold,
        threshold=threshold,
    )


@admin_router.post(
    "/classes/{class_id}/anticheat-threshold",
    response_model=ClassThresholdOut,
)
def update_class_threshold(
    class_id: int,
    req: ThresholdUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_teacher),
):
    """Update a class's anticheat threshold (plan §39).

    Body: ``{"threshold": float}`` — Pydantic Field(ge=0.0, le=1.0)
    rejects out-of-range with 422 before the route runs.  Owning
    teacher or admin only.
    """
    cls = db.get(Class, class_id)
    if cls is None:
        raise HTTPException(status_code=404, detail="Class not found")
    if not _user_may_view_class(user, cls):
        raise HTTPException(
            status_code=403,
            detail="Only the owning teacher can update this class",
        )
    cls.anticheat_threshold = req.threshold
    db.commit()
    return cls
