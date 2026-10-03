"""Actor resolution: which evidence makes an identity and which only proposes one."""

from itertools import permutations

from influence.repositories.register import RegisterEntry, to_actor
from influence.schemas.atlas import CITIZENS_ACTOR_ID, Actor, ActorAlias
from influence.services.actors import (
    ABSENT_FROM_REGISTER,
    ActorResolver,
    merge_actors,
    resolution_summary,
)

BEUC = RegisterEntry(
    register_id="9505781573-45",
    name="Bureau Européen des Unions de Consommateurs",
    acronym="BEUC",
    country="BELGIUM",
    country_code="BEL",
    category="Non-governmental organisations",
    members="Acme Robotics; Verbraucherzentrale Bundesverband",
)
FAIR_TRIALS_EUROPE = RegisterEntry(
    register_id="302540016347-29", name="Fair Trials Europe", country_code="BEL"
)
SIEMENS = RegisterEntry(
    register_id="974875639237-65", name="Siemens Energy AG", acronym="SE", country_code="DEU"
)
GREEK = RegisterEntry(
    register_id="111111111111-11",
    name="Αρχέλων",
    latin_name="Archelon Turtle Society",
    country_code="GRC",
)
# Two registrations under one name, and two unrelated bodies sharing one acronym.
GREENPEACE_ONE = RegisterEntry(register_id="222222222222-01", name="Greenpeace", acronym="GP")
GREENPEACE_TWO = RegisterEntry(register_id="222222222222-02", name="Greenpeace e.V.", acronym="GP")
# A name made only of filler words: reachable by its ID, never by its name.
FILLER = RegisterEntry(register_id="333333333333-33", name="The European", acronym=".")

WIND = "Northern Renewable Energy Producers Association Network"
WIND_CLOSE = RegisterEntry(
    register_id="444444444444-01", name=f"{WIND}s", country_code="DNK", acronym=None
)
WIND_REORDERED = RegisterEntry(
    register_id="444444444444-02",
    name="Network Association Producers Energy Renewable Northern",
    country_code="DNK",
)
WIND_CLOSE_LATER = RegisterEntry(
    register_id="444444444444-03",
    name="Northern Renewable Energy Producers Associations Networks",
)
WIND_FAR = RegisterEntry(
    register_id="444444444444-04",
    name="Northern Renewable Energy Consumers Federation Bureau",
)
WIND_SHORT = RegisterEntry(register_id="444444444444-05", name="Northern Bank")
WIND_ABROAD = RegisterEntry(
    register_id="444444444444-06",
    name="Association Network Producers Energy Renewable Northern",
    country_code="NOR",
)

REGISTER = (BEUC, FAIR_TRIALS_EUROPE, SIEMENS, GREEK, GREENPEACE_ONE, GREENPEACE_TWO, FILLER)
RESOLVER = ActorResolver.build(REGISTER)


def resolve(
    name: str | None,
    register_id: str | None = None,
    *,
    resolver: ActorResolver = RESOLVER,
    user_type: str | None = None,
    country: str | None = None,
    document_id: str | None = None,
) -> Actor:
    return resolver.resolve(
        name,
        register_id=register_id,
        source_kind="hys_feedback",
        user_type=user_type,
        country=country,
        document_id=document_id,
    )


def test_citizens_are_one_aggregate_and_never_named() -> None:
    by_type = resolve("Jane Doe", "9505781573-45", user_type="EU_CITIZEN")
    by_absence = resolve("  ", None, user_type="COMPANY")
    by_bad_id = resolve(None, "n/a")

    assert by_type == by_absence == by_bad_id
    assert (by_type.actor_id, by_type.kind) == (CITIZENS_ACTOR_ID, "citizens")
    assert "Jane" not in by_type.model_dump_json()
    assert by_type.aliases == ()


def test_register_id_decides_and_the_source_spelling_becomes_an_alias() -> None:
    actor = resolve(
        " The  European Consumer Organisation ",
        " 9505781573-45 ",
        document_id="doc:hys_feedback:1",
    )

    assert actor.actor_id == "actor:tr:9505781573-45"
    assert (actor.resolution, actor.resolution_score) == ("register_id", 1.0)
    assert (actor.name, actor.country) == (BEUC.name, "BEL")
    assert (
        ActorAlias(
            name="The European Consumer Organisation",
            source_kind="hys_feedback",
            document_id="doc:hys_feedback:1",
        )
        in actor.aliases
    )
    assert [alias.name for alias in actor.aliases] == sorted(alias.name for alias in actor.aliases)


def test_register_id_without_a_name_adds_no_alias() -> None:
    assert resolve(None, "9505781573-45") == to_actor(BEUC)
    assert resolve(None, "333333333333-33").name == "The European"


def test_two_register_ids_never_merge_even_under_one_name() -> None:
    first = resolve("Greenpeace", "222222222222-01")
    second = resolve("Greenpeace", "222222222222-02")

    assert first.actor_id != second.actor_id
    assert {actor.actor_id for actor in merge_actors([first, second, first])} == {
        "actor:tr:222222222222-01",
        "actor:tr:222222222222-02",
    }


def test_deregistered_id_keeps_its_identity_and_is_not_matched_by_name() -> None:
    actor = resolve("Fair Trials Europe", "999999999999-99", country="BEL")
    unnamed = resolve(None, "999999999999-99")

    assert actor.actor_id == unnamed.actor_id == "actor:tr:999999999999-99"
    assert (actor.resolution, actor.register_id) == ("register_id", "999999999999-99")
    assert actor.category == ABSENT_FROM_REGISTER
    assert (actor.name, actor.country, actor.candidate_ids) == ("Fair Trials Europe", "BEL", ())
    assert [alias.name for alias in actor.aliases] == ["Fair Trials Europe"]
    assert (unnamed.name, unnamed.aliases) == ("Transparency Register 999999999999-99", ())


def test_malformed_id_identifies_nothing_so_the_name_decides() -> None:
    actor = resolve("Siemens Energy", "12345")

    assert (actor.actor_id, actor.resolution) == ("actor:tr:974875639237-65", "normalised_exact")


def test_unique_normalised_name_is_accepted_as_the_register_identity() -> None:
    actor = resolve("SIEMENS ENERGY", country="DEU")
    latin = resolve("Archelon Turtle Society")

    assert actor.actor_id == "actor:tr:974875639237-65"
    assert (actor.resolution, actor.resolution_score) == ("normalised_exact", 1.0)
    assert (actor.register_id, actor.candidate_ids) == ("974875639237-65", ())
    assert "SIEMENS ENERGY" in [alias.name for alias in actor.aliases]
    assert (latin.actor_id, latin.resolution) == ("actor:tr:111111111111-11", "normalised_exact")


def test_a_name_differing_in_scope_words_only_proposes() -> None:
    actor = resolve("Fair Trials")

    assert actor.actor_id == "actor:name:hys_feedback.fair-trials"
    assert (actor.resolution, actor.resolution_score) == ("fuzzy", 1.0)
    assert actor.register_id is None
    assert actor.candidate_ids == ("actor:tr:302540016347-29",)


def test_name_shared_by_several_entries_is_ambiguous() -> None:
    actor = resolve("Greenpeace")

    assert actor.actor_id == "actor:name:hys_feedback.greenpeace"
    assert (actor.resolution, actor.resolution_score, actor.register_id) == ("ambiguous", 1.0, None)
    assert actor.candidate_ids == ("actor:tr:222222222222-01", "actor:tr:222222222222-02")


def test_acronym_alone_never_merges() -> None:
    actor = resolve("BEUC", country="BEL")
    shared = resolve("GP")

    assert actor.actor_id == "actor:name:hys_feedback.beuc"
    assert (actor.resolution, actor.resolution_score, actor.register_id) == ("acronym", None, None)
    assert actor.candidate_ids == ("actor:tr:9505781573-45",)
    assert shared.resolution == "ambiguous"
    assert len(shared.candidate_ids) == 2


def test_an_association_is_never_merged_with_its_members() -> None:
    member = RegisterEntry(register_id="555555555555-55", name="Acme Robotics")

    without_entry = resolve("Acme Robotics")
    with_entry = resolve("Acme Robotics", resolver=ActorResolver.build([*REGISTER, member]))

    # BEUC lists Acme Robotics among its members; that text is never a matching key.
    assert (without_entry.resolution, without_entry.candidate_ids) == ("unresolved", ())
    assert without_entry.actor_id == "actor:name:hys_feedback.acme-robotics"
    assert with_entry.actor_id == "actor:tr:555555555555-55"


def test_fuzzy_match_proposes_the_best_candidate_without_merging() -> None:
    resolver = ActorResolver.build([WIND_CLOSE, WIND_REORDERED, WIND_CLOSE_LATER, WIND_FAR])

    actor = resolve(WIND, resolver=resolver, country="DNK")
    lone = resolve(WIND, resolver=ActorResolver.build([WIND_CLOSE, WIND_SHORT]))

    assert actor.actor_id.startswith("actor:name:hys_feedback.northern-renewable")
    assert (actor.resolution, actor.resolution_score, actor.register_id) == ("fuzzy", 1.0, None)
    assert actor.candidate_ids == ("actor:tr:444444444444-02",)
    assert lone.candidate_ids == ("actor:tr:444444444444-01",)
    assert lone.resolution_score is not None
    assert 0.9 <= lone.resolution_score < 1.0


def test_equally_good_fuzzy_candidates_are_ambiguous() -> None:
    resolver = ActorResolver.build([WIND_REORDERED, WIND_ABROAD])

    tied = resolve(WIND, resolver=resolver)
    same_country = resolve(WIND, resolver=resolver, country="DNK")

    assert (tied.resolution, tied.resolution_score) == ("ambiguous", 1.0)
    assert tied.candidate_ids == ("actor:tr:444444444444-02", "actor:tr:444444444444-06")
    # The Norwegian entry is not proposed for a Danish submitter.
    assert (same_country.resolution, same_country.candidate_ids) == (
        "fuzzy",
        ("actor:tr:444444444444-02",),
    )


def test_distant_or_absent_names_stay_unresolved() -> None:
    resolver = ActorResolver.build([WIND_FAR, WIND_SHORT])

    actor = resolve(WIND, resolver=resolver, country="Atlantis")

    assert (actor.resolution, actor.resolution_score, actor.candidate_ids) == (
        "unresolved",
        None,
        (),
    )
    assert actor.country == "Atlantis"
    assert [alias.name for alias in actor.aliases] == [WIND]


def test_names_that_leave_no_ascii_key_still_get_distinct_identities() -> None:
    first = resolve("Οργανισμός")
    second = resolve("Ιδρυμα")
    filler = resolve("The European")

    assert first.actor_id != second.actor_id
    assert first.actor_id.startswith("actor:name:hys_feedback.")
    assert first == resolve("Οργανισμός")
    assert (filler.resolution, filler.candidate_ids) == ("unresolved", ())
    assert filler.actor_id.startswith("actor:name:hys_feedback.")


def test_merge_unions_aliases_in_a_fixed_order_without_changing_identity() -> None:
    mentions = [
        resolve("BEUC - consumers", "9505781573-45", document_id="doc:hys_feedback:2"),
        resolve("The Consumer Organisation", "9505781573-45", document_id="doc:hys_feedback:1"),
        resolve("BEUC - consumers", "9505781573-45", document_id="doc:hys_feedback:2"),
        resolve("Siemens Energy"),
        resolve("Jane Doe", user_type="NON_EU_CITIZEN"),
    ]

    results = {merge_actors(order) for order in permutations(mentions)}

    assert len(results) == 1
    (merged,) = results
    assert [actor.actor_id for actor in merged] == [
        CITIZENS_ACTOR_ID,
        "actor:tr:9505781573-45",
        "actor:tr:974875639237-65",
    ]
    beuc = merged[1]
    assert [alias.name for alias in beuc.aliases] == [
        "BEUC",
        "BEUC - consumers",
        "Bureau Européen des Unions de Consommateurs",
        "The Consumer Organisation",
    ]
    assert beuc.model_copy(update={"aliases": ()}) == to_actor(BEUC).model_copy(
        update={"aliases": ()}
    )
    assert merge_actors([]) == ()


def test_summary_counts_every_method_and_keeps_citizens_apart() -> None:
    actors = [
        resolve("x", "9505781573-45"),
        resolve("Siemens Energy"),
        resolve("BEUC"),
        resolve("Fair Trials"),
        resolve("Greenpeace"),
        resolve("Nobody Known"),
        resolve(None),
        resolve("Jane", user_type="EU_CITIZEN"),
    ]

    assert resolution_summary(actors) == {
        "register_id": 1,
        "mep_id": 0,
        "normalised_exact": 1,
        "acronym": 1,
        "fuzzy": 1,
        "ambiguous": 1,
        "unresolved": 1,
        "citizens": 2,
    }
