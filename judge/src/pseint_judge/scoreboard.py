"""Scoreboard recompute + nightly reconcile hook (todo 14, M12).

``apply_submission`` takes the previous scoreboard plus a new/changed
submission and returns the updated scoreboard.  Recompute is ALWAYS possible
(no frozen scoreboards): the function re-runs the full computation over the
previous submissions plus the new one — the previous ``Scoreboard`` carries
its full submission set for exactly this purpose.

Recompute trigger per mode (documented here; the API layer, todo 18+, decides
when to call ``apply_submission``):
- ``cf``:         an AC flip — a submission becoming AC changes solved-state.
- ``ioi``:        a per-case point delta — a submission changing points.
- ``assignment``: a best-rating change — a submission beating the current best
                  (more AC cases, or equal cases with fewer steps).

``reconcile`` is the nightly batch hook (M12): a full recompute from ALL
submissions, independent of any previous scoreboard.  It is the source of
truth that corrects any drift in the live-recomputed scoreboards.
"""

from __future__ import annotations

from datetime import datetime

from pseint_judge.scoring import Submission, compute_scoreboard


def apply_submission(
    prev,
    submission: Submission,
    *,
    mode: str,
    start_at: datetime | None = None,
    roster: dict[str, set[str]] | None = None,
    deadline: datetime | None = None,
):
    """Return the scoreboard after adding ``submission`` to ``prev``.

    Recomputes from scratch over ``prev.submissions`` plus the new submission
    — recompute is always possible, nothing is frozen.  ``prev`` must be a
    ``Scoreboard`` produced by ``compute_scoreboard`` (it carries the full
    submission set).  Mode and config are passed explicitly, never inferred.
    """
    all_subs = list(prev.submissions) + [submission]
    return compute_scoreboard(
        all_subs,
        mode=mode,
        start_at=start_at,
        roster=roster,
        deadline=deadline,
    )


def reconcile(
    submissions: list[Submission],
    *,
    mode: str,
    start_at: datetime | None = None,
    roster: dict[str, set[str]] | None = None,
    deadline: datetime | None = None,
):
    """Nightly batch hook (M12): full recompute from ALL submissions.

    Independent of any previous scoreboard — the authoritative recompute that
    corrects drift in the live-recomputed scoreboards.
    """
    return compute_scoreboard(
        submissions,
        mode=mode,
        start_at=start_at,
        roster=roster,
        deadline=deadline,
    )
