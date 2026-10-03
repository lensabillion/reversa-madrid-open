"""Part 3's coordinated amendments: what `influence coordinated` writes for one law.

A cluster is a set of tabled amendments whose inserted wording is near-identical. It is a
candidate for a shared outside draft, never proof of one: parts 3 and 4 still have to find
the draft among the law's submissions.
"""

from datetime import date
from typing import Literal

from pydantic import AwareDatetime, Field

from influence.schemas.atlas import (
    ActorId,
    AmendmentId,
    AmendmentStage,
    AtlasRecord,
    NonEmpty,
    ProcedureId,
    SourceSpan,
)
from influence.schemas.scoring import FrozenModel

type CoordinationMethod = Literal["shingle-jaccard-1"]


class ClusterMember(FrozenModel):
    """One amendment of a cluster, with the wording it inserts quoted from its `new_text`."""

    amendment_id: AmendmentId
    stage: AmendmentStage
    committee: str | None
    tabled_on: date | None
    target_provision: str | None
    author_ids: tuple[ActorId, ...]
    author_names: tuple[str, ...]
    # The groups of the authors the MEP dump knows, sorted. Empty is unknown, not "no group".
    political_groups: tuple[str, ...]
    inserted: tuple[SourceSpan, ...] = Field(min_length=1)


class CoordinatedCluster(FrozenModel):
    cluster_id: NonEmpty
    # Earliest tabled first, undated last.
    members: tuple[ClusterMember, ...] = Field(min_length=2)
    political_groups: tuple[str, ...]
    # Two members share no author and no political group.
    cross_group: bool
    # Inserted words of the member that inserts the fewest.
    inserted_words: int = Field(ge=1)
    # The least similar pair: a cluster joins amendments through chains of similar pairs.
    min_similarity: float = Field(ge=0, le=1, allow_inf_nan=False)


class CoordinationCounts(FrozenModel):
    """Every amendment of the law is in exactly one of the last three counts."""

    amendments: int = Field(ge=0)
    compared: int = Field(ge=0)
    too_short: int = Field(ge=0)
    # Over the diff's bounds (800 tokens or 12,000 characters a side).
    not_comparable: int = Field(ge=0)


class CoordinatedView(AtlasRecord):
    procedure_id: ProcedureId
    slug: NonEmpty
    title: NonEmpty
    run_id: NonEmpty
    generated_at: AwareDatetime
    method: CoordinationMethod
    min_inserted_words: int = Field(ge=1)
    shingle_words: int = Field(ge=1)
    similarity_threshold: float = Field(gt=0, le=1)
    counts: CoordinationCounts
    # Clusters spanning groups first, then by groups and size.
    clusters: tuple[CoordinatedCluster, ...]
    limitations: tuple[str, ...]
