"""Each amendment author's political group on the day the amendment was tabled.

A Member who moved from one group to another tabled their earlier amendments under the
earlier group, so every count by group reads the group an amendment records for each
author (`Amendment.author_groups`), never the Member's latest group. Bundles collected
before amendments recorded those groups fall back to the latest group, and the views that
count by group then say so in their limitations.
"""

from collections.abc import Iterable, Mapping

from influence.schemas.atlas import Actor, Amendment

TABLING_DAY_GROUPS = (
    "A Member's political group is their group on the day the amendment was tabled, from "
    "Parltrack's dated group spells; a Member with no spell covering that day counts as "
    "group unknown, never under a later group."
)
LATEST_SPELL_FALLBACK = (
    "This bundle was collected before amendments recorded each author's group on the "
    "tabling day, so for its amendments a Member's political group is the one of their "
    "latest spell in Parltrack's dump, which can differ from their group when tabling."
)


def latest_groups(actors: Iterable[Actor]) -> dict[str, str]:
    """Each Member's latest group, for amendments that record no tabling-day groups."""
    return {
        actor.actor_id: actor.political_group
        for actor in actors
        if actor.political_group is not None
    }


def tabling_groups(amendment: Amendment, latest: Mapping[str, str]) -> dict[str, str | None]:
    """Each author's group when `amendment` was tabled; None where it is unknown.

    The latest group stands in only when the amendment records no groups at all (an older
    bundle); a None the amendment records stays None.
    """
    if amendment.author_groups:
        return dict(zip(amendment.author_ids, amendment.author_groups, strict=True))
    return {author: latest.get(author) for author in amendment.author_ids}


def uses_latest_groups(amendments: Iterable[Amendment]) -> bool:
    """Whether any authored amendment lacks tabling-day groups, so the fallback applied."""
    return any(amendment.author_ids and not amendment.author_groups for amendment in amendments)


def group_limitations(amendments: Iterable[Amendment]) -> tuple[str, ...]:
    """The group limitation sentences that apply to these amendments."""
    if uses_latest_groups(amendments):
        return (TABLING_DAY_GROUPS, LATEST_SPELL_FALLBACK)
    return (TABLING_DAY_GROUPS,)
