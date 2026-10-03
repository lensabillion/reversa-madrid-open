"""Grouped folds: no organization, amendment text or submission text crosses a split.

Review finding R4: a scorer must not be tested on an organization, amendment or passage it
saw in training. Each labelled pair links its organization, its amendment text and its
submission text. The first choice is connected components over those links: whole
components go to one fold, so nothing can cross. When there are fewer components than
folds, or one holds more than a fold's share of the positives (on LobbyPlag one holds 170
of 172), components cannot make k useful folds. Then the test groups are organizations,
joined wherever two organizations submitted an identical input (the same amendment text
and the same submission text, after `text_key`), so a duplicated input is never tested in
two folds; every training pair that shares an amendment or submission text with the test
fold is withheld from that fold's training data ("purged"). Either way no organization or
text appears on both sides of a train/test split, and no identical input sits in two test
folds (so neither in both the development and held-out halves of `calibrate.py`); the
fallback pays for it with smaller training sets, which the report counts. A single shared
amendment or submission text may still appear in two test folds when its pairs differ in
the other text: joining on single texts would rebuild the dominant component.
"""

from collections import defaultdict
from collections.abc import Callable, Hashable, Iterable, Sequence
from dataclasses import dataclass
from math import ceil
from typing import Literal

from influence.practice.labels import (
    LabelledPair,
    PracticeDataError,
    PracticePair,
    input_key,
    text_key,
)

type Grouping = Literal["connected_components", "organizations_with_purge"]
type Link = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class Fold:
    """Indices into the labelled pairs. `purged` pairs are in neither `test` nor `train`."""

    test: tuple[int, ...]
    train: tuple[int, ...]
    purged: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ComponentSize:
    positives: int
    negatives: int
    organizations: int
    amendments: int


@dataclass(frozen=True, slots=True)
class FoldPlan:
    grouping: Grouping
    components: tuple[ComponentSize, ...]
    folds: tuple[Fold, ...]


def links(pair: PracticePair) -> tuple[Link, Link, Link]:
    return (
        ("organization", pair.organization_id, ""),
        ("amendment", *text_key(pair.amendment)),
        ("submission", *text_key(pair.submission)),
    )


def connected_components(
    pairs: Sequence[PracticePair],
    keys: Callable[[PracticePair], Iterable[Hashable]] = links,
) -> list[list[int]]:
    """Union-find with path halving over each pair's hashed `keys`: O(n log n) amortized."""
    parent = list(range(len(pairs)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    first: dict[Hashable, int] = {}
    for index, pair in enumerate(pairs):
        for link in keys(pair):
            parent[root(index)] = root(first.setdefault(link, index))
    members: defaultdict[int, list[int]] = defaultdict(list)
    for index in range(len(pairs)):
        members[root(index)].append(index)
    return list(members.values())


def organization_groups(pair: PracticePair) -> tuple[Hashable, Hashable]:
    """An organization and its exact input: pairs sharing either belong to one test group."""
    return ("organization", pair.organization_id), ("input", input_key(pair))


def _assign(groups: list[list[int]], pairs: Sequence[LabelledPair], k: int) -> list[list[int]]:
    """Largest group first, into the fold with the fewest positives: O(G log G + G k).

    Groups without positives balance negatives instead. Ties fall to the smaller fold, then
    the lower index; the group order breaks its own ties by smallest candidate identifier,
    so the result does not depend on input order.
    """

    def positives(group: list[int]) -> int:
        return sum(pairs[index].influenced for index in group)

    ordered = sorted(
        groups,
        key=lambda group: (
            -positives(group),
            -len(group),
            min(pairs[index].pair.candidate_id for index in group),
        ),
    )
    folds: list[list[int]] = [[] for _ in range(k)]
    fold_positives = [0] * k
    for group in ordered:
        count = positives(group)
        target = min(
            range(k),
            key=lambda fold: (
                fold_positives[fold] if count else len(folds[fold]) - fold_positives[fold],
                len(folds[fold]),
                fold,
            ),
        )
        folds[target].extend(group)
        fold_positives[target] += count
    return [sorted(fold) for fold in folds]


def make_folds(pairs: Sequence[LabelledPair], k: int) -> FoldPlan:
    """Assign every pair to exactly one test fold; O(k n) for the purge.

    Raises `PracticeDataError` when there are fewer groups than folds, so no fold is empty.
    The fallback's groups are organizations joined by identical inputs (module docstring).
    """
    if k < 2:
        raise ValueError(f"Need at least 2 folds, got {k}")
    texts = [item.pair for item in pairs]
    components = connected_components(texts)
    largest = max((sum(pairs[i].influenced for i in group) for group in components), default=0)
    grouping: Grouping
    if len(components) >= k and largest <= ceil(sum(item.influenced for item in pairs) / k):
        grouping, groups = "connected_components", components
    else:
        grouping = "organizations_with_purge"
        groups = connected_components(texts, organization_groups)
    if len(groups) < k:
        raise PracticeDataError(f"{len(groups)} independent groups cannot fill {k} folds")
    folds: list[Fold] = []
    for test in _assign(groups, pairs, k):
        tested = set(test)
        test_links = {link for index in test for link in links(texts[index])}
        train: list[int] = []
        purged: list[int] = []
        for index, pair in enumerate(texts):
            if index not in tested:
                (purged if test_links.intersection(links(pair)) else train).append(index)
        folds.append(Fold(test=tuple(test), train=tuple(train), purged=tuple(purged)))
    sizes = [
        ComponentSize(
            positives=sum(pairs[i].influenced for i in group),
            negatives=sum(not pairs[i].influenced for i in group),
            organizations=len({texts[i].organization_id for i in group}),
            amendments=len({texts[i].amendment_id for i in group}),
        )
        for group in components
    ]
    sizes.sort(key=lambda size: (-size.positives - size.negatives, -size.positives))
    return FoldPlan(grouping=grouping, components=tuple(sizes), folds=tuple(folds))
