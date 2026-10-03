"""Part 8 · Publish at scale: many laws through collect and the per-law steps, resumably.

The brief asks for "all of Europe from 2019" (plan gate 9). One law already has a command
per step; the batch runs the same services over a list of laws: those named with
`--laws`, or every procedure of the Parltrack dossiers catalog with an amendment tabled
on or after a date. Nothing here analyses a law: each step is the service its own
command calls, so a law's files are the same whichever command wrote them.

Resuming is by run: a law that already has a published collect manifest is not collected
again (unless `refresh`), and a step whose output file was built from that manifest's run
is skipped. One law failing is recorded and the batch moves on; `batch.json` is written
atomically after every law, so an interrupted batch keeps what it finished.
"""

import json
import platform
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from functools import cached_property
from pathlib import Path
from time import perf_counter

from influence.extraction.cache import CacheError
from influence.extraction.fetching import CachedFetcher, FetchError
from influence.extraction.files import write_bytes_atomic
from influence.extraction.layout import procedure_slug
from influence.extraction.records import StageStore
from influence.repositories import parltrack
from influence.repositories.hys import HysError, read_index
from influence.repositories.parltrack import ParltrackError, ProcedureEntry
from influence.schemas.batch import (
    BatchLaw,
    BatchRun,
    BatchSelection,
    BatchStep,
    CoverageBanner,
    CoverageCount,
    StepOutcome,
)
from influence.schemas.coordinated import CoordinatedView
from influence.services import channels, coordinated, direction, lineage_assembly, pipeline
from influence.services.collect import (
    CollectError,
    CollectInputs,
    CollectSettings,
    collect_law,
    resolve_law,
)
from influence.services.coordinated import CoordinationError
from influence.services.pipeline import Collected, PipelineError

# In run order: `directions` reads the atlas view, so atlas comes first when chosen.
STEPS: tuple[BatchStep, ...] = ("atlas", "coordinated", "channels", "lineage", "directions")
# The cheap steps, read from Parltrack and the collect bundle; atlas takes minutes a law.
DEFAULT_STEPS: tuple[BatchStep, ...] = ("coordinated", "channels", "lineage", "directions")
BATCH_FILE = "batch.json"
OUTPUTS: Mapping[BatchStep, str] = {
    "atlas": pipeline.VIEW_FILE,
    "coordinated": coordinated.VIEW_FILE,
    "channels": channels.VIEW_FILE,
    "lineage": lineage_assembly.VIEW_FILE,
    "directions": direction.VIEW_FILE,
}
_AMENDMENT_LAYERS = frozenset({"committee_amendments", "plenary_amendments"})
# Every failure one law's run can raise. Anything else is a bug and stops the batch, with
# the laws finished so far already in batch.json.
LAW_ERRORS = (
    CollectError,
    CacheError,
    FetchError,
    HysError,
    ParltrackError,
    PipelineError,
    CoordinationError,
    OSError,
    ValueError,
)


@dataclass(frozen=True)
class PlannedLaw:
    query: str
    # None when the query names no single procedure; `error` then says why.
    procedure_id: str | None
    title: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class BatchSettings:
    collect: CollectSettings
    steps: tuple[BatchStep, ...]
    selection: BatchSelection


def _failure(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"


def plan_named(
    queries: Sequence[str], catalog: Sequence[ProcedureEntry], fetcher: CachedFetcher
) -> tuple[PlannedLaw, ...]:
    """Resolve each name as `collect` does; a name that fails is planned as a failed law.

    Two names for one procedure run it once, under the first name.
    """
    planned: list[PlannedLaw] = []
    seen: set[str] = set()
    for query in queries:
        try:
            law = resolve_law(query, catalog, fetcher)
        except CollectError as error:
            planned.append(PlannedLaw(query, None, error=_failure(error)))
            continue
        if law.procedure_id in seen:
            continue
        seen.add(law.procedure_id)
        title = None if law.entry is None else law.entry.title
        planned.append(PlannedLaw(query, law.procedure_id, title))
    return tuple(planned)


def amended_since(dumps: Iterable[Path], since: date) -> Counter[str]:
    """Procedure -> amendments tabled on or after `since`, over the given amendment dumps.

    One parse of every record: linear in the dumps' size, about a minute for the
    committee dump (about 55 s to parse, plan §5), and memory grows only with the number
    of procedures. A record with no date or reference is not counted.
    """
    first = since.isoformat()
    counts: Counter[str] = Counter()
    for path in dumps:
        for record in parltrack.iter_dump(path):
            reference, tabled = record.get("reference"), record.get("date")
            if isinstance(reference, str) and isinstance(tabled, str) and tabled[:10] >= first:
                counts[reference] += 1
    return counts


def plan_since(
    catalog: Sequence[ProcedureEntry], counts: Counter[str], limit: int | None
) -> tuple[PlannedLaw, ...]:
    """The catalog's procedures with counted amendments, most amended first.

    Most amended first, so a batch cut short (or limited) has covered the most amendments
    it could. A counted procedure the catalog lacks is left out: it has no dossier.
    """
    titles = {entry.procedure_id: entry.title for entry in catalog}
    chosen = sorted((p for p in counts if p in titles), key=lambda p: (-counts[p], p))
    return tuple(PlannedLaw(p, p, titles[p]) for p in chosen[:limit])


def built_from(path: Path) -> str | None:
    """The collect run an output file was built from; None when absent or unreadable."""
    try:
        found: object = json.loads(path.read_bytes())
    except FileNotFoundError:
        return None
    except ValueError:
        # A damaged output is built again, not trusted.
        return None
    if not isinstance(found, dict):
        return None
    run_id = found.get("run_id")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    return run_id if isinstance(run_id, str) else None


class StepRunner:
    """Each step as its own command runs it, minus the printing; one instance per batch."""

    def __init__(self, data_root: Path, index: Path, clock: Callable[[], datetime]) -> None:
        self._data_root = data_root
        self._index = index
        self._clock = clock

    @cached_property
    def types(self) -> dict[int, str] | None:
        """Publication types from the Have Your Say index, read once for every law."""
        return (
            channels.publication_types(read_index(self._index)) if self._index.is_file() else None
        )

    def run(self, step: BatchStep, collected: Collected, bundle: Path) -> None:
        law, run_id, now = collected.law, collected.manifest.run_id, self._clock()

        def coordination() -> CoordinatedView:
            return coordinated.build_coordination(
                law, run_id, collected.amendments, collected.actors, generated_at=now
            )

        if step == "atlas":
            try:
                view = pipeline.build_view(collected, generated_at=now)
                # As `influence atlas` does: clusters first, the view last, from one run.
                coordinated.write_coordination(coordination(), bundle)
                pipeline.write_view(view, bundle)
            except LAW_ERRORS:
                pipeline.remove_stale_view(bundle, run_id)
                raise
        elif step == "coordinated":
            coordinated.write_coordination(coordination(), bundle)
        elif step == "channels":
            channels.write_channels(
                channels.build_channels(
                    law,
                    run_id,
                    documents=collected.documents,
                    passages=collected.passages,
                    actors=collected.actors,
                    amendments=collected.amendments,
                    types=self.types,
                    generated_at=now,
                ),
                bundle,
            )
        elif step == "lineage":
            lineage_assembly.write_lineage(
                lineage_assembly.build_lineage(collected, generated_at=now), bundle
            )
        else:
            atlas = pipeline.read_view(self._data_root, bundle.name)
            direction.write_directions(
                direction.build_directions(
                    law, run_id, collected.amendments, collected.actors, atlas, generated_at=now
                ),
                bundle,
            )


@dataclass(frozen=True)
class _Context:
    inputs: CollectInputs
    settings: BatchSettings
    fetcher: CachedFetcher
    clock: Callable[[], datetime]
    timer: Callable[[], float]
    steps: StepRunner


def _run_law(planned: PlannedLaw, context: _Context) -> BatchLaw:
    started = context.timer()
    if planned.procedure_id is None:
        return BatchLaw(
            query=planned.query,
            procedure_id=None,
            title=None,
            status="failed",
            error=planned.error,
            seconds=0.0,
        )
    collect_settings = context.settings.collect
    bundle = collect_settings.data_root / "laws" / procedure_slug(planned.procedure_id)
    outcomes: list[StepOutcome] = []
    try:
        manifest = None if collect_settings.refresh else StageStore(bundle).current()
        if manifest is None:
            began = context.timer()
            manifest = collect_law(
                planned.procedure_id,
                inputs=context.inputs,
                settings=collect_settings,
                fetcher=context.fetcher,
                clock=context.clock,
            ).manifest
            outcomes.append(
                StepOutcome(step="collect", status="done", seconds=context.timer() - began)
            )
        else:
            outcomes.append(StepOutcome(step="collect", status="reused", seconds=0.0))
        run_id = manifest.run_id
        pending = {
            step
            for step in context.settings.steps
            if collect_settings.refresh or built_from(bundle / OUTPUTS[step]) != run_id
        }
        collected = pipeline.load_collected(bundle) if pending else None
    except LAW_ERRORS as error:
        return BatchLaw(
            query=planned.query,
            procedure_id=planned.procedure_id,
            title=planned.title,
            status="failed",
            error=_failure(error),
            seconds=context.timer() - started,
            steps=tuple(outcomes),
        )
    for step in context.settings.steps:
        if collected is None or step not in pending:
            outcomes.append(StepOutcome(step=step, status="skipped", seconds=0.0))
            continue
        began = context.timer()
        try:
            context.steps.run(step, collected, bundle)
        except LAW_ERRORS as error:
            outcomes.append(
                StepOutcome(
                    step=step,
                    status="failed",
                    seconds=context.timer() - began,
                    error=_failure(error),
                )
            )
            continue
        outcomes.append(StepOutcome(step=step, status="done", seconds=context.timer() - began))
    return BatchLaw(
        query=planned.query,
        procedure_id=planned.procedure_id,
        title=planned.title,
        status="partial" if any(o.status == "failed" for o in outcomes) else "complete",
        run_id=run_id,
        seconds=context.timer() - started,
        amendments=sum(
            row.count or 0 for row in manifest.coverage if row.layer in _AMENDMENT_LAYERS
        ),
        steps=tuple(outcomes),
        coverage=tuple(
            CoverageCount(layer=row.layer, status=row.status, count=row.count)
            for row in manifest.coverage
        ),
    )


def coverage_banner(
    laws: Sequence[BatchLaw],
    *,
    selected: int,
    hardware: str,
    started_at: datetime,
    finished_at: datetime | None,
) -> CoverageBanner:
    """What the batch covers so far, counted from its law rows. Linear in the rows."""
    statuses = Counter(law.status for law in laws)
    missing = Counter(row.layer for law in laws for row in law.coverage if row.status != "complete")
    failed = Counter(step.step for law in laws for step in law.steps if step.status == "failed")
    return CoverageBanner(
        laws_selected=selected,
        laws_attempted=len(laws),
        laws_complete=statuses["complete"],
        laws_partial=statuses["partial"],
        laws_failed=statuses["failed"],
        amendments_covered=sum(law.amendments or 0 for law in laws),
        layers_missing=dict(sorted(missing.items())),
        steps_failed=dict(sorted(failed.items())),
        hardware=hardware,
        started_at=started_at,
        finished_at=finished_at,
    )


def _no_progress(_position: int, _total: int, _law: BatchLaw) -> None:
    """Nobody watches the batch: batch.json says how it went."""


def run_batch(
    planned: Sequence[PlannedLaw],
    *,
    inputs: CollectInputs,
    settings: BatchSettings,
    fetcher: CachedFetcher,
    clock: Callable[[], datetime],
    timer: Callable[[], float] = perf_counter,
    on_law: Callable[[int, int, BatchLaw], None] = _no_progress,
) -> tuple[BatchRun, Path]:
    """Run every planned law in order and write `data/laws/batch.json` after each one.

    Returns the finished batch and where it was written. Linear in the number of laws;
    each law costs what its collect and steps cost (collect scans the amendment dumps
    once per law, which dominates the cheap steps).
    """
    root = settings.collect.data_root
    path = root / "laws" / BATCH_FILE
    hardware = settings.collect.hardware or platform.platform()
    context = _Context(
        inputs, settings, fetcher, clock, timer, StepRunner(root, inputs.hys_index, clock)
    )
    started_at = clock()
    laws: list[BatchLaw] = []

    def write(finished_at: datetime | None) -> BatchRun:
        run = BatchRun(
            selection=settings.selection,
            steps=settings.steps,
            attachments=settings.collect.attachments,
            refresh=settings.collect.refresh,
            code_revision=settings.collect.code_revision,
            banner=coverage_banner(
                laws,
                selected=len(planned),
                hardware=hardware,
                started_at=started_at,
                finished_at=finished_at,
            ),
            laws=tuple(laws),
        )
        write_bytes_atomic(path, run.model_dump_json(indent=2).encode("utf-8"))
        return run

    for position, law in enumerate(planned, start=1):
        laws.append(_run_law(law, context))
        write(None)
        on_law(position, len(planned), laws[-1])
    return write(clock()), path
