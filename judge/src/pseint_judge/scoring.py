"""Scoring engines for the judge (todo 14).

Pure functions — no DB.  Computes scoreboard rows from submission records
(dataclasses).  The API layer (todo 18+) persists and calls these functions.

Three modes, never mixed (the caller passes ``mode`` explicitly — it is never
inferred from the submissions):

- ``"cf"``:         Codeforces-style.  A problem is solved iff ANY submission
                    is AC; penalty = sum(AC_time_min) + 20 x wrong attempts on
                    SOLVED problems; rank solves desc, penalty asc.
- ``"ioi"``:        IOI-style.  Points per problem = MAX points across that
                    participant's submissions; total = sum; rank points desc.
- ``"assignment"``: Best submission per problem (max AC cases, tie-break min
                    steps); resubmissions allowed until the deadline.

Teams (CF/IOI): when a locked ``roster`` is supplied, participants are teams.
CF solve_time = first AC by any member; wrong attempts = union of team
attempts.  IOI team points = max over members (per problem).  The roster is
locked once the contest starts — the caller passes the frozen roster and no
mid-contest edits are honoured (members not in the roster are ignored).

Pinned scoring edges (plan §14, normative):
- penalty time = whole minutes since contest ``start_at`` (floored).
- wrong-attempt count EXCLUDES attempts before ``start_at``, attempts after a
  problem's first AC, and infra retries (``Submission.retry``).
- same-score ranks are STABLE: equal scores share the same rank number
  (competition ranking, e.g. 1,1,3).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

MODES = frozenset({"cf", "ioi", "assignment"})

# Wrong-attempt penalty per wrong attempt on a solved problem (CF).
CF_WRONG_PENALTY = 20


@dataclass(frozen=True)
class Submission:
    """One graded submission (the per-case verdict record scoring consumes).

    ``verdict`` is the overall verdict (AC/WA/TLE/RE/CE).  ``points`` carries
    the IOI per-case points; ``ac_cases``/``steps`` drive assignment best.
    ``retry`` marks an infra retry (excluded from CF wrong-attempt counting).
    """

    id: str
    user_id: str
    problem_id: str
    submitted_at: datetime
    verdict: str
    points: float = 0.0
    ac_cases: int = 0
    steps: int = 0
    team_id: str | None = None
    retry: bool = False


@dataclass(frozen=True)
class ProblemResult:
    """Per-problem scoring detail for one participant."""

    problem_id: str
    solved: bool = False
    solve_time_min: int = 0
    wrong_attempts: int = 0
    points: float = 0.0
    best_ac_cases: int = 0
    best_steps: int = 0
    best_submission_id: str | None = None


@dataclass(frozen=True)
class ScoreboardRow:
    """One participant's (or team's) scoreboard row."""

    participant_id: str
    rank: int = 0
    solves: int = 0
    penalty: int = 0
    points: float = 0.0
    total_ac_cases: int = 0
    problems: dict[str, ProblemResult] = field(default_factory=dict)


@dataclass(frozen=True)
class Scoreboard:
    """Ordered scoreboard (by rank) with participant lookup.

    Carries the full ``submissions`` set it was computed from so that
    recompute is ALWAYS possible (nothing is frozen) — the scoreboard.py
    ``apply_submission`` hook relies on this.
    """

    mode: str
    rows: tuple[ScoreboardRow, ...]
    submissions: tuple[Submission, ...] = ()
    _by_participant: dict[str, ScoreboardRow] = field(default_factory=dict)

    def by_participant(self, participant_id: str) -> ScoreboardRow:
        return self._by_participant[participant_id]


def _whole_minutes(t: datetime, start_at: datetime) -> int:
    """Whole (floored) minutes from ``start_at`` to ``t``, never negative."""
    delta = t - start_at
    return max(0, int(delta.total_seconds() // 60))


def _cf_participant(
    participant_id: str, subs: list[Submission], start_at: datetime
) -> ScoreboardRow:
    by_problem: dict[str, list[Submission]] = {}
    for s in subs:
        by_problem.setdefault(s.problem_id, []).append(s)

    solves = 0
    penalty = 0
    problems: dict[str, ProblemResult] = {}
    for pid, psubs in by_problem.items():
        ac = [s for s in psubs if s.verdict == "AC"]
        solved = bool(ac)
        solve_time_min = 0
        wrong = 0
        if solved:
            first_ac = min(s.submitted_at for s in ac)
            solve_time_min = _whole_minutes(first_ac, start_at)
            # Wrong attempts: non-AC, non-retry, >= start_at, before first AC.
            wrong = sum(
                1
                for s in psubs
                if s.verdict != "AC"
                and not s.retry
                and s.submitted_at >= start_at
                and s.submitted_at < first_ac
            )
            solves += 1
            penalty += solve_time_min + CF_WRONG_PENALTY * wrong
        else:
            # Unsolved: wrong attempts don't affect penalty, but report them.
            wrong = sum(
                1
                for s in psubs
                if s.verdict != "AC" and not s.retry and s.submitted_at >= start_at
            )
        problems[pid] = ProblemResult(
            problem_id=pid,
            solved=solved,
            solve_time_min=solve_time_min,
            wrong_attempts=wrong,
        )
    return ScoreboardRow(
        participant_id=participant_id, solves=solves, penalty=penalty, problems=problems
    )


def _ioi_participant(
    participant_id: str, subs: list[Submission]
) -> ScoreboardRow:
    by_problem: dict[str, list[Submission]] = {}
    for s in subs:
        by_problem.setdefault(s.problem_id, []).append(s)

    total = 0.0
    problems: dict[str, ProblemResult] = {}
    for pid, psubs in by_problem.items():
        pts = max(s.points for s in psubs)
        total += pts
        problems[pid] = ProblemResult(problem_id=pid, points=pts)
    return ScoreboardRow(
        participant_id=participant_id, points=total, problems=problems
    )


def _assignment_participant(
    participant_id: str, subs: list[Submission], deadline: datetime
) -> ScoreboardRow:
    by_problem: dict[str, list[Submission]] = {}
    for s in subs:
        if s.submitted_at <= deadline:
            by_problem.setdefault(s.problem_id, []).append(s)

    total_ac = 0
    problems: dict[str, ProblemResult] = {}
    for pid, psubs in by_problem.items():
        best = max(psubs, key=lambda s: (s.ac_cases, -s.steps))
        total_ac += best.ac_cases
        problems[pid] = ProblemResult(
            problem_id=pid,
            best_ac_cases=best.ac_cases,
            best_steps=best.steps,
            best_submission_id=best.id,
        )
    return ScoreboardRow(
        participant_id=participant_id, total_ac_cases=total_ac, problems=problems
    )


def _assign_ranks(rows: list[ScoreboardRow], key_fn) -> list[ScoreboardRow]:
    """Competition ranking: equal keys share a rank; next rank skips (1,1,3)."""
    result: list[ScoreboardRow] = []
    rank = 1
    prev_key = None
    for i, row in enumerate(rows):
        key = key_fn(row)
        if i == 0 or key != prev_key:
            rank = i + 1
        result.append(replace(row, rank=rank))
        prev_key = key
    return result


def compute_scoreboard(
    submissions: list[Submission],
    *,
    mode: str,
    start_at: datetime | None = None,
    roster: dict[str, set[str]] | None = None,
    deadline: datetime | None = None,
) -> Scoreboard:
    """Compute the full scoreboard for ``submissions`` under ``mode``.

    ``mode`` is REQUIRED and never inferred.  ``start_at`` is required for
    ``cf``; ``deadline`` is required for ``assignment``.  When ``roster`` is
    supplied (teams enabled), participants are the roster's teams and only
    locked-roster members' submissions count.
    """
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode!r}")
    if mode == "cf" and start_at is None:
        raise ValueError("cf mode requires start_at")
    if mode == "assignment" and deadline is None:
        raise ValueError("assignment mode requires deadline")

    if roster is not None:
        participants: dict[str, list[Submission]] = {}
        for team_id, members in roster.items():
            participants[team_id] = [
                s for s in submissions if s.team_id == team_id and s.user_id in members
            ]
    else:
        participants = {}
        for s in submissions:
            participants.setdefault(s.user_id, []).append(s)

    rows: list[ScoreboardRow] = []
    for pid, subs in participants.items():
        if mode == "cf":
            rows.append(_cf_participant(pid, subs, start_at))
        elif mode == "ioi":
            rows.append(_ioi_participant(pid, subs))
        else:
            rows.append(_assignment_participant(pid, subs, deadline))

    if mode == "cf":
        rows.sort(key=lambda r: (-r.solves, r.penalty))
        rows = _assign_ranks(rows, lambda r: (r.solves, r.penalty))
    elif mode == "ioi":
        rows.sort(key=lambda r: (-r.points,))
        rows = _assign_ranks(rows, lambda r: (r.points,))
    else:
        rows.sort(key=lambda r: (-r.total_ac_cases,))
        rows = _assign_ranks(rows, lambda r: (r.total_ac_cases,))

    by_participant = {r.participant_id: r for r in rows}
    return Scoreboard(
        mode=mode,
        rows=tuple(rows),
        submissions=tuple(submissions),
        _by_participant=by_participant,
    )
