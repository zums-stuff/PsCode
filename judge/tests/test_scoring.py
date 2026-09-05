"""Tests for pseint_judge.scoring + pseint_judge.scoreboard (todo 14).

TDD suite covering CF-style, IOI-style and assignment-best scoring with
teams, tie-breaks, and the pinned scoring edges (penalty minutes, wrong-attempt
exclusions, roster lock).  Also covers the scoreboard recompute triggers and
the nightly reconcile hook (M12).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from pseint_judge.scoreboard import apply_submission, reconcile
from pseint_judge.scoring import (
    Submission,
    compute_scoreboard,
)

T0 = datetime(2026, 9, 1, 9, 0, 0)


def _sub(
    sid: str,
    user: str,
    problem: str,
    minutes: int,
    verdict: str = "WA",
    *,
    points: float = 0.0,
    ac_cases: int = 0,
    steps: int = 0,
    team: str | None = None,
    retry: bool = False,
) -> Submission:
    return Submission(
        id=sid,
        user_id=user,
        problem_id=problem,
        submitted_at=T0 + timedelta(minutes=minutes),
        verdict=verdict,
        points=points,
        ac_cases=ac_cases,
        steps=steps,
        team_id=team,
        retry=retry,
    )


class TestCFPenaltyArithmetic:
    """CF penalty = sum(AC_time_min) + 20 x wrong attempts on solved problems."""

    def test_two_solves_one_wrong_each_penalty_80(self) -> None:
        subs = [
            _sub("s1", "u1", "P1", 5, "WA"),
            _sub("s2", "u1", "P1", 10, "AC"),
            _sub("s3", "u1", "P2", 25, "WA"),
            _sub("s4", "u1", "P2", 30, "AC"),
        ]
        sb = compute_scoreboard(subs, mode="cf", start_at=T0)
        row = sb.by_participant("u1")
        assert row.solves == 2
        # (10 + 20*1) + (30 + 20*1) = 30 + 50 = 80
        assert row.penalty == 80


class TestCFRank:
    """CF rank: solves desc, penalty asc."""

    def test_two_solves_beats_one_solve(self) -> None:
        subs = [
            _sub("a1", "A", "P1", 10, "AC"),
            _sub("a2", "A", "P2", 30, "AC"),
            _sub("b1", "B", "P1", 5, "AC"),
        ]
        sb = compute_scoreboard(subs, mode="cf", start_at=T0)
        # A: 2 solves / 40min penalty; B: 1 solve / 5min penalty.
        assert sb.by_participant("A").rank == 1
        assert sb.by_participant("B").rank == 2


class TestCFWrongAttemptExclusions:
    """Wrong attempts after first AC and before start_at are excluded."""

    def test_wrong_attempt_after_first_ac_excluded(self) -> None:
        subs = [
            _sub("s1", "u1", "P1", 5, "WA"),
            _sub("s2", "u1", "P1", 10, "AC"),
            _sub("s3", "u1", "P1", 15, "WA"),  # after AC -> excluded
        ]
        sb = compute_scoreboard(subs, mode="cf", start_at=T0)
        row = sb.by_participant("u1")
        assert row.solves == 1
        assert row.penalty == 10 + 20 * 1  # only the pre-AC WA counts

    def test_wrong_attempt_before_start_at_excluded(self) -> None:
        subs = [
            _sub("s1", "u1", "P1", -5, "WA"),  # before start_at -> excluded
            _sub("s2", "u1", "P1", 10, "AC"),
        ]
        sb = compute_scoreboard(subs, mode="cf", start_at=T0)
        row = sb.by_participant("u1")
        assert row.solves == 1
        assert row.penalty == 10  # no wrong attempts counted

    def test_infra_retry_excluded_from_wrong_attempts(self) -> None:
        subs = [
            _sub("s1", "u1", "P1", 5, "WA", retry=True),  # infra retry -> excluded
            _sub("s2", "u1", "P1", 10, "AC"),
        ]
        sb = compute_scoreboard(subs, mode="cf", start_at=T0)
        row = sb.by_participant("u1")
        assert row.penalty == 10  # retry not counted as a wrong attempt


class TestCFTeams:
    """CF team: solve_time = first AC by any member; wrong = union of attempts."""

    def test_member_wa_then_teammate_ac(self) -> None:
        subs = [
            _sub("s1", "A", "P1", 5, "WA", team="T1"),
            _sub("s2", "B", "P1", 10, "AC", team="T1"),
        ]
        roster = {"T1": {"A", "B"}}
        sb = compute_scoreboard(subs, mode="cf", start_at=T0, roster=roster)
        row = sb.by_participant("T1")
        assert row.solves == 1
        # solve_time = B's AC at 10min; penalty includes A's WA.
        assert row.penalty == 10 + 20 * 1

    def test_roster_locked_ignores_unknown_member(self) -> None:
        # C is not in the locked roster -> its submissions don't count for T1.
        subs = [
            _sub("s1", "A", "P1", 5, "WA", team="T1"),
            _sub("s2", "C", "P1", 10, "AC", team="T1"),
        ]
        roster = {"T1": {"A", "B"}}
        sb = compute_scoreboard(subs, mode="cf", start_at=T0, roster=roster)
        row = sb.by_participant("T1")
        assert row.solves == 0  # C not in roster -> no AC counts


class TestIOIMaxPoints:
    """IOI points per problem = MAX points across submissions."""

    def test_max_points_across_submissions(self) -> None:
        subs = [
            _sub("s1", "u1", "P1", 1, "WA", points=60),
            _sub("s2", "u1", "P1", 2, "WA", points=80),
            _sub("s3", "u1", "P1", 3, "WA", points=70),
        ]
        sb = compute_scoreboard(subs, mode="ioi")
        row = sb.by_participant("u1")
        assert row.points == 80


class TestIOIRank:
    """IOI rank: points desc."""

    def test_points_desc_rank(self) -> None:
        subs = [
            _sub("a1", "A", "P1", 1, "AC", points=100),
            _sub("b1", "B", "P1", 1, "WA", points=80),
        ]
        sb = compute_scoreboard(subs, mode="ioi")
        assert sb.by_participant("A").rank == 1
        assert sb.by_participant("B").rank == 2


class TestIOITeams:
    """IOI team points = max over members (per problem)."""

    def test_team_ioi_is_max_over_members(self) -> None:
        subs = [
            _sub("s1", "A", "P1", 1, "WA", points=60, team="T1"),
            _sub("s2", "B", "P1", 2, "WA", points=80, team="T1"),
        ]
        roster = {"T1": {"A", "B"}}
        sb = compute_scoreboard(subs, mode="ioi", roster=roster)
        row = sb.by_participant("T1")
        assert row.points == 80


class TestAssignmentBest:
    """Assignment best: max AC cases, tie-break min steps."""

    def test_max_ac_cases_tiebreak_min_steps(self) -> None:
        subs = [
            _sub("s1", "u1", "P1", 1, ac_cases=3, steps=100),
            _sub("s2", "u1", "P1", 2, ac_cases=5, steps=200),
            _sub("s3", "u1", "P1", 3, ac_cases=5, steps=150),
        ]
        sb = compute_scoreboard(
            subs, mode="assignment", deadline=T0 + timedelta(hours=1)
        )
        row = sb.by_participant("u1")
        best = row.problems["P1"]
        # s3 wins: 5 cases, 150 steps < 200.
        assert best.best_submission_id == "s3"
        assert best.best_ac_cases == 5
        assert best.best_steps == 150

    def test_submissions_after_deadline_excluded(self) -> None:
        subs = [
            _sub("s1", "u1", "P1", 30, ac_cases=5, steps=100),
            _sub("s2", "u1", "P1", 90, ac_cases=7, steps=50),  # after deadline
        ]
        sb = compute_scoreboard(
            subs, mode="assignment", deadline=T0 + timedelta(minutes=60)
        )
        row = sb.by_participant("u1")
        assert row.problems["P1"].best_submission_id == "s1"  # s2 excluded


class TestCFTieBreak:
    """CF tie-break: solves desc, penalty asc."""

    def test_solves_desc_then_penalty_asc(self) -> None:
        subs = [
            _sub("a1", "A", "P1", 10, "AC"),
            _sub("a2", "A", "P2", 30, "AC"),  # A: 2 solves / 40
            _sub("b1", "B", "P1", 10, "AC"),
            _sub("b2", "B", "P2", 50, "AC"),  # B: 2 solves / 60
            _sub("c1", "C", "P1", 5, "AC"),  # C: 1 solve / 5
        ]
        sb = compute_scoreboard(subs, mode="cf", start_at=T0)
        assert sb.by_participant("A").rank == 1  # 2 solves, lower penalty
        assert sb.by_participant("B").rank == 2  # 2 solves, higher penalty
        assert sb.by_participant("C").rank == 3  # 1 solve


class TestSameScoreRanksStable:
    """Equal scores share the same rank number (1,1,3 convention)."""

    def test_equal_scores_share_rank(self) -> None:
        subs = [
            _sub("a1", "A", "P1", 10, "AC"),
            _sub("b1", "B", "P1", 10, "AC"),  # same solve + penalty as A
            _sub("c1", "C", "P1", 5, "AC"),  # lower penalty -> rank 1
        ]
        sb = compute_scoreboard(subs, mode="cf", start_at=T0)
        # C: 1 solve / 5min -> rank 1. A and B: 1 solve / 10min -> rank 2,2.
        assert sb.by_participant("C").rank == 1
        assert sb.by_participant("A").rank == 2
        assert sb.by_participant("B").rank == 2

    def test_ioi_equal_points_share_rank(self) -> None:
        subs = [
            _sub("a1", "A", "P1", 1, "AC", points=100),
            _sub("b1", "B", "P1", 1, "AC", points=100),
            _sub("c1", "C", "P1", 1, "WA", points=50),
        ]
        sb = compute_scoreboard(subs, mode="ioi")
        assert sb.by_participant("A").rank == 1
        assert sb.by_participant("B").rank == 1
        assert sb.by_participant("C").rank == 3


class TestIOIPartialUpdate:
    """A later WA changing IOI points moves the row; CF solved-state unchanged."""

    def test_ioi_row_moves_cf_solved_state_stays(self) -> None:
        subs = [
            _sub("a1", "A", "P1", 1, "WA", points=80),
            _sub("b1", "B", "P1", 1, "AC", points=100),
        ]
        # IOI: B(100) r1, A(80) r2. CF: A unsolved, B solved.
        ioi = compute_scoreboard(subs, mode="ioi")
        cf = compute_scoreboard(subs, mode="cf", start_at=T0)
        assert ioi.by_participant("A").rank == 2
        assert cf.by_participant("A").solves == 0
        assert cf.by_participant("B").solves == 1

        # A later submits a WA with higher partial points (105, still not AC).
        new_subs = subs + [_sub("a2", "A", "P1", 5, "WA", points=105)]
        ioi2 = compute_scoreboard(new_subs, mode="ioi")
        cf2 = compute_scoreboard(new_subs, mode="cf", start_at=T0)
        # IOI: A now 105 -> rank 1, B 100 -> rank 2. Row moved.
        assert ioi2.by_participant("A").rank == 1
        assert ioi2.by_participant("B").rank == 2
        # CF: A still unsolved (no AC), B still solved. Solved-state unchanged.
        assert cf2.by_participant("A").solves == 0
        assert cf2.by_participant("B").solves == 1


class TestScoreboardRecompute:
    """apply_submission recomputes on any verdict/points change; reconcile full."""

    def test_apply_submission_recomputes_cf(self) -> None:
        subs = [_sub("s1", "u1", "P1", 10, "AC")]
        sb = compute_scoreboard(subs, mode="cf", start_at=T0)
        assert sb.by_participant("u1").solves == 1

        # A new AC on P2 flips the row.
        new = _sub("s2", "u1", "P2", 20, "AC")
        sb2 = apply_submission(sb, new, mode="cf", start_at=T0)
        assert sb2.by_participant("u1").solves == 2

    def test_apply_submission_recomputes_ioi(self) -> None:
        subs = [_sub("s1", "u1", "P1", 1, "WA", points=60)]
        sb = compute_scoreboard(subs, mode="ioi")
        assert sb.by_participant("u1").points == 60

        new = _sub("s2", "u1", "P1", 2, "WA", points=90)
        sb2 = apply_submission(sb, new, mode="ioi")
        assert sb2.by_participant("u1").points == 90

    def test_reconcile_full_recompute(self) -> None:
        subs = [
            _sub("s1", "u1", "P1", 10, "AC"),
            _sub("s2", "u2", "P1", 5, "AC"),
        ]
        sb = reconcile(subs, mode="cf", start_at=T0)
        assert sb.by_participant("u1").solves == 1
        assert sb.by_participant("u2").solves == 1
        # u2 has lower penalty -> rank 1.
        assert sb.by_participant("u2").rank == 1
        assert sb.by_participant("u1").rank == 2


class TestModeIsExplicit:
    """Mode is always passed in; never inferred from the submissions."""

    def test_same_submissions_scored_differently_by_mode(self) -> None:
        subs = [
            _sub("s1", "u1", "P1", 10, "AC", points=100, ac_cases=5, steps=50),
        ]
        cf = compute_scoreboard(subs, mode="cf", start_at=T0)
        ioi = compute_scoreboard(subs, mode="ioi")
        assignment = compute_scoreboard(
            subs, mode="assignment", deadline=T0 + timedelta(hours=1)
        )
        assert cf.by_participant("u1").solves == 1
        assert ioi.by_participant("u1").points == 100
        assert assignment.by_participant("u1").problems["P1"].best_ac_cases == 5

    def test_unknown_mode_raises(self) -> None:
        with pytest.raises(ValueError):
            compute_scoreboard([], mode="bogus")
