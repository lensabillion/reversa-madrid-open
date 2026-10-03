"""The hidden test's metrics, as pure functions of parallel scores and labels.

At 19:00 the organizers rank 60 pairs (30 real influence, 30 lookalike decoys) by our
score. Precision in the top k is the share of real pairs among our k highest scores; recall
is the share of real pairs whose score reaches the threshold; AUC is the probability that a
random real pair outscores a random decoy. `influenced[i]` is True for a real pair.
"""

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import groupby
from operator import itemgetter


@dataclass(frozen=True, slots=True)
class Summary:
    mean: float
    p10: float


def _check(scores: Sequence[float], influenced: Sequence[bool]) -> None:
    if len(scores) != len(influenced) or not scores:
        raise ValueError("Need one label per score, and at least one score")
    if not all(map(math.isfinite, scores)):
        raise ValueError("Scores must be finite")


def precision_at_k(
    scores: Sequence[float], influenced: Sequence[bool], k: int, tie_order: Sequence[int]
) -> float:
    """Ties at the cut fall by `tie_order` (lower first), which callers draw at random.

    Random tie-breaking stops a scorer that gives many pairs one score from being credited
    with the input order. O(n log n).
    """
    _check(scores, influenced)
    if not 1 <= k <= len(scores) or len(tie_order) != len(scores):
        raise ValueError("Need 1 <= k <= len(scores) and one tie-break key per score")
    ranked = sorted(range(len(scores)), key=lambda index: (-scores[index], tie_order[index]))
    return sum(influenced[index] for index in ranked[:k]) / k


def recall_at(scores: Sequence[float], influenced: Sequence[bool], threshold: float) -> float:
    """The organizers have not said how recall is computed (decision D5), so the threshold
    is a parameter; 0.5 is the assumption until they answer.
    """
    _check(scores, influenced)
    real = [score for score, label in zip(scores, influenced, strict=True) if label]
    if not real:
        raise ValueError("Recall needs at least one real pair")
    return sum(score >= threshold for score in real) / len(real)


def auc(scores: Sequence[float], influenced: Sequence[bool]) -> float:
    """Mann-Whitney AUC from mid-ranks, so a tie counts one half. O(n log n)."""
    _check(scores, influenced)
    positives = sum(influenced)
    negatives = len(influenced) - positives
    if not positives or not negatives:
        raise ValueError("AUC needs at least one real pair and one decoy")
    rank_sum = 0.0
    position = 0
    for _, tied in groupby(sorted(zip(scores, influenced, strict=True)), key=itemgetter(0)):
        labels = [label for _, label in tied]
        rank_sum += (position + (len(labels) + 1) / 2) * sum(labels)
        position += len(labels)
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def summarize(values: Sequence[float]) -> Summary:
    """Mean and 10th percentile (linear interpolation, as numpy's default)."""
    if not values:
        raise ValueError("Cannot summarize no values")
    return Summary(
        mean=statistics.fmean(values),
        p10=statistics.quantiles(values, n=10, method="inclusive")[0],
    )
