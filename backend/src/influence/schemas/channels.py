"""Part 7's HOW: the channels through which one law was lobbied, counted from part 1's records.

Every number is a count of collected records with its denominator beside it, never a bare
share, and it describes what the record holds: a channel associated with a law, not one
that caused a change in it. Nothing here reads a link, confirmed or not.
"""

from datetime import date
from typing import Literal

from pydantic import AwareDatetime, Field

from influence.schemas.atlas import (
    ActorId,
    AtlasRecord,
    LayerCoverage,
    NonEmpty,
    ProcedureId,
)
from influence.schemas.coordinated import CoordinationCounts
from influence.schemas.scoring import FrozenModel

type ChannelsMethod = Literal["channels-1"]


class KeyCount(FrozenModel):
    """One value of a breakdown and how many records carry it."""

    key: NonEmpty
    count: int = Field(ge=0)


class DateSplit(FrozenModel):
    """Records placed against one reference date; the four counts sum to `total`.

    `on_or_after` includes the reference day itself. `unplaced` holds dated records when the
    reference date is unknown, so they are neither before nor after it.
    """

    reference_date: date | None
    total: int = Field(ge=0)
    before: int = Field(ge=0)
    on_or_after: int = Field(ge=0)
    undated: int = Field(ge=0)
    unplaced: int = Field(ge=0)


class PublicationFeedback(FrozenModel):
    """Feedback on one Have Your Say publication, one stage of the Commission's consultation."""

    # None when the feedback's URL names no publication.
    publication_id: int | None
    # The source's own code (for example PROP_REG for feedback on the proposal); None when
    # the Have Your Say index is not built or does not list the publication.
    publication_type: str | None
    feedback: int = Field(ge=0)
    earliest: date | None
    latest: date | None


class SubmitterGroup(FrozenModel):
    """Feedback items, and the distinct submitters behind them, sharing one attribute."""

    key: NonEmpty
    feedback: int = Field(ge=0)
    submitters: int = Field(ge=0)


class ConsultationChannel(FrozenModel):
    feedback: int = Field(ge=0)
    attachments: int = Field(ge=0)
    # Ordered by publication ID, unknown last.
    by_publication: tuple[PublicationFeedback, ...]
    # Why `publication_type` is missing, when it is missing for any publication.
    publication_type_gap: str | None
    # Feedback whose submitter no passage or actor alias names.
    feedback_without_submitter: int = Field(ge=0)
    submitters: int = Field(ge=0)
    # Most feedback first; `unknown` is a key, never dropped.
    by_actor_kind: tuple[SubmitterGroup, ...]
    by_register_category: tuple[SubmitterGroup, ...]
    # Organisation submitters carrying a Transparency Register ID, of all organisations.
    organisations: int = Field(ge=0)
    organisations_with_register_id: int = Field(ge=0)


class TimingChannel(FrozenModel):
    # Consultation feedback dated against the Commission's proposal.
    feedback_vs_proposal: DateSplit
    amendments_vs_proposal: DateSplit
    amendments_vs_completion: DateSplit


class TablingMep(FrozenModel):
    actor_id: ActorId
    name: NonEmpty
    # Every group the Member tabled these amendments under, "/"-joined; None if unknown.
    political_group: str | None
    amendments: int = Field(ge=1)


class MepChannel(FrozenModel):
    amendments: int = Field(ge=0)
    by_stage: tuple[KeyCount, ...]
    by_committee: tuple[KeyCount, ...]
    # An amendment counts once for each group among its authors, so these can sum to more
    # than `with_known_group`.
    by_political_group: tuple[KeyCount, ...]
    with_known_group: int = Field(ge=0)
    # Authors listed, none of them with a group the MEP dump states.
    group_unknown: int = Field(ge=0)
    # No author listed at all (common for plenary amendments tabled by a group or committee).
    no_known_author: int = Field(ge=0)
    tabling_meps: int = Field(ge=0)
    # Most amendments first; at most `TOP_MEPS` of them.
    top_meps: tuple[TablingMep, ...]


class CoalitionChannel(FrozenModel):
    amendments: int = Field(ge=0)
    # Amendments with two or more authors, and those whose authors' known groups differ.
    cosigned: int = Field(ge=0)
    cosigned_across_groups: int = Field(ge=0)
    # Part 3's near-identical wording tabled separately by Members of different groups.
    coordinated: CoordinationCounts
    coordinated_clusters: int = Field(ge=0)
    cross_group_clusters: int = Field(ge=0)
    amendments_in_cross_group_clusters: int = Field(ge=0)


class ChannelsView(AtlasRecord):
    procedure_id: ProcedureId
    slug: NonEmpty
    title: NonEmpty
    run_id: NonEmpty
    generated_at: AwareDatetime
    method: ChannelsMethod
    consultation: ConsultationChannel
    timing: TimingChannel
    meps: MepChannel
    coalitions: CoalitionChannel
    # Part 1's coverage rows for votes and meetings, as collected: no count is invented.
    votes_and_meetings: tuple[LayerCoverage, ...]
    limitations: tuple[str, ...]
