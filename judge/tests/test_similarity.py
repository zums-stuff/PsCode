"""Tests for pseint_judge.similarity — anticheat text-similarity (todo 38).

Covers D13 (normalization), M12/D16 (same-team exclusion), the top-k
per-submission cap, threshold filtering, and dedupe — exactly the
QA scenarios the plan pins for the planted renamed-variable pair, the
bubble-vs-merge false-positive guard, and the threshold boundary.
"""

from __future__ import annotations

import pytest

from pseint_judge.similarity import (
    DEFAULT_THRESHOLD,
    DEFAULT_TOP_K,
    SCOPES,
    SimilarityPair,
    TextSubmission,
    batch_compute,
    find_pairs,
    normalize,
    similarity,
)

# ---------------------------------------------------------------------------
# Fixtures — sample programs used across multiple tests
# ---------------------------------------------------------------------------

COPY_TEMPLATE = """Proceso Suma
    suma <- 0
    Para i <- 1 Hasta n Hacer
        suma <- suma + i
    FinPara
    Escribir suma
FinProceso"""

COPY_WITH_RENAMES = """Proceso Suma
    total <- 0
    Para j <- 1 Hasta m Hacer
        total <- total + j
    FinPara
    Escribir total
FinProceso"""

BUBBLE_SORT = """Proceso Sort
    Para i <- 1 Hasta n-1 Hacer
        Para j <- 1 Hasta n-i Hacer
            Si A[j] > A[j+1] Entonces
                temp <- A[j]
                A[j] <- A[j+1]
                A[j+1] <- temp
            FinSi
        FinPara
    FinPara
FinProceso"""

MERGE_SORT = """Proceso Sort
    Si izq < der Entonces
        medio <- (izq+der)/2
        mergeSort(A, izq, medio)
        mergeSort(A, medio+1, der)
        merge(A, izq, medio, der)
    FinSi
FinProceso"""

IDENTICAL_HELLO = """Proceso Hola
    Escribir "Hola Mundo"
FinProceso"""


# ---------------------------------------------------------------------------
# Normalization (D13 — four steps)
# ---------------------------------------------------------------------------


class TestNormalize:
    """normalize() applies comments + ws + lowercase + identifier fold."""

    def test_strips_line_comments(self) -> None:
        """// comments are removed entirely (along with their line content)."""
        assert normalize("// this is a comment\nx <- 1\n") == "N<-1"

    def test_strips_all_whitespace(self) -> None:
        """Tabs, newlines, CR, runs of spaces — ALL collapse."""
        assert normalize("a\n\t  b\r\nc") == "NNN"

    def test_lowercases_before_folding(self) -> None:
        """Uppercase identifiers fold identically to lowercase ones."""
        assert normalize("SUMA <- 1\n") == "N<-1"

    def test_folds_identifiers_to_placeholder(self) -> None:
        """Every \\b[A-Za-z_]\\w*\\b becomes 'N'."""
        assert normalize("foo <- bar\n") == "N<-N"

    def test_full_pipeline(self) -> None:
        """All four steps applied in the spec order — pinned string."""
        # Comments stripped, lowercased, identifiers folded, ws stripped.
        src = "// Header\nSUMA <- 0\n// inline\nPara i <- 1 Hasta N\n"
        assert normalize(src) == "N<-0NN<-1NN"

    def test_empty_after_stripping(self) -> None:
        """Comment-only source normalizes to empty string."""
        assert normalize("// nothing but a comment\n") == ""


# ---------------------------------------------------------------------------
# similarity() — primitive ratio
# ---------------------------------------------------------------------------


class TestSimilarity:
    """similarity() wraps SequenceMatcher over the normalized forms."""

    def test_identical_sources_score_one(self) -> None:
        """Renamed-only copies normalize to the same string -> 1.0."""
        assert similarity(COPY_TEMPLATE, COPY_WITH_RENAMES) == 1.0

    def test_renamed_variable_pair_above_threshold(self) -> None:
        """The planted renamed-variable pair must score >= 0.85 (todo 38 QA)."""
        score = similarity(COPY_TEMPLATE, COPY_WITH_RENAMES)
        assert score >= 0.85, f"expected >= 0.85, got {score}"

    def test_different_algorithms_below_threshold(self) -> None:
        """Bubble vs merge sort must score < 0.85 (todo 38 QA — no false positive)."""
        score = similarity(BUBBLE_SORT, MERGE_SORT)
        assert score < 0.85, f"expected < 0.85, got {score}"

    def test_unrelated_sources_score_low(self) -> None:
        """Completely different programs produce a low score."""
        # Bubble sort vs the template suma — totally different control flow.
        score = similarity(BUBBLE_SORT, COPY_TEMPLATE)
        assert score < 0.5


# ---------------------------------------------------------------------------
# find_pairs() — exclusion rules
# ---------------------------------------------------------------------------


class TestFindPairsExclusions:
    """Same-team and explicit-exclude pairs are dropped."""

    def test_same_team_pair_excluded(self) -> None:
        """Two teammates with identical source -> no pair (M12/D16)."""
        subs = [
            TextSubmission(
                id="r1", source=IDENTICAL_HELLO, user_id="u1", team_id="TEAM1"
            ),
            TextSubmission(
                id="r2", source=IDENTICAL_HELLO, user_id="u2", team_id="TEAM1"
            ),
        ]
        assert find_pairs(subs, scope="contest") == []

    def test_different_teams_not_excluded(self) -> None:
        """Two runs on different teams with identical source DO flag."""
        subs = [
            TextSubmission(
                id="r1", source=IDENTICAL_HELLO, user_id="u1", team_id="TEAM1"
            ),
            TextSubmission(
                id="r2", source=IDENTICAL_HELLO, user_id="u2", team_id="TEAM2"
            ),
        ]
        pairs = find_pairs(subs, scope="contest")
        assert len(pairs) == 1
        assert pairs[0].score == 1.0
        assert pairs[0].scope == "contest"

    def test_explicit_exclude_pairs_dropped(self) -> None:
        """Pairs in exclude_team_pairs are skipped even with no team set."""
        subs = [
            TextSubmission(id="r1", source=IDENTICAL_HELLO, user_id="u1"),
            TextSubmission(id="r2", source=IDENTICAL_HELLO, user_id="u2"),
        ]
        pairs = find_pairs(
            subs, scope="class", exclude_team_pairs=[("r1", "r2")]
        )
        assert pairs == []

    def test_unknown_scope_raises(self) -> None:
        """scope outside SCOPES is a ValueError, not a silent empty list."""
        subs = [TextSubmission(id="r1", source="x", user_id="u1")]
        with pytest.raises(ValueError, match="unknown scope"):
            find_pairs(subs, scope="global")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# find_pairs() — threshold, top_k, dedupe
# ---------------------------------------------------------------------------


class TestFindPairsFiltering:
    """Threshold filter, top-k cap, dedupe of unordered input."""

    def test_threshold_drops_below_pairs(self) -> None:
        """Pairs below threshold are filtered out."""
        subs = [
            TextSubmission(id="A", source=COPY_TEMPLATE, user_id="uA"),
            TextSubmission(id="B", source=COPY_WITH_RENAMES, user_id="uB"),
            TextSubmission(id="C", source=MERGE_SORT, user_id="uC"),
        ]
        # Default 0.85 keeps only the renamed copy pair.
        default = find_pairs(subs, scope="problem")
        assert {(p.run_a_id, p.run_b_id) for p in default} == {("A", "B")}

        # Threshold 0.0 keeps every pair (none score 0 by construction,
        # but a low threshold catches everything above 0.0).
        lax = find_pairs(subs, scope="problem", threshold=0.0)
        assert {(p.run_a_id, p.run_b_id) for p in lax} == {
            ("A", "B"),
            ("A", "C"),
            ("B", "C"),
        }

    def test_top_k_per_submission_caps_partners(self) -> None:
        """With 4 identical subs and top_k=2, the LEAST-popular pair drops.

        X1..X4 all 1.0 with each other.  Per submission, top-2 keeps the
        two lex-smaller partners; only the pair where neither side's
        top-2 overlaps gets filtered out.  That pair is (X3, X4) because
        both X3 and X4 prefer their lex-smaller neighbors (X1, X2) when
        sorting ties.
        """
        subs = [
            TextSubmission(id=f"X{i}", source=IDENTICAL_HELLO, user_id=f"u{i}")
            for i in range(1, 5)
        ]
        pairs = find_pairs(subs, scope="problem", top_k=2)
        pair_ids = {(p.run_a_id, p.run_b_id) for p in pairs}
        # 4 subs -> C(4,2) = 6 possible; exactly 1 dropped.
        assert len(pairs) == 5
        assert ("X3", "X4") not in pair_ids

    def test_dedupe_unordered_input(self) -> None:
        """find_pairs is order-independent AND collapses duplicate ids."""
        a = TextSubmission(id="A", source=IDENTICAL_HELLO, user_id="uA")
        b = TextSubmission(id="B", source=IDENTICAL_HELLO, user_id="uB")

        forward = find_pairs([a, b], scope="problem")
        reversed_ = find_pairs([b, a], scope="problem")
        with_duplicate = find_pairs([a, a, b], scope="problem")

        assert forward == reversed_
        assert forward == with_duplicate
        assert len(forward) == 1
        # Canonical form: lex-smaller id first.
        assert forward[0].run_a_id == "A"
        assert forward[0].run_b_id == "B"

    def test_results_sorted_by_score_desc(self) -> None:
        """Highest score first — the teacher UI relies on this ordering."""
        subs = [
            TextSubmission(id="X1", source=IDENTICAL_HELLO, user_id="u1"),
            TextSubmission(id="X2", source=IDENTICAL_HELLO, user_id="u2"),
            TextSubmission(id="X3", source=IDENTICAL_HELLO, user_id="u3"),
            TextSubmission(id="X4", source=IDENTICAL_HELLO, user_id="u4"),
        ]
        pairs = find_pairs(subs, scope="problem")
        scores = [p.score for p in pairs]
        assert scores == sorted(scores, reverse=True)

    def test_default_threshold_and_top_k(self) -> None:
        """Module constants are exported and reachable from outside."""
        assert DEFAULT_THRESHOLD == 0.85
        assert DEFAULT_TOP_K == 5
        assert SCOPES == frozenset({"class", "contest", "problem"})


# ---------------------------------------------------------------------------
# Records + batch entry point
# ---------------------------------------------------------------------------


class TestRecordsAndBatch:
    """SimilarityPair shape + batch_compute delegation."""

    def test_similarity_pair_fields_pinned(self) -> None:
        """Dataclass fields match the schema from todo 16."""
        p = SimilarityPair(
            run_a_id="run_a", run_b_id="run_b", score=0.9, scope="class"
        )
        assert p.run_a_id == "run_a"
        assert p.run_b_id == "run_b"
        assert p.score == 0.9
        assert p.scope == "class"

    def test_batch_compute_delegates_to_find_pairs(self) -> None:
        """batch_compute is the worker's stable call surface — same result."""
        subs = [
            TextSubmission(id="r1", source=IDENTICAL_HELLO, user_id="u1"),
            TextSubmission(id="r2", source=IDENTICAL_HELLO, user_id="u2"),
        ]
        assert batch_compute(subs, scope="problem") == find_pairs(
            subs, scope="problem"
        )

    def test_batch_compute_passes_scope_through(self) -> None:
        """Scope flows through batch_compute to every emitted pair."""
        subs = [
            TextSubmission(id="r1", source=IDENTICAL_HELLO, user_id="u1"),
            TextSubmission(id="r2", source=IDENTICAL_HELLO, user_id="u2"),
        ]
        pairs = batch_compute(subs, scope="contest")
        assert all(p.scope == "contest" for p in pairs)

    def test_planted_pair_via_find_pairs(self) -> None:
        """End-to-end: the renamed-copy pair appears in find_pairs output."""
        subs = [
            TextSubmission(id="r1", source=COPY_TEMPLATE, user_id="u1"),
            TextSubmission(id="r2", source=COPY_WITH_RENAMES, user_id="u2"),
            TextSubmission(id="r3", source=MERGE_SORT, user_id="u3"),
        ]
        pairs = find_pairs(subs, scope="problem")
        assert {(p.run_a_id, p.run_b_id) for p in pairs} == {("r1", "r2")}
        assert pairs[0].score >= 0.85
