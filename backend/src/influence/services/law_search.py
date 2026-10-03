"""Part 8 · Publish: find any law the jury names, and build its files from the explorer.

Search runs the commands' own resolver (`collect.resolve_law`) over the Parltrack dossiers
catalog, which is loaded once per service and kept: about 24,000 procedures, a few
megabytes in memory, and a hash of the dossiers dump plus a read of the cached catalog
(seconds) on the first request. A build runs, in one background thread, the same
`collect_law` and per-law steps (`batch.StepRunner`) the commands run; one build at a
time per process. Collect runs without attachments for speed. Build state is kept in
memory only, so a restarted server reports no earlier build.
"""

import logging
import platform
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from time import perf_counter

from influence.extraction.fetching import CachedFetcher
from influence.extraction.layout import procedure_slug
from influence.repositories.parltrack import ProcedureEntry
from influence.schemas.batch import BatchStep
from influence.schemas.laws import BuildState, BuildStatus, LawHit, LawSearch
from influence.services import lineage_assembly, pipeline
from influence.services.batch import STEPS, StepRunner
from influence.services.collect import (
    AmbiguousLawError,
    CollectError,
    CollectInputs,
    CollectSettings,
    collect_law,
    load_catalog,
    resolve_law,
)

LOG_LINES = 20
LOGGER = logging.getLogger(__name__)
# One build at a time in the whole process: two collects would race on the same caches.
_BUILD_LOCK = threading.Lock()


class CatalogMissingError(RuntimeError):
    """`make setup` has not been run: there is no Parltrack dossiers dump to search."""


class BuildBusyError(RuntimeError):
    """Another build is running."""


class UnknownLawError(LookupError):
    """The slug names no procedure of the catalog."""


def _background(work: Callable[[], None]) -> None:
    threading.Thread(target=work, name="law-build", daemon=True).start()


@dataclass
class _Build:
    slug: str
    procedure_id: str
    steps: tuple[BatchStep, ...]
    started_at: datetime
    state: BuildStatus = "queued"
    step: str | None = None
    finished_at: datetime | None = None
    error: str | None = None
    log: deque[str] = field(default_factory=lambda: deque(maxlen=LOG_LINES))

    def snapshot(self) -> BuildState:
        return BuildState(
            slug=self.slug,
            procedure_id=self.procedure_id,
            state=self.state,
            step=self.step,
            steps=self.steps,
            started_at=self.started_at.isoformat(),
            finished_at=None if self.finished_at is None else self.finished_at.isoformat(),
            error=self.error,
            log=tuple(self.log),
        )


class LawService:
    def __init__(
        self,
        data_root: Path,
        *,
        fetcher: CachedFetcher,
        code_revision: str,
        clock: Callable[[], datetime],
        start: Callable[[Callable[[], None]], None] = _background,
    ) -> None:
        self._root = data_root
        self._inputs = CollectInputs.under(data_root)
        self._fetcher = fetcher
        self._revision = code_revision
        self._clock = clock
        self._start = start
        self._catalog: dict[str, ProcedureEntry] | None = None
        self._catalog_lock = threading.Lock()
        self._builds: dict[str, _Build] = {}

    def _entries(self) -> dict[str, ProcedureEntry]:
        """Slug -> catalog entry, loaded on first use and kept for the service's life."""
        with self._catalog_lock:
            if self._catalog is None:
                if not self._inputs.dossiers.is_file():
                    raise CatalogMissingError(
                        "Run `make setup` first: the Parltrack dossiers catalog is missing"
                    )
                catalog = load_catalog(self._inputs.dossiers, self._root / "catalog")
                self._catalog = {procedure_slug(e.procedure_id): e for e in catalog}
            return self._catalog

    def _hit(self, procedure_id: str, title: str) -> LawHit:
        slug = procedure_slug(procedure_id)
        bundle = self._root / "laws" / slug
        return LawHit(
            procedure_id=procedure_id,
            title=title,
            slug=slug,
            has_lineage=(bundle / lineage_assembly.VIEW_FILE).is_file(),
            has_atlas=(bundle / pipeline.VIEW_FILE).is_file(),
            build=self.build_state(slug),
        )

    def search(self, query: str) -> LawSearch:
        """Resolve `query` as `make collect LAW=...` would; linear in the catalog's size."""
        entries = self._entries()
        try:
            law = resolve_law(query, tuple(entries.values()), self._fetcher)
        except AmbiguousLawError as error:
            choices = tuple(self._hit(p, title) for p, title in error.choices)
            return LawSearch(
                query=query, status="ambiguous", law=None, choices=choices, message=str(error)
            )
        except CollectError as error:
            return LawSearch(
                query=query, status="not_found", law=None, choices=(), message=str(error)
            )
        if law.entry is None:
            return LawSearch(
                query=query,
                status="not_found",
                law=None,
                choices=(),
                message=f"{law.procedure_id} is not in the Parltrack dossiers catalog",
            )
        hit = self._hit(law.procedure_id, law.entry.title)
        return LawSearch(query=query, status="found", law=hit, choices=(hit,), message=None)

    def build_state(self, slug: str) -> BuildState | None:
        build = self._builds.get(slug)
        return None if build is None else build.snapshot()

    def start_build(self, slug: str, steps: tuple[BatchStep, ...]) -> BuildState:
        entry = self._entries().get(slug)
        if entry is None:
            raise UnknownLawError(f"No catalog procedure has the slug {slug}")
        if not _BUILD_LOCK.acquire(blocking=False):
            raise BuildBusyError("Another law is being built; wait for it to finish")
        ordered: tuple[BatchStep, ...] = tuple(step for step in STEPS if step in steps)
        build = _Build(slug, entry.procedure_id, ordered, self._clock())
        build.log.append(f"Queued {entry.procedure_id}: collect, {', '.join(ordered)}")
        self._builds[slug] = build
        self._start(lambda: self._run(build))
        return build.snapshot()

    def _run(self, build: _Build) -> None:
        try:
            self._steps(build)
        except Exception as error:
            LOGGER.exception("Build of %s failed", build.procedure_id)
            build.error = f"{type(error).__name__}: {error}"
            build.state = "failed"
            build.log.append(f"Failed: {build.error}")
        else:
            build.state, build.step = "done", None
            build.log.append("Done")
        finally:
            build.finished_at = self._clock()
            _BUILD_LOCK.release()

    def _steps(self, build: _Build) -> None:
        build.state, build.step = "running", "collect"
        build.log.append("Collecting without attachments (faster; attachment text is skipped)")
        began = perf_counter()
        settings = CollectSettings(
            data_root=self._root,
            code_revision=self._revision,
            attachments=False,
            hardware=platform.platform(),
        )
        result = collect_law(
            build.procedure_id,
            inputs=self._inputs,
            settings=settings,
            fetcher=self._fetcher,
            clock=self._clock,
        )
        build.log.append(f"collect done in {perf_counter() - began:.1f} s")
        collected = pipeline.load_collected(result.bundle)
        runner = StepRunner(self._root, self._inputs.hys_index, self._clock)
        for step in build.steps:
            build.step = step
            began = perf_counter()
            runner.run(step, collected, result.bundle)
            build.log.append(f"{step} done in {perf_counter() - began:.1f} s")
