"""The explorer's law search and on-demand build: what was typed, and one build's progress."""

from typing import Literal

from pydantic import Field

from influence.schemas.batch import BatchStep
from influence.schemas.scoring import FrozenModel

type BuildStatus = Literal["queued", "running", "done", "failed"]


class BuildState(FrozenModel):
    slug: str
    procedure_id: str
    state: BuildStatus
    # The step running, or the one that failed; None when queued or done.
    step: str | None
    steps: tuple[BatchStep, ...]
    started_at: str
    finished_at: str | None
    error: str | None
    # The last progress lines, oldest first.
    log: tuple[str, ...]


class LawHit(FrozenModel):
    procedure_id: str
    title: str
    slug: str
    has_lineage: bool
    has_atlas: bool
    build: BuildState | None


class LawSearch(FrozenModel):
    query: str
    status: Literal["found", "ambiguous", "not_found"]
    law: LawHit | None
    choices: tuple[LawHit, ...]
    message: str | None


class BuildRequest(FrozenModel):
    steps: tuple[BatchStep, ...] = Field(default=("lineage", "atlas"), min_length=1)
