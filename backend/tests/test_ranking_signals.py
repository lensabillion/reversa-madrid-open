"""Ranking context, ties and semantic input validation without inferred publication."""

import math

import pytest

from influence.services.ranking_signals import (
    RankedPair,
    background_signals,
    cosine,
    feature_vector,
)


def test_background_competition_ranks_and_input_order_invariance() -> None:
    rows = [
        RankedPair("a", "am1", "ask1", 0.9),
        RankedPair("b", "am1", "ask2", 0.9),
        RankedPair("c", "am1", "ask3", 0.3),
        RankedPair("d", "am2", "ask1", 0.95),
    ]
    actual = background_signals(rows)
    assert actual == background_signals(rows[::-1])
    assert actual["a"]["forward_reciprocal_rank"] == 1
    assert actual["c"]["forward_reciprocal_rank"] == 1 / 3
    assert actual["a"]["reverse_reciprocal_rank"] == 0.5
    assert actual["a"]["mutual_reciprocal_rank"] == 2 / 3
    assert sum(row["background_z"] for row in actual.values()) == pytest.approx(0)
    assert sum(row["background_z"] ** 2 for row in actual.values()) / 4 == pytest.approx(1)


def test_constant_empty_and_invalid_backgrounds() -> None:
    assert background_signals([]) == {}
    row = RankedPair("a", "am", "ask", 0.4)
    assert background_signals([row])["a"]["background_z"] == 0
    with pytest.raises(ValueError, match="unique"):
        background_signals([row, row])
    with pytest.raises(ValueError, match="finite"):
        background_signals([RankedPair("a", "am", "ask", math.nan)])


def test_cosine_and_invalid_embeddings() -> None:
    assert cosine([1, 0], [1, 0]) == 1
    assert cosine([1, 0], [0, 1]) == 0
    assert cosine([1, 0], [-1, 0]) == -1
    assert cosine([1e308, 1e308], [1e-300, 1e-300]) == pytest.approx(1)
    for left, right in (([], []), ([1], [1, 2]), ([math.nan], [1]), ([0], [1])):
        with pytest.raises(ValueError, match=r"embedding|Embedding"):
            cosine(left, right)


def test_feature_schema_never_silently_drops_missing_signals() -> None:
    assert feature_vector({"a": 2, "b": 3}, ["b", "a"]) == (3, 2)
    with pytest.raises(KeyError):
        feature_vector({"a": 2}, ["missing"])
    for names in ([], ["a", "a"]):
        with pytest.raises(ValueError, match="unique"):
            feature_vector({"a": 2}, names)
    with pytest.raises(ValueError, match="finite"):
        feature_vector({"a": math.inf}, ["a"])
