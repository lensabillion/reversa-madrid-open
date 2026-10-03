"""Every count by political group uses each author's group on the day they tabled.

Member 1 sat with Renew in 2022 and moved to the EPP later, so their latest group is EPP;
Member 3 was EPP throughout. On a 2022 amendment Member 1 counts as Renew in the coordinated
clusters, the HOW counts, the lineage credits and the TOWARDS directions alike.
"""

from datetime import date

import pytest
import test_lineage
from test_coordinated import LATER, amendment, law, mep

from influence.schemas.atlas import Amendment
from influence.services import channels, coordinated, direction, lineage
from influence.services.tabling_groups import (
    LATEST_SPELL_FALLBACK,
    TABLING_DAY_GROUPS,
    group_limitations,
    known_groups,
    latest_groups,
    tabling_groups,
)

SWITCHER = mep(1, "EPP")
STAYER = mep(3, "EPP")
ACTORS = (SWITCHER, STAYER)


def on_day(item: Amendment, *groups: str | None) -> Amendment:
    """The amendment as a bundle collected after tabling-day groups were recorded."""
    return Amendment.model_validate({**item.model_dump(), "author_groups": groups})


RENEW_2022 = on_day(amendment("PE1-1", authors=(1,), tabled=date(2022, 3, 1)), "Renew")
EPP_2022 = on_day(amendment("PE1-2", authors=(3,), tabled=date(2022, 3, 2)), "EPP")
UNKNOWN_2022 = on_day(amendment("PE1-3", "", authors=(1,), tabled=None), None)


# --- The rule ---------------------------------------------------------------------------------


def test_the_recorded_group_wins_over_the_latest_and_none_stays_unknown() -> None:
    latest = latest_groups((*ACTORS, mep(4, None)))
    assert latest == {"actor:mep:1": "EPP", "actor:mep:3": "EPP"}
    assert tabling_groups(RENEW_2022, latest) == {"actor:mep:1": "Renew"}
    assert tabling_groups(UNKNOWN_2022, latest) == {"actor:mep:1": None}
    assert known_groups(UNKNOWN_2022, latest) == set()
    old = amendment("PE1-4", authors=(1, 9))
    assert tabling_groups(old, latest) == {"actor:mep:1": "EPP", "actor:mep:9": None}
    assert group_limitations([RENEW_2022, UNKNOWN_2022]) == (TABLING_DAY_GROUPS,)
    assert group_limitations([RENEW_2022, old]) == (TABLING_DAY_GROUPS, LATEST_SPELL_FALLBACK)
    # Committee text has no author, so it needs no group and triggers no fallback.
    assert group_limitations([amendment("PE1-5")]) == (TABLING_DAY_GROUPS,)


# --- Coordinated amendments -------------------------------------------------------------------


def test_coordinated_wording_from_renew_then_and_the_epp_spans_groups() -> None:
    view = coordinated.build_coordination(
        law(), "run-1", [RENEW_2022, EPP_2022], ACTORS, generated_at=LATER
    )

    (cluster,) = view.clusters
    assert [member.political_groups for member in cluster.members] == [("Renew",), ("EPP",)]
    assert (cluster.political_groups, cluster.cross_group) == (("EPP", "Renew"), True)
    assert LATEST_SPELL_FALLBACK not in view.limitations
    assert TABLING_DAY_GROUPS in view.limitations


def test_an_old_bundle_falls_back_to_the_latest_group_and_says_so() -> None:
    old = [amendment("PE1-1", authors=(1,)), amendment("PE1-2", authors=(3,))]

    view = coordinated.build_coordination(law(), "run-1", old, ACTORS, generated_at=LATER)

    (cluster,) = view.clusters
    assert (cluster.political_groups, cluster.cross_group) == (("EPP",), False)
    assert view.limitations[-2:] == (TABLING_DAY_GROUPS, LATEST_SPELL_FALLBACK)


def test_a_group_unknown_on_the_day_is_never_the_latest_one() -> None:
    unknown = on_day(amendment("PE1-1", authors=(1,)), None)

    (cluster,) = coordinated.find_coordinated([unknown, EPP_2022], ACTORS)[0]

    assert [member.political_groups for member in cluster.members] == [(), ("EPP",)]
    assert (cluster.political_groups, cluster.cross_group) == (("EPP",), False)


# --- HOW: Members and coalitions --------------------------------------------------------------


def test_how_counts_each_amendment_under_the_group_its_author_tabled_in() -> None:
    later = on_day(amendment("PE2-1", "", authors=(1,), tabled=date(2025, 1, 9)), "EPP")
    both = amendment("PE2-2", "", authors=(1, 3), tabled=date(2022, 5, 1))
    cosigned = on_day(both, "Renew", "EPP")
    amendments = [RENEW_2022, later, cosigned, UNKNOWN_2022]

    members = channels.mep_channel(amendments, ACTORS)
    coalitions = channels.coalition_channel(amendments, ACTORS)

    assert [(item.key, item.count) for item in members.by_political_group] == [
        ("EPP", 2),
        ("Renew", 2),
    ]
    assert (members.with_known_group, members.group_unknown) == (3, 1)
    assert {(m.actor_id, m.political_group, m.amendments) for m in members.top_meps} == {
        ("actor:mep:1", "EPP/Renew", 4),
        ("actor:mep:3", "EPP", 1),
    }
    # By latest group both co-signers are EPP; on the day they were Renew and EPP.
    assert coalitions.cosigned_across_groups == 1


def test_how_with_an_old_bundle_uses_the_latest_group_and_says_so() -> None:
    old = amendment("PE1-1", authors=(1,))
    members = channels.mep_channel([old], ACTORS)
    assert [(item.key, item.count) for item in members.by_political_group] == [("EPP", 1)]
    assert members.top_meps[0].political_group == "EPP"


@pytest.mark.parametrize(
    ("amendments", "fallback"),
    [((RENEW_2022,), False), ((amendment("PE1-1", authors=(1,)),), True)],
)
def test_the_channels_view_names_the_fallback_only_for_an_old_bundle(
    amendments: tuple[Amendment, ...], fallback: bool
) -> None:
    view = channels.build_channels(
        law(),
        "run-1",
        documents=(),
        passages=(),
        actors=ACTORS,
        amendments=amendments,
        types=None,
        generated_at=LATER,
    )
    assert TABLING_DAY_GROUPS in view.limitations
    assert (LATEST_SPELL_FALLBACK in view.limitations) is fallback


# --- TOWARDS: directions by group -------------------------------------------------------------


def test_directions_count_the_2022_amendment_under_renew() -> None:
    view = direction.build_directions(
        law(), "run-1", [RENEW_2022, EPP_2022, UNKNOWN_2022], ACTORS, None, generated_at=LATER
    )

    assert sorted((row.group, row.amendments) for row in view.by_group) == [
        ("EPP", 1),
        ("Renew", 1),
    ]
    assert view.without_group == 1
    assert {(m.actor_id, m.political_group) for m in view.top_members} == {
        ("actor:mep:1", "Renew"),
        ("actor:mep:3", "EPP"),
    }
    assert view.limitations[-1] == TABLING_DAY_GROUPS


def test_directions_of_an_old_bundle_use_the_latest_group_and_say_so() -> None:
    old = amendment("PE1-1", authors=(1,))
    view = direction.build_directions(law(), "run-1", [old], ACTORS, None, generated_at=LATER)
    assert [row.group for row in view.by_group] == ["EPP"]
    assert view.limitations[-2:] == (TABLING_DAY_GROUPS, LATEST_SPELL_FALLBACK)


# --- Lineage: adopted wording credited by group -----------------------------------------------


def adopted(*groups: str | None) -> Amendment:
    item = test_lineage.amendment(1, test_lineage.NEW)
    return on_day(item, *groups) if groups else item


def credited_groups(result: lineage.Adoption) -> list[str]:
    return sorted(credit.name for credit in result.credits if credit.holder_kind == "group")


def test_lineage_credits_the_group_the_author_tabled_in() -> None:
    articles = [test_lineage.PROPOSAL, test_lineage.FINAL]

    result = lineage.adopt_records([adopted("Renew")], articles, [SWITCHER])

    assert [a.author_groups for a in result.adoptions] == [("Renew",)]
    assert credited_groups(result) == ["Renew"]
    assert result.limitations[0] == TABLING_DAY_GROUPS
    assert LATEST_SPELL_FALLBACK not in result.limitations


def test_lineage_of_an_old_bundle_uses_the_latest_group_and_says_so() -> None:
    articles = [test_lineage.PROPOSAL, test_lineage.FINAL]

    result = lineage.adopt_records([adopted()], articles, [SWITCHER])

    assert [a.author_groups for a in result.adoptions] == [("EPP",)]
    assert credited_groups(result) == ["EPP"]
    assert result.limitations[:2] == (TABLING_DAY_GROUPS, LATEST_SPELL_FALLBACK)


def test_lineage_credits_no_group_when_the_group_that_day_is_unknown() -> None:
    articles = [test_lineage.PROPOSAL, test_lineage.FINAL]

    result = lineage.adopt_records([adopted(None)], articles, [SWITCHER])

    assert [a.author_groups for a in result.adoptions] == [(None,)]
    assert credited_groups(result) == []
    assert result.phrases_without_group == 1
