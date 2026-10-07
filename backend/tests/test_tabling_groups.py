"""Every count by political group uses each author's group on the day they tabled.

Member 1 sat with Renew in 2022 and moved to the EPP later, so their latest group is EPP;
Member 3 was EPP throughout. Lineage credits a 2022 amendment from Member 1 to Renew.
"""

from datetime import date

import test_lineage
from lineage_fixture import amendment, mep

from influence.schemas.atlas import Amendment
from influence.services import lineage
from influence.services.tabling_groups import (
    LATEST_SPELL_FALLBACK,
    TABLING_DAY_GROUPS,
    group_limitations,
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


def test_the_recorded_group_wins_over_the_latest_and_none_stays_unknown() -> None:
    latest = latest_groups((*ACTORS, mep(4, None)))
    assert latest == {"actor:mep:1": "EPP", "actor:mep:3": "EPP"}
    assert tabling_groups(RENEW_2022, latest) == {"actor:mep:1": "Renew"}
    assert tabling_groups(UNKNOWN_2022, latest) == {"actor:mep:1": None}
    old = amendment("PE1-4", authors=(1, 9))
    assert tabling_groups(old, latest) == {"actor:mep:1": "EPP", "actor:mep:9": None}
    assert group_limitations([RENEW_2022, UNKNOWN_2022]) == (TABLING_DAY_GROUPS,)
    assert group_limitations([RENEW_2022, old]) == (TABLING_DAY_GROUPS, LATEST_SPELL_FALLBACK)
    # Committee text has no author, so it needs no group and triggers no fallback.
    assert group_limitations([amendment("PE1-5")]) == (TABLING_DAY_GROUPS,)


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
