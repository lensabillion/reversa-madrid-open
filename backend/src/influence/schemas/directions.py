"""Part 7's directions: what `influence directions <law>` writes for one law.

A direction is a label read from the wording an amendment changes (stricter, weaker,
delete, delay, exempt, add, keep, other, unknown). It describes the edit, not the stance
of whoever tabled or asked for it, and a count of labels is not a cause.
"""

from typing import Literal

from pydantic import AwareDatetime, Field

from influence.schemas.atlas import (
    ActorId,
    AmendmentId,
    AmendmentStage,
    AtlasRecord,
    Direction,
    LinkId,
    NonEmpty,
    ProcedureId,
    SourceSpan,
)
from influence.schemas.scoring import FrozenModel

type DirectionMethod = Literal["direction-rules-1"]
# `from_published_links`: actor directions come from the law's atlas view. The other two
# say why there are none: no view was built, the view publishes no link, or the view was
# built from an older collect run than the amendments counted here.
type ActorsStatus = Literal[
    "from_published_links", "no_atlas_view", "no_published_links", "stale_atlas_view"
]


class DirectionCounts(FrozenModel):
    """One count per direction; every counted amendment (or link) is in exactly one."""

    stricter: int = Field(default=0, ge=0)
    weaker: int = Field(default=0, ge=0)
    delete: int = Field(default=0, ge=0)
    delay: int = Field(default=0, ge=0)
    exempt: int = Field(default=0, ge=0)
    add: int = Field(default=0, ge=0)
    keep: int = Field(default=0, ge=0)
    other: int = Field(default=0, ge=0)
    unknown: int = Field(default=0, ge=0)

    def pairs(self) -> tuple[tuple[Direction, int], ...]:
        """The counts as typed pairs, in field order, for printing without `Any`."""
        return (
            ("stricter", self.stricter),
            ("weaker", self.weaker),
            ("delete", self.delete),
            ("delay", self.delay),
            ("exempt", self.exempt),
            ("add", self.add),
            ("keep", self.keep),
            ("other", self.other),
            ("unknown", self.unknown),
        )


class UnknownReasons(FrozenModel):
    """Why amendments came back `unknown`; the two counts sum to `counts.unknown`."""

    # Over the diff's bounds (800 tokens or 12,000 characters a side).
    over_long: int = Field(ge=0)
    # Parltrack did not give the original wording and the new wording holds no cue.
    original_unknown: int = Field(ge=0)


class StageDirections(FrozenModel):
    stage: AmendmentStage
    amendments: int = Field(ge=0)
    counts: DirectionCounts


class GroupDirections(FrozenModel):
    """Amendments with an author in `group`; a cross-group amendment counts in each group."""

    group: NonEmpty
    amendments: int = Field(ge=1)
    counts: DirectionCounts


class MemberDirections(FrozenModel):
    """One tabling Member; a co-signed amendment counts for each of its authors."""

    actor_id: ActorId
    name: NonEmpty
    political_group: str | None
    amendments: int = Field(ge=1)
    counts: DirectionCounts


class ActorDirections(FrozenModel):
    """The directions of the amendments one actor's asks are published as linked to.

    Counted per published link: one ask echoed by two amendments counts twice.
    """

    actor_id: ActorId
    name: NonEmpty
    published_links: int = Field(ge=1)
    counts: DirectionCounts
    link_ids: tuple[LinkId, ...] = Field(min_length=1)


class DirectionExample(FrozenModel):
    """One amendment per direction with the wording that decided its label, quoted exactly."""

    direction: Direction
    amendment_id: AmendmentId
    span: SourceSpan


class DirectionsView(AtlasRecord):
    procedure_id: ProcedureId
    slug: NonEmpty
    title: NonEmpty
    run_id: NonEmpty
    generated_at: AwareDatetime
    method: DirectionMethod
    amendments: int = Field(ge=0)
    counts: DirectionCounts
    unknown_reasons: UnknownReasons
    by_stage: tuple[StageDirections, ...]
    # Most amendments first. Amendments with no author of known group are counted apart.
    by_group: tuple[GroupDirections, ...]
    without_group: int = Field(ge=0)
    # The Members who tabled the most amendments, most first.
    top_members: tuple[MemberDirections, ...]
    actors_status: ActorsStatus
    actors_reason: str | None
    # The run the atlas view was built from, which can be older than `run_id`.
    atlas_run_id: str | None
    # Most published links first.
    actors: tuple[ActorDirections, ...]
    examples: tuple[DirectionExample, ...]
    limitations: tuple[str, ...]
