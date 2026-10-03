"""Grouped folds: nothing crosses a split, on fixed and on generated link graphs."""

import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from practice_fixture import labelled, links_of

from influence.practice.folds import FoldPlan, connected_components, make_folds, organization_groups
from influence.practice.labels import LabelledPair, PracticeDataError, input_key

PROPERTY = settings(derandomize=True, database=None, deadline=None, max_examples=300)


def _members(pairs: list[LabelledPair], plan: FoldPlan) -> list[set[str]]:
    return [{pairs[index].pair.candidate_id for index in fold.test} for fold in plan.folds]


def test_independent_organizations_become_whole_components() -> None:
    pairs = [
        labelled(f"org{org}", f"{org}-{item}", f"{org}-{item}", item < 2, f"c{org}-{item}")
        for org in range(4)
        for item in range(3)
    ]
    plan = make_folds(pairs, 2)
    assert plan.grouping == "connected_components"
    assert [(size.positives, size.negatives) for size in plan.components] == [(2, 1)] * 4
    assert [sorted({pairs[i].pair.organization_id for i in fold.test}) for fold in plan.folds] == [
        ["org0", "org2"],
        ["org1", "org3"],
    ]
    assert all(fold.purged == () and len(fold.train) == 6 for fold in plan.folds)


def test_a_dominant_component_falls_back_to_organizations_and_purges() -> None:
    # Every organization proposed a change to amendment "shared", which links them all.
    pairs = [labelled("big", f"big-{item}", f"big-{item}", True, f"b{item}") for item in range(6)]
    pairs += [
        labelled(
            f"org{org}", "shared" if org < 2 else f"own-{org}", f"s{org}", org % 2 == 0, f"o{org}"
        )
        for org in range(4)
    ]
    pairs.append(labelled("big", "shared", "big-shared", False, "b-shared"))
    plan = make_folds(pairs, 3)
    assert plan.grouping == "organizations_with_purge"
    assert plan.components[0].positives == 7
    assert plan.components[0].organizations == 3
    tested = _members(pairs, plan)
    assert {"b0", "b-shared"} <= tested[0]
    # Organizations org0 and org1 share amendment "shared" with the big fold: each fold
    # withholds the other's pair from training rather than letting the text cross.
    for fold in plan.folds:
        assert links_of(pairs, fold.test).isdisjoint(links_of(pairs, fold.train))
    assert sum(len(fold.purged) for fold in plan.folds) > 0


def test_fewer_components_than_folds_fall_back_to_organizations() -> None:
    # Found by the property below: two organizations share one text, so they form a single
    # component, yet as two organizations they can still fill two folds.
    pairs = [labelled("org0", "a0", "s0", False, "c0"), labelled("org1", "a0", "s1", False, "c1")]
    plan = make_folds(pairs, 2)
    assert plan.grouping == "organizations_with_purge"
    assert _members(pairs, plan) == [{"c0"}, {"c1"}]
    assert all(fold.train == () and len(fold.purged) == 1 for fold in plan.folds)


def test_an_identical_input_from_two_organizations_stays_in_one_test_fold() -> None:
    # Review finding: under the fallback, the same (amendment, submission) text submitted by
    # two organizations was tested in two folds, so it sat in both the development and the
    # held-out half of the calibration. Identical inputs now join their organizations.
    # Grouped by organization alone, org0 and org1 went to folds 1 and 2.
    pairs = [labelled("big", f"big-{item}", f"big-{item}", True, f"b{item}") for item in range(4)]
    pairs += [labelled("big", "shared", "big-shared", False, "b-shared")]
    pairs += [labelled(f"org{org}", "a-dup", "s-dup", True, f"dup{org}") for org in range(2)]
    pairs += [labelled("org4", "shared", "s4", False, "o4")]
    plan = make_folds(pairs, 3)
    assert plan.grouping == "organizations_with_purge"
    assert _members(pairs, plan) == [
        {"b0", "b1", "b2", "b3", "b-shared"},
        {"dup0", "dup1"},
        {"o4"},
    ]
    two_identical = [
        labelled("org0", "a0", "s0", False, "c0"),
        labelled("org1", "a0", "s0", True, "c1"),
    ]
    with pytest.raises(PracticeDataError, match="1 independent groups cannot fill 2 folds"):
        make_folds(two_identical, 2)


def test_too_few_groups_or_folds_are_rejected() -> None:
    pairs = [labelled("only", str(item), str(item), item % 2 == 0, f"c{item}") for item in range(4)]
    with pytest.raises(PracticeDataError, match="1 independent groups cannot fill 2 folds"):
        make_folds(pairs, 2)
    with pytest.raises(ValueError, match="at least 2 folds"):
        make_folds(pairs, 1)


LINKS = st.lists(
    st.tuples(st.integers(0, 5), st.integers(0, 7), st.integers(0, 7), st.booleans()),
    min_size=1,
    max_size=40,
)


@PROPERTY
@given(LINKS, st.integers(2, 4), st.randoms(use_true_random=False))
def test_no_organization_or_text_crosses_a_split(
    links: list[tuple[int, int, int, bool]], k: int, rng: random.Random
) -> None:
    pairs = [
        labelled(f"org{org}", f"a{amendment}", f"s{submission}", influenced, f"c{index:02}")
        for index, (org, amendment, submission, influenced) in enumerate(links)
    ]
    try:
        plan = make_folds(pairs, k)
    except PracticeDataError:
        assert len(connected_components([item.pair for item in pairs], organization_groups)) < k
        return
    every = sorted(index for fold in plan.folds for index in fold.test)
    assert every == list(range(len(pairs)))
    for fold in plan.folds:
        assert fold.test
        assert sorted((*fold.test, *fold.train, *fold.purged)) == list(range(len(pairs)))
        assert links_of(pairs, fold.test).isdisjoint(links_of(pairs, fold.train))
    # An identical input is tested in exactly one fold.
    folds_of_input: dict[object, set[int]] = {}
    for number, fold in enumerate(plan.folds):
        for index in fold.test:
            folds_of_input.setdefault(input_key(pairs[index].pair), set()).add(number)
    assert all(len(numbers) == 1 for numbers in folds_of_input.values())
    if plan.grouping == "connected_components":
        assert all(fold.purged == () for fold in plan.folds)
    # The same data in another order yields the same folds.
    shuffled = pairs.copy()
    rng.shuffle(shuffled)
    again = make_folds(shuffled, k)
    assert again.grouping == plan.grouping
    assert _members(shuffled, again) == _members(pairs, plan)
