"""Text-level similarity engine for the anticheat report (todo 38).

REPORT-ONLY.  Never flags, never penalises, never auto-rejects (D13).
The teacher UI surfaces the pair list verbatim; only humans decide what
to do with it.

Pipeline
--------
    source  ->  normalize  ->  difflib.SequenceMatcher.ratio  ->  score

Normalization (D13, NORMATIVE)
------------------------------
Four transformations are applied:

1. Strip ``//`` line comments (everything from ``//`` to end of line).
2. Lowercase.
3. Fold identifier tokens to ``"N"`` via
   ``re.sub(r"\\b[A-Za-z_]\\w*\\b", "N", ...)`` so renamed variables
   collapse (``i`` -> ``j``, ``n`` -> ``m``, ``suma`` -> ``total``
   all match).
4. Strip ALL whitespace (incl. ``\\n``, ``\\r``, ``\\t``).

Order matters: folding MUST happen before whitespace is stripped,
otherwise ``\\b[A-Za-z_]\\w*\\b`` misses identifiers glued to
adjacent digits (e.g. ``0Para`` after strip has no word boundary
between ``0`` and ``P``).  Comments are stripped first so a ``//``
inside a string literal cannot swallow the rest of the line.

Same-team pairs are EXCLUDED (M12/D16).  Pairs below the threshold
(default ``0.85``, configurable per class via the API in todo 39) are
DROPPED.  Top-k per submission (default ``5``) caps each submission's
partner list; each pair is reported ONCE in canonical (lex-smaller id
first) ordering.

This module is PURE: no DB writes, no IO, no async.  The API layer
(todo 39) persists the result; the worker (todo 35) calls
``batch_compute``.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Constants — pinned by plan §38 and D13
# ---------------------------------------------------------------------------

# Single-line comment marker for PseInt (per SPEC).  The full dialect also
# supports ``/* ... */`` block comments but the anticheat shortcut per D13
# only handles ``//`` — block comments are rare in student submissions and
# would slip past comment-stripping (intentional simplification).
_COMMENT_RE = re.compile(r"//[^\n]*")

# Fold every identifier-shaped token to the placeholder ``N``.  Word
# boundaries (``\b``) keep operators/punctuation from being absorbed.
_IDENT_RE = re.compile(r"\b[A-Za-z_]\w*\b")

# Default cut-off below which a pair is dropped (D13, plan §38).
DEFAULT_THRESHOLD = 0.85

# Default per-submission cap; each submission keeps its top-k partners
# by score (tie-break by canonical pair id).
DEFAULT_TOP_K = 5

# Module-level scope labels (mirrors the ``similarity_pairs.scope`` enum
# in the API's schema, todo 16).
SCOPES = frozenset({"class", "contest", "problem"})


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SimilarityPair:
    """One ordered (canonical) similarity pair within a scope.

    Mirrors the ``similarity_pairs`` schema columns from todo 16:
    ``run_a_id`` / ``run_b_id`` are FKs into ``runs``; ``scope`` is the
    enum ``class`` | ``contest`` | ``problem``; ``score`` is in
    ``[0.0, 1.0]``.  ``run_a_id`` is ALWAYS lex-smaller than
    ``run_b_id`` — the canonical form that dedupes unordered input.
    """

    run_a_id: str
    run_b_id: str
    score: float
    scope: str


@dataclass(frozen=True)
class TextSubmission:
    """Minimum record needed for similarity analysis.

    ``source`` is the program text AS WRITTEN — normalization happens
    inside the function, the API layer never sends pre-normalized text.
    ``team_id`` enables same-team exclusion (M12/D16): when both sides
    share a non-None team, the pair is skipped.
    """

    id: str
    source: str
    user_id: str
    team_id: str | None = None


# ---------------------------------------------------------------------------
# Normalization + scoring primitives
# ---------------------------------------------------------------------------


def normalize(source: str) -> str:
    """Apply the four-step normalization (D13).

    Order: comments -> lowercase -> identifier fold -> whitespace strip.

    Folding BEFORE whitespace strip is required so the regex catches
    every identifier (whitespace is the boundary between tokens;
    strip it first and adjacent identifier/digit runs merge with no
    ``\\b`` boundary).  Lowercasing before folding keeps the
    placeholder ``N`` uppercase while collapsing ``SUMA`` and ``suma``
    to the same token.

    The output is a single line of folded characters suitable for
    ``difflib.SequenceMatcher`` (which operates on hashable sequences).
    """
    no_comments = _COMMENT_RE.sub("", source)
    folded = _IDENT_RE.sub("N", no_comments.lower())
    return re.sub(r"\s+", "", folded)


def similarity(a: str, b: str) -> float:
    """SequenceMatcher ratio over normalized forms (D13).

    Returns a float in ``[0.0, 1.0]`` — ``difflib``'s ratio is
    ``2 * M / T`` where ``M`` is matching characters and ``T`` is total
    characters.  Identical normalized sources -> ``1.0``; no overlap ->
    ``0.0``.
    """
    return difflib.SequenceMatcher(None, normalize(a), normalize(b)).ratio()


# ---------------------------------------------------------------------------
# Pair-finding
# ---------------------------------------------------------------------------


def _canonical(a: str, b: str) -> tuple[str, str]:
    """Return (smaller, larger) of the two ids — pair canonical form."""
    return (a, b) if a < b else (b, a)


def find_pairs(
    submissions: Iterable[TextSubmission],
    *,
    scope: str,
    exclude_team_pairs: Iterable[tuple[str, str]] | None = None,
    threshold: float = DEFAULT_THRESHOLD,
    top_k: int = DEFAULT_TOP_K,
) -> list[SimilarityPair]:
    """Find high-similarity pairs within ``scope``.

    Pairs are EXCLUDED if:

    * both submissions share a non-None ``team_id`` (M12/D16), or
    * the pair appears in ``exclude_team_pairs`` (either direction).

    Pairs are DROPPED if ``score < threshold``.

    Top-k per submission: each submission keeps its best ``top_k``
    partners by score (tie-break by canonical ``(run_a_id, run_b_id)``).
    A pair survives the cap if EITHER side kept the other — the
    union, deduped by canonical key, is returned.

    Returns pairs sorted by ``(-score, run_a_id, run_b_id)`` so the
    highest-similarity pair surfaces first in the teacher UI.
    """
    if scope not in SCOPES:
        raise ValueError(
            f"unknown scope: {scope!r} (expected one of {sorted(SCOPES)})"
        )

    subs = list(submissions)
    extra_exclude: set[frozenset[str]] = set()
    if exclude_team_pairs is not None:
        for a, b in exclude_team_pairs:
            extra_exclude.add(frozenset({a, b}))

    # Pass 1 — compute scores, apply exclusions + threshold filter.
    raw: list[SimilarityPair] = []
    for i in range(len(subs)):
        left = subs[i]
        for j in range(i + 1, len(subs)):
            right = subs[j]
            if left.id == right.id:
                continue
            if left.team_id is not None and left.team_id == right.team_id:
                continue
            key = frozenset({left.id, right.id})
            if key in extra_exclude:
                continue
            score = similarity(left.source, right.source)
            if score < threshold:
                continue
            a, b = _canonical(left.id, right.id)
            raw.append(SimilarityPair(run_a_id=a, run_b_id=b, score=score, scope=scope))

    # Pass 2 — top-k per submission.  Each pair is indexed against BOTH
    # of its submissions; a pair survives if either side kept it.
    partners: dict[str, list[SimilarityPair]] = {}
    for p in raw:
        partners.setdefault(p.run_a_id, []).append(p)
        partners.setdefault(p.run_b_id, []).append(p)

    keep: set[tuple[str, str]] = set()
    for plist in partners.values():
        plist.sort(key=lambda p: (-p.score, p.run_a_id, p.run_b_id))
        for p in plist[:top_k]:
            keep.add((p.run_a_id, p.run_b_id))

    # Final dedupe (canonical ordering already collapses pairs, but
    # safeguard against duplicate inputs) + sort.
    seen: set[tuple[str, str]] = set()
    result: list[SimilarityPair] = []
    for p in raw:
        k = (p.run_a_id, p.run_b_id)
        if k not in keep or k in seen:
            continue
        seen.add(k)
        result.append(p)
    result.sort(key=lambda p: (-p.score, p.run_a_id, p.run_b_id))
    return result


def batch_compute(
    submissions: Iterable[TextSubmission],
    *,
    scope: str,
    exclude_team_pairs: Iterable[tuple[str, str]] | None = None,
    threshold: float = DEFAULT_THRESHOLD,
    top_k: int = DEFAULT_TOP_K,
) -> list[SimilarityPair]:
    """Batch entry point for the anticheat worker (todo 35).

    Pure delegation to ``find_pairs``.  Exists as a stable call surface
    so the worker can attach logging, parallelism, or pre/post hooks
    here without changing call sites.
    """
    return find_pairs(
        submissions,
        scope=scope,
        exclude_team_pairs=exclude_team_pairs,
        threshold=threshold,
        top_k=top_k,
    )
