"""The batch file: what `influence batch` ran over many laws, and how much of Europe it covers.

`data/laws/batch.json` is rewritten after every law, so a run that stops keeps the laws it
finished; `finished_at` stays None until the last law is done. The banner is derived from
the law rows each time, never kept apart from them.
"""

from datetime import date
from typing import Literal

from pydantic import AwareDatetime, Field

from influence.schemas.atlas import Layer, LayerStatus
from influence.schemas.scoring import FrozenModel

# The steps a batch can run after collect, in the order they run: atlas first, because
# `directions` reads the atlas view when one exists.
type BatchStep = Literal["atlas", "coordinated", "channels", "lineage", "directions"]
# done: built in this run; reused: a complete collect run was already published;
# skipped: the output already carries the current collect run; failed: see `error`.
type StepStatus = Literal["done", "reused", "skipped", "failed"]
# complete: collected and every step done or skipped; partial: collected, a step failed;
# failed: the law could not be resolved or collected.
type BatchLawStatus = Literal["complete", "partial", "failed"]


class StepOutcome(FrozenModel):
    step: Literal["collect"] | BatchStep
    status: StepStatus
    seconds: float = Field(ge=0)
    error: str | None = None


class CoverageCount(FrozenModel):
    """One collect coverage row without its reason: the batch counts, the manifest explains."""

    layer: Layer
    status: LayerStatus
    count: int | None = Field(default=None, ge=0)


class BatchLaw(FrozenModel):
    query: str
    # None when the query named no single procedure.
    procedure_id: str | None
    title: str | None
    status: BatchLawStatus
    # The collect run the steps were built from; None when nothing was collected.
    run_id: str | None = None
    error: str | None = None
    seconds: float = Field(ge=0)
    # Committee and plenary amendments the collect run holds; None when nothing was collected.
    amendments: int | None = Field(default=None, ge=0)
    steps: tuple[StepOutcome, ...] = ()
    coverage: tuple[CoverageCount, ...] = ()


class BatchSelection(FrozenModel):
    mode: Literal["laws", "since"]
    # The names typed with --laws, in order; empty for --since.
    laws: tuple[str, ...] = ()
    # The first day an amendment must be tabled on for --since; None for --laws.
    since: date | None = None
    limit: int | None = Field(default=None, ge=1)


class CoverageBanner(FrozenModel):
    laws_selected: int = Field(ge=0)
    laws_attempted: int = Field(ge=0)
    laws_complete: int = Field(ge=0)
    laws_partial: int = Field(ge=0)
    laws_failed: int = Field(ge=0)
    amendments_covered: int = Field(ge=0)
    # Layer -> how many collected laws hold it in a state other than complete.
    layers_missing: dict[str, int]
    # Step -> how many laws it failed on.
    steps_failed: dict[str, int]
    hardware: str
    started_at: AwareDatetime
    finished_at: AwareDatetime | None = None


class BatchRun(FrozenModel):
    schema_version: Literal["batch-1"] = "batch-1"
    selection: BatchSelection
    steps: tuple[BatchStep, ...]
    attachments: bool
    refresh: bool
    code_revision: str
    banner: CoverageBanner
    laws: tuple[BatchLaw, ...]
