"""The hidden test's metrics: hand-computed examples, then invariants on generated inputs."""

import math
import random
from collections.abc import Callable

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from influence.practice.metrics import auc, precision_at_k, recall_at, summarize

# Derandomized: every run tries the same examples, and a failure prints the one that failed.
PROPERTY = settings(derandomize=True, database=None, deadline=None, max_examples=300)

# Scores on a coarse grid, so ties are common and strictly increasing maps stay exact.
GRID = st.integers(min_value=0, max_value=20).map(lambda step: step / 20)


@st.composite
def labelled_scores(draw: st.DrawFn) -> tuple[list[float], list[bool]]:
    """At least one real pair and one decoy, in random order."""
    real = draw(st.lists(GRID, min_size=1, max_size=30))
    decoys = draw(st.lists(GRID, min_size=1, max_size=30))
    rows = draw(st.permutations([(score, True) for score in real] + [(s, False) for s in decoys]))
    return [score for score, _ in rows], [label for _, label in rows]


def test_precision_at_k_breaks_ties_by_the_supplied_order() -> None:
    scores, influenced = [0.9, 0.8, 0.8, 0.1], [True, False, True, False]
    assert precision_at_k(scores, influenced, 2, [0, 1, 2, 3]) == 0.5
    assert precision_at_k(scores, influenced, 2, [0, 2, 1, 3]) == 1.0
    assert precision_at_k(scores, influenced, 4, [3, 2, 1, 0]) == 0.5


def test_recall_counts_a_score_equal_to_the_threshold_as_found() -> None:
    assert recall_at([0.5, 0.49, 0.9], [True, True, False], 0.5) == 0.5
    assert recall_at([0.5, 0.49, 0.9], [True, True, False], 0.49) == 1.0


def test_auc_counts_a_tie_as_one_half() -> None:
    # Real pairs 0.9 and 0.5 against decoys 0.5 and 0.1: wins 1 + 1 + 1, one tie.
    assert auc([0.9, 0.5, 0.5, 0.1], [True, True, False, False]) == 3.5 / 4
    assert auc([0.2, 0.2], [True, False]) == 0.5


def test_summary_is_the_mean_and_tenth_percentile() -> None:
    summary = summarize([float(value) for value in range(1, 12)])
    assert (summary.mean, summary.p10) == (6.0, 2.0)
    assert summarize([0.25]).p10 == 0.25


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: auc([0.1], [True, False]), "one label per score"),
        (lambda: auc([], []), "one label per score"),
        (lambda: auc([math.nan, 0.1], [True, False]), "finite"),
        (lambda: auc([0.1, 0.2], [True, True]), "one real pair and one decoy"),
        (lambda: recall_at([0.1], [False], 0.5), "at least one real pair"),
        (lambda: precision_at_k([0.1], [True], 2, [0]), "1 <= k"),
        (lambda: precision_at_k([0.1, 0.2], [True, False], 1, [0]), "tie-break"),
        (lambda: summarize([]), "no values"),
    ],
)
def test_invalid_inputs_are_rejected(call: Callable[[], object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        call()


@PROPERTY
@given(labelled_scores())
def test_auc_matches_the_pairwise_definition(rows: tuple[list[float], list[bool]]) -> None:
    scores, influenced = rows
    real = [s for s, label in zip(scores, influenced, strict=True) if label]
    decoys = [s for s, label in zip(scores, influenced, strict=True) if not label]
    wins = sum((r > d) + 0.5 * (r == d) for r in real for d in decoys)
    value = auc(scores, influenced)
    assert 0 <= value <= 1
    assert math.isclose(value, wins / (len(real) * len(decoys)), abs_tol=1e-12)


@PROPERTY
@given(labelled_scores())
def test_negating_scores_reverses_auc(rows: tuple[list[float], list[bool]]) -> None:
    # Holds with ties too: a tie counts one half in both directions.
    scores, influenced = rows
    negated = auc([-score for score in scores], influenced)
    assert math.isclose(negated, 1 - auc(scores, influenced), abs_tol=1e-12)


@PROPERTY
@given(labelled_scores(), GRID, st.randoms(use_true_random=False))
def test_metrics_ignore_strictly_increasing_transforms(
    rows: tuple[list[float], list[bool]], threshold: float, rng: random.Random
) -> None:
    scores, influenced = rows
    cubed = [score**3 for score in scores]
    order = list(range(len(scores)))
    rng.shuffle(order)
    k = min(20, len(scores))
    assert precision_at_k(cubed, influenced, k, order) == precision_at_k(
        scores, influenced, k, order
    )
    assert recall_at(cubed, influenced, threshold**3) == recall_at(scores, influenced, threshold)
    assert auc(cubed, influenced) == auc(scores, influenced)
