"""Entity resolution: the layer that fired is recorded, and ambiguity stays unresolved."""

import pytest
from extraction_fixtures import make_actor

from influence.extraction.names import (
    FUZZY_THRESHOLD,
    UNRESOLVED,
    ActorIndex,
    normalise,
    token_set_ratio,
    tokenise,
)

CCIA = make_actor("1", "Computer and Communications Industry Association", "CCIA")
BEUC = make_actor("2", "Bureau Europeen des Unions de Consommateurs", "BEUC")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Example Tech GmbH", "example tech"),
        ("The European Association of Example, e.V.", "association example"),
        ("EXAMPLE-TECH  (Brussels)", "example tech brussels"),
        ("The", ""),
    ],
)
def test_normalisation_strips_legal_suffixes_punctuation_and_filler(
    raw: str, expected: str
) -> None:
    assert normalise(raw) == expected


def test_tokenise_keeps_order_so_the_normalised_key_is_stable() -> None:
    assert tokenise("Example Tech Ltd") == ("example", "tech")


def test_token_set_ratio_ignores_word_order_and_is_zero_when_nothing_remains() -> None:
    assert token_set_ratio("Alpha Beta Systems", "Systems Beta Alpha") == 1.0
    assert token_set_ratio("The European", "Alpha") == 0.0


def test_a_registration_id_resolves_without_looking_at_the_name() -> None:
    index = ActorIndex.build([CCIA, BEUC])
    resolution = index.resolve("however it was typed", registration_id="2")
    assert (resolution.actor_id, resolution.method, resolution.score) == (
        "2",
        "registration_id",
        1.0,
    )


def test_an_unknown_registration_id_falls_through_to_the_name_layers() -> None:
    index = ActorIndex.build([CCIA])
    resolution = index.resolve("Computer and Communications Industry Association", "999")
    assert (resolution.actor_id, resolution.method) == ("1", "normalised_exact")


def test_an_acronym_only_submission_resolves_through_the_acronym_index() -> None:
    index = ActorIndex.build([CCIA, BEUC])
    resolution = index.resolve("BEUC")
    assert (resolution.actor_id, resolution.method) == ("2", "acronym")


def test_a_name_that_normalises_to_nothing_is_unresolved_rather_than_guessed() -> None:
    assert ActorIndex.build([CCIA]).resolve("The") == UNRESOLVED


def test_an_actor_whose_own_name_normalises_to_nothing_is_indexed_by_id_only() -> None:
    index = ActorIndex.build([make_actor("3", "The")])
    assert index.by_name == {}
    assert index.by_id["3"].name == "The"


@pytest.mark.parametrize("raw_name", ["Computer and Communications Industry Association", "CCIA"])
def test_two_entries_sharing_a_name_or_acronym_are_reported_ambiguous(raw_name: str) -> None:
    twin = make_actor("1b", "Computer and Communications Industry Association", "CCIA")
    resolution = ActorIndex.build([CCIA, twin]).resolve(raw_name)
    assert (resolution.actor_id, resolution.method) == (None, "ambiguous")


def test_a_near_match_resolves_fuzzily_and_records_the_score_it_scored() -> None:
    resolution = ActorIndex.build([CCIA, BEUC]).resolve("Computer & Communications Industry Assoc.")
    assert resolution.actor_id == "1"
    assert resolution.method == "fuzzy"
    assert resolution.score is not None
    assert FUZZY_THRESHOLD <= resolution.score < 1.0


def test_a_name_below_the_threshold_is_left_unresolved() -> None:
    assert ActorIndex.build([CCIA, BEUC]).resolve("Greenpeace") == UNRESOLVED


def test_two_equally_similar_actors_are_ambiguous_rather_than_resolved_by_order() -> None:
    first = make_actor("4", "Alpha Beta Gamma Deltax")
    second = make_actor("5", "Gamma Beta Alpha Deltax")
    resolution = ActorIndex.build([first, second]).resolve("Alpha Beta Gamma Deltaxx")
    assert (resolution.actor_id, resolution.method) == (None, "ambiguous")
    assert resolution.score is not None
    assert resolution.score >= FUZZY_THRESHOLD


def test_an_empty_register_resolves_nothing_instead_of_failing() -> None:
    assert ActorIndex.build([]).resolve("Example Association") == UNRESOLVED
