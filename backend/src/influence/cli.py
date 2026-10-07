"""The `influence` command: the pipeline without the web server, thin over the services.

`influence setup` fetches, once per machine, the global files every law's run reads: the
Parltrack dumps, the register export and the Have Your Say index.
`influence collect <law>` is Atlas part 1: it writes one law's public record under
`data/laws/<procedure>/`. `influence atlas <law>` collects, then runs parts 3 to 7 and
writes the view the explorer serves (`atlas.json`) and the law's coordinated amendments
(`coordinated.json`). `influence coordinated <law>` collects, then lists those near-identical
amendments tabled by different political groups. `influence lineage <law>` collects, then
traces the final act's new wording to the amendments and consultation documents that carry
it (`lineage.json`). `influence channels <law>` collects, then counts the channels the law
was lobbied through: consultation stages, timing, tabling Members and coalitions
(`channels.json`). `influence directions <law>` collects, then counts which way the
amendments move the law and, through the atlas view's published links, each actor's asks
(`directions.json`). `influence audit sample <law>` draws a seeded blind sample of the
view's links into two readers' sheets and a private key under `data/audit/`, and
`influence audit score <dir>` scores the filled sheets with Wilson intervals; neither
writes to a law's view. `influence forecast <law> [<law> ...]` reads every written atlas view,
validates the forecast on the completed laws and forecasts the named open laws' asks
(`data/laws/forecast.json`). `influence batch` runs collect and those steps over many laws, named
or every procedure amended since a date, resumably, into `data/laws/batch.json`.
`influence report <law> [<law> ...]` reads those files, without
collecting, and writes the public report (`data/laws/report.md`). Exit status: 0 when
every output was written, 1 on any input, source or output failure, 2 on a command-line
usage error.
"""

import argparse
import logging
import os
import platform
import ssl
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from time import perf_counter
from typing import cast

from pydantic import SecretStr

import influence
from influence.extraction.cache import CacheError, HttpCache
from influence.extraction.cli import default_data_root
from influence.extraction.fetching import CachedFetcher, UrllibFetcher
from influence.extraction.layout import LayoutError, procedure_slug
from influence.extraction.records import RecordError
from influence.repositories.hys import HysError, read_index
from influence.repositories.parltrack import ParltrackError
from influence.schemas.atlas import LinkTier
from influence.schemas.batch import BatchLaw, BatchRun, BatchSelection, BatchStep
from influence.schemas.coordinated import CoordinatedCluster, CoordinatedView
from influence.schemas.forecast_view import ForecastView
from influence.services import batch as batching
from influence.services.audit_sheets import (
    AuditFileError,
    SampledStatus,
    score_sample,
    write_result,
    write_sample,
)
from influence.services.channels import build_channels, publication_types, write_channels
from influence.services.collect import (
    AmbiguousLawError,
    CollectError,
    CollectInputs,
    CollectResult,
    CollectSettings,
    ResolvedLaw,
    collect_law,
    load_catalog,
    source_revision,
)
from influence.services.coordinated import build_coordination, write_coordination
from influence.services.direction import build_directions, write_directions
from influence.services.forecast import LeakageError
from influence.services.forecasting import (
    ForecastError,
    build_forecasts,
    read_evidence,
    resolve_law,
    write_forecasts,
)
from influence.services.jev import JevClient, JevError
from influence.services.jev_judge import JevJudge
from influence.services.lineage_assembly import build_lineage, write_lineage
from influence.services.pipeline import (
    Collected,
    PipelineError,
    build_view,
    load_collected,
    read_view,
    remove_stale_view,
    write_view,
)
from influence.services.report import (
    DEFAULT_LINKS,
    DEFAULT_SEED,
    REPORT_FILE,
    ReportError,
    build_report,
    load_law,
    resolve_slug,
    write_report,
)
from influence.services.setup import GROUPS, SetupError, SetupFile, SetupGroup, setup_data

JEV_KEY_VARIABLE = "TYPESAFE_API_KEY"

# Clusters `influence coordinated` prints; the file holds all of them.
CLUSTERS_SHOWN = 10
# Political groups and actors `influence directions` prints; the file holds all of them.
GROUPS_SHOWN = 10
QUOTE_CHARACTERS = 200
# The index crawl asks about 4,170 pages over about 35 minutes; a line per 250 shows it
# is moving without flooding the terminal.
CRAWL_REPORT_EVERY = 250


def _count(value: str) -> int:
    try:
        count = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"not an integer: {value!r}") from error
    if count < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {count}")
    return count


def _groups(value: str) -> tuple[SetupGroup, ...]:
    """`parltrack,register` as setup groups, in run order whatever order was typed."""
    named = {name.strip() for name in value.split(",")}
    unknown = sorted(named - set(GROUPS))
    if unknown:
        listed = ", ".join(repr(name) for name in unknown)
        raise argparse.ArgumentTypeError(f"unknown {listed}; choose from {','.join(GROUPS)}")
    return tuple(group for group in GROUPS if group in named)


def _crawl_progress(done: int, total: int | None) -> None:
    if done % CRAWL_REPORT_EVERY == 0 or done == total:
        print(f"  Have Your Say index: {done} of {total or '?'} initiatives", file=sys.stderr)


def _print_setup(root: Path, files: Sequence[SetupFile]) -> None:
    print(f"  {'file':<46}{'bytes':>13}  {'sha256':<14}action")
    for item in files:
        name = item.path.relative_to(root).as_posix()
        print(f"  {name:<46}{item.byte_count:>13,}  {item.sha256[:12]:<14}{item.action}")


def _setup(data_root: Path | None, groups: tuple[SetupGroup, ...], *, refresh: bool) -> int:
    root = data_root if data_root is not None else default_data_root()
    source = UrllibFetcher()
    fetcher = CachedFetcher(cache=HttpCache(root / "cache"), fetcher=source, streamer=source.stream)
    started = perf_counter()
    done: list[SetupFile] = []
    files = setup_data(
        root, groups=groups, fetcher=fetcher, refresh=refresh, progress=_crawl_progress
    )
    try:
        for item in files:
            # Not list(files): that list is lost when a file fails, and with it what finished.
            done.append(item)  # noqa: PERF402
    except (SetupError, CacheError, ParltrackError, OSError) as error:
        print(f"Stopped after {perf_counter() - started:.1f} s; finished before the error:")
        _print_setup(root, done)
        print(f"error: {error}", file=sys.stderr)
        print("The files listed are complete; rerun to fetch the rest.", file=sys.stderr)
        return 1
    print(f"Set up {root.absolute()} in {perf_counter() - started:.1f} s")
    _print_setup(root, done)
    return 0


def _print_resolved(query: str, law: ResolvedLaw) -> None:
    """Printed before the stages run, so a wrong law can be stopped before it takes minutes."""
    if law.entry is None:
        found = "which the Parltrack dossiers dump does not hold"
    else:
        found = f"titled {law.entry.title!r} in the Parltrack dossiers dump"
    print(f"Resolved {query!r} to {law.procedure_id}, {found}", flush=True)


def _print_collected(result: CollectResult, elapsed: float) -> None:
    law = result.law
    print(f"Collected {law.procedure_id} {law.title} in {elapsed:.1f} s")
    print(f"  {'layer':<22}{'status':<15}{'count':>7}  reason")
    for item in law.coverage:
        count = "" if item.count is None else str(item.count)
        print(f"  {item.layer:<22}{item.status:<15}{count:>7}  {item.reason or ''}".rstrip())
    print(f"bundle:   {result.bundle.absolute()}")
    print(f"manifest: {result.manifest_path.absolute()}")


def _coordination(collected: Collected, generated_at: datetime) -> CoordinatedView:
    return build_coordination(
        collected.law,
        collected.manifest.run_id,
        collected.amendments,
        collected.actors,
        generated_at=generated_at,
    )


def _print_coordination(view: CoordinatedView) -> list[CoordinatedCluster]:
    """The one summary line both commands print; returns the clusters that span groups."""
    counts = view.counts
    crossing = [cluster for cluster in view.clusters if cluster.cross_group]
    print(
        f"Coordinated amendments: {len(crossing)} of {len(view.clusters)} clusters span "
        f"political groups ({counts.amendments} amendments: {counts.compared} compared, "
        f"{counts.too_short} too short, {counts.not_comparable} not comparable)"
    )
    return crossing


def _build_view(result: CollectResult) -> int:
    try:
        collected = load_collected(result.bundle)
        now = datetime.now(UTC)
        view = build_view(collected, generated_at=now)
        coordination = _coordination(collected, now)
        # Both are built before either is written, and the view last: the API lists a law
        # by its view, so a listed law always has the clusters of the same run beside it.
        clusters = write_coordination(coordination, result.bundle)
        path = write_view(view, result.bundle)
    except (PipelineError, RecordError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        print("The collected bundle is kept; no view was written.", file=sys.stderr)
        # A view of an earlier collect run would otherwise be served beside this run's records.
        if remove_stale_view(result.bundle, result.manifest.run_id):
            print("The view of an earlier collect run was removed.", file=sys.stderr)
        return 1
    statuses = Counter(link.status for link in view.bundle.links)
    print(
        f"Atlas: {statuses['published']} published, {statuses['unconfirmed']} unconfirmed, "
        f"{statuses['contradicted']} contradicted links; graph of "
        f"{len(view.snapshot.nodes)} nodes and {len(view.snapshot.edges)} edges"
    )
    _print_coordination(coordination)
    print(f"view:     {path.absolute()}")
    print(f"clusters: {clusters.absolute()}")
    return 0


def _list_coordinated(result: CollectResult) -> int:
    try:
        view = _coordination(load_collected(result.bundle), datetime.now(UTC))
        path = write_coordination(view, result.bundle)
    except (PipelineError, RecordError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        print("The collected bundle is kept; no cluster file was written.", file=sys.stderr)
        return 1
    crossing = _print_coordination(view)
    for position, cluster in enumerate(crossing[:CLUSTERS_SHOWN], start=1):
        print(
            f"  {position}. {len(cluster.members)} amendments, "
            f"{'/'.join(cluster.political_groups)}, at least {cluster.inserted_words} "
            f"inserted words, least similar pair {cluster.min_similarity:.2f}"
        )
        for member in cluster.members:
            groups = "/".join(member.political_groups) or "group unknown"
            print(
                f"     {member.amendment_id}  {member.tabled_on or 'undated'}  [{groups}]  "
                f"{member.target_provision or 'provision unknown'}"
            )
        quote = " ... ".join(span.text for span in cluster.members[0].inserted)
        print(f'     "{" ".join(quote.split())[:QUOTE_CHARACTERS]}"')
    print(f"clusters: {path.absolute()}")
    return 0


def _jev_judge(data_root: Path, max_usd: float) -> JevJudge:
    """Jev keyed from the environment; answers are cached under the data root."""
    key = os.environ.get(JEV_KEY_VARIABLE, "")
    if not key.strip():
        raise JevError(f"--jev needs the TypeSafe key in {JEV_KEY_VARIABLE}")
    if not 0 < max_usd < float("inf"):
        raise JevError("--jev-max-usd must be a positive amount")
    client = JevClient(SecretStr(key), ssl.create_default_context())
    return JevJudge(client=client, cache=data_root / "cache" / "jev", max_usd=max_usd)


def _list_lineage(result: CollectResult, judge: JevJudge | None = None) -> int:
    try:
        view = build_lineage(
            load_collected(result.bundle), generated_at=datetime.now(UTC), judge=judge
        )
        path = write_lineage(view, result.bundle)
    except (PipelineError, RecordError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        print("The collected bundle is kept; no lineage file was written.", file=sys.stderr)
        return 1
    counts = view.counts
    if view.status == "unknown":
        print(f"Lineage: unknown ({view.reason})")
    else:
        print(
            f"Lineage: {counts.adopted_phrases} adopted phrases from {counts.amendments_adopting} "
            f"of {counts.amendments} amendments; {counts.linked_units} of {counts.changed_units} "
            "new words of the final act traced to an amendment"
        )
        documents = (
            "origins unknown (no consultation text)"
            if counts.documents_read is None
            else f"{counts.documents_with_origin} of {counts.documents_read} consultation "
            "documents say adopted or tabled wording first"
        )
        print(f"  {documents}")
        for credit in [c for c in view.credits if c.holder_kind == "mep"][:CLUSTERS_SHOWN]:
            print(
                f"  {credit.name}: {credit.amendments} of {credit.amendments_tabled} amendments "
                f"adopted, {credit.phrases} phrase(s) ({credit.joint_phrases} joint)"
            )
    print(f"lineage: {path.absolute()}")
    print(f"explorer: http://localhost:3000/lineage?law={view.slug}")
    return 0


def _list_channels(result: CollectResult, index: Path) -> int:
    try:
        collected = load_collected(result.bundle)
        types = publication_types(read_index(index)) if index.is_file() else None
        view = build_channels(
            collected.law,
            collected.manifest.run_id,
            documents=collected.documents,
            passages=collected.passages,
            actors=collected.actors,
            amendments=collected.amendments,
            types=types,
            generated_at=datetime.now(UTC),
        )
        path = write_channels(view, result.bundle)
    except (PipelineError, RecordError, HysError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        print("The collected bundle is kept; no channels file was written.", file=sys.stderr)
        return 1
    consultation, timing, meps, coalitions = (
        view.consultation,
        view.timing.feedback_vs_proposal,
        view.meps,
        view.coalitions,
    )
    print(
        f"Consultation: {consultation.feedback} feedback from {consultation.submitters} "
        f"submitters on {len(consultation.by_publication)} publication(s); "
        f"{consultation.organisations_with_register_id} of {consultation.organisations} "
        "organisations carry a register ID"
    )
    for publication in consultation.by_publication:
        print(
            f"  publication {publication.publication_id or 'unknown'} "
            f"({publication.publication_type or 'type unknown'}): {publication.feedback} feedback"
        )
    print(
        f"Timing: of {timing.total} feedback, {timing.before} before the proposal, "
        f"{timing.on_or_after} on or after, {timing.undated} undated, "
        f"{timing.unplaced} with no proposal date to place them"
    )
    groups = ", ".join(f"{item.key} {item.count}" for item in meps.by_political_group)
    print(
        f"Members: {meps.amendments} amendments by {meps.tabling_meps} Members "
        f"({meps.no_known_author} with no known author); by group: {groups or 'none known'}"
    )
    print(
        f"Coalitions: {coalitions.cosigned_across_groups} of {coalitions.amendments} amendments "
        f"co-signed across groups; {coalitions.cross_group_clusters} coordinated clusters "
        f"across groups hold {coalitions.amendments_in_cross_group_clusters} amendments"
    )
    for row in view.votes_and_meetings:
        print(f"{row.layer.capitalize()}: {row.status} ({row.reason})")
    print(f"channels: {path.absolute()}")
    return 0


def _counted(pairs: Sequence[tuple[str, int]]) -> str:
    return ", ".join(f"{name} {count}" for name, count in pairs if count) or "none"


def _list_directions(result: CollectResult) -> int:
    try:
        collected = load_collected(result.bundle)
        view = build_directions(
            collected.law,
            collected.manifest.run_id,
            collected.amendments,
            collected.actors,
            # The collect bundle is `<data root>/laws/<slug>`, where `atlas` writes its view.
            read_view(result.bundle.parent.parent, result.bundle.name),
            generated_at=datetime.now(UTC),
        )
        path = write_directions(view, result.bundle)
    except (PipelineError, RecordError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        print("The collected bundle is kept; no directions file was written.", file=sys.stderr)
        return 1
    print(f"Directions of {view.amendments} amendments: {_counted(view.counts.pairs())}")
    for stage in view.by_stage:
        print(f"  {stage.stage}: {_counted(stage.counts.pairs())}")
    for group in view.by_group[:GROUPS_SHOWN]:
        print(f"  {group.group} ({group.amendments}): {_counted(group.counts.pairs())}")
    if view.actors_reason is not None:
        print(f"Actors: {view.actors_status}: {view.actors_reason}")
    for actor in view.actors[:GROUPS_SHOWN]:
        print(
            f"  {actor.name} ({actor.published_links} published links): "
            f"{_counted(actor.counts.pairs())}"
        )
    for example in view.examples:
        quote = " ".join(example.span.text.split())[:QUOTE_CHARACTERS]
        print(f'  {example.direction:<9}{example.amendment_id}  "{quote}"')
    print(f"directions: {path.absolute()}")
    return 0


def _slug(value: str) -> str:
    """A procedure number or a slug as the slug of the law's directory."""
    try:
        return procedure_slug(value)
    except LayoutError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _audit_sample(
    slug: str,
    data_root: Path | None,
    *,
    size: int,
    seed: int,
    status: SampledStatus,
    tier: LinkTier | None,
) -> int:
    root = data_root if data_root is not None else default_data_root()
    try:
        view = read_view(root, slug)
        if view is None:
            raise AuditFileError(
                f"No atlas view at {root / 'laws' / slug}; run `make atlas` for the law first "
                "and name it by procedure number or slug"
            )
        files = write_sample(view, root / "audit", size=size, seed=seed, status=status, tier=tier)
    except (PipelineError, AuditFileError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    key = files.key
    strata = Counter(item.stratum for item in key.items)
    print(
        f"Sampled {len(key.items)} of {key.population} {status} links of {key.procedure_id} "
        f"(run {key.run_id}) with seed {seed}: "
        + ", ".join(f"{name} {count}" for name, count in sorted(strata.items()))
    )
    print(key.purpose)
    for reader in ("a", "b"):
        print(f"reader {reader}: {(files.directory / f'reader-{reader}.csv').absolute()}")
    print(f"key:      {(files.directory / 'key.json').absolute()}  (keep it from the readers)")
    print("Each reader fills verdict (yes, no or unsure) and note alone; then run audit score.")
    return 0


def _audit_score(directory: Path) -> int:
    try:
        result = score_sample(directory)
        data, summary = write_result(result, directory)
    except (AuditFileError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    for row in (*result.strata, result.overall):
        precision = "n/a" if row.precision is None else f"{row.precision:.3f}"
        print(
            f"  {row.stratum}: {row.agreed_correct} agreed correct, {row.agreed_incorrect} "
            f"agreed incorrect, {row.disagreements} split, {row.unlabelled} unlabelled; "
            f"precision {precision} (95% {row.low:.3f} to {row.high:.3f})"
        )
    if result.threshold is not None:
        cut = result.threshold.proposed_cut
        print(
            "Proposed prose threshold (a proposal, not applied): "
            + ("none reaches" if cut is None else f"{cut:.2f} is the lowest cut reaching")
            + f" a lower bound of {result.threshold.floor:.2f}"
        )
    print(f"result:  {data.absolute()}")
    print(f"summary: {summary.absolute()}")
    return 0


def _forecast(queries: Sequence[str], data_root: Path | None) -> int:
    root = data_root if data_root is not None else default_data_root()
    try:
        laws, problems = read_evidence(root)
        targets = {resolve_law(query, [law.law for law in laws]).procedure_id for query in queries}
        view = build_forecasts(
            laws,
            {law.slug for law in laws if law.law.procedure_id in targets},
            generated_at=datetime.now(UTC),
            problems=problems,
        )
        path = write_forecasts(view, root)
    except (ForecastError, LeakageError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        print("No forecast file was written.", file=sys.stderr)
        return 1
    _print_forecast(view)
    print(f"forecast: {path.absolute()}")
    return 0


def _print_forecast(view: ForecastView) -> None:
    check = view.validation
    print(
        f"History: {check.training_examples} decided asks ({check.training_wins} won) from "
        f"{check.training_laws} completed law(s); {check.tested_splits} of {check.splits} "
        f"rolling splits tested on {check.test_examples} asks"
    )
    if check.adequate:
        print(
            f"Probabilities published: Brier {check.model_brier:.3f} against prevalence "
            f"{check.baseline_brier:.3f}"
        )
    else:
        print("No probability published; scenarios only, because:")
        for reason in check.reasons:
            print(f"  {reason}")
    rule = view.fallback_rule
    print(f"Fallback rule {rule.rule}: {'computable' if rule.computable else 'not computable'}")
    for law in view.laws:
        role = "target" if law.target else "history"
        excluded = ", ".join(f"{reason} {count}" for reason, count in law.excluded.items())
        print(
            f"  {law.procedure_id} ({law.status}, {role}): {law.asks} asks, "
            f"{law.training_examples} trained, {law.forecasts} forecast; "
            f"excluded: {excluded or 'none'}"
        )
        if law.note is not None:
            print(f"    {law.note}")
    kinds = Counter(item.scenario or item.score_type for item in view.forecasts)
    for kind, count in sorted(kinds.items()):
        print(f"  {count} x {kind}")
    for limitation in view.limitations:
        if limitation.startswith("Skipped view"):
            print(f"  {limitation}")


def _report(
    queries: Sequence[str], data_root: Path | None, out: Path | None, links: int, seed: int
) -> int:
    """Read what the other commands wrote and write the public report; collects nothing."""
    root = data_root if data_root is not None else default_data_root()
    # `make report LAW='AI Act, 2022/0140(COD)'` passes several laws as one argument.
    names = [name.strip() for query in queries for name in query.split(",") if name.strip()]
    try:
        slugs = dict.fromkeys(resolve_slug(root, name) for name in names)
        laws = [load_law(root, slug) for slug in slugs]
        report = build_report(laws, generated_at=datetime.now(UTC), links=links, seed=seed)
        path = write_report(report, out if out is not None else root / "laws" / REPORT_FILE)
    except (ReportError, PipelineError, RecordError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        print("No report was written.", file=sys.stderr)
        return 1
    print("\n".join(report.headlines))
    print()
    print("\n".join(report.links).rstrip())
    print()
    print(f"report: {path.absolute()}")
    return 0


def _collect(
    query: str,
    data_root: Path | None,
    *,
    refresh: bool,
    attachments: bool,
    then: Callable[[CollectResult], int] | None = None,
) -> int:
    # pypdf warns about every unusual font in every attachment, hundreds of lines per law;
    # none of it changes the extracted text, and it buries the result on the console.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    root = data_root if data_root is not None else default_data_root()
    settings = CollectSettings(
        data_root=root,
        code_revision=source_revision(Path(influence.__file__).parent),
        attachments=attachments,
        refresh=refresh,
        hardware=platform.platform(),
    )
    fetcher = CachedFetcher(cache=HttpCache(root / "cache"), fetcher=UrllibFetcher())
    started = perf_counter()
    try:
        result = collect_law(
            query,
            inputs=CollectInputs.under(root),
            settings=settings,
            fetcher=fetcher,
            clock=lambda: datetime.now(UTC),
            on_resolved=lambda law: _print_resolved(query, law),
        )
    except AmbiguousLawError as error:
        print(f"error: {query!r} names more than one procedure:", file=sys.stderr)
        for procedure, title in error.choices:
            print(f"  {procedure}  {title}", file=sys.stderr)
        print("Rerun with one procedure number.", file=sys.stderr)
        return 1
    except (CollectError, CacheError, RecordError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        print("No manifest was published for this run.", file=sys.stderr)
        return 1
    _print_collected(result, perf_counter() - started)
    return then(result) if then is not None else 0


def _law_names(value: str) -> tuple[str, ...]:
    names = tuple(name.strip() for name in value.split(",") if name.strip())
    if not names:
        raise argparse.ArgumentTypeError("name at least one law")
    return names


def _year(value: str) -> date:
    """`2019` as 1 January 2019, the first day an amendment may be tabled on."""
    try:
        return date(int(value), 1, 1)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"not a year: {value!r}") from error


def _steps(value: str) -> tuple[BatchStep, ...]:
    """`lineage,atlas` as batch steps, in run order whatever order was typed."""
    named = {name.strip() for name in value.split(",")}
    unknown = sorted(named - set(batching.STEPS))
    if unknown:
        listed = ", ".join(repr(name) for name in unknown)
        raise argparse.ArgumentTypeError(
            f"unknown {listed}; choose from {','.join(batching.STEPS)}"
        )
    return tuple(step for step in batching.STEPS if step in named)


def _print_batch_law(position: int, total: int, law: BatchLaw) -> None:
    steps = ", ".join(
        f"{step.step} {step.status}"
        + (f" {step.seconds:.1f} s" if step.status in ("done", "failed") else "")
        for step in law.steps
    )
    amendments = "" if law.amendments is None else f"; {law.amendments:,} amendments"
    print(
        f"[{position}/{total}] {law.procedure_id or law.query} {law.status} "
        f"in {law.seconds:.1f} s ({steps or 'nothing run'}){amendments}",
        flush=True,
    )
    for step in law.steps:
        if step.error is not None:
            print(f"  {step.step}: {step.error}", file=sys.stderr)
    if law.error is not None:
        print(f"  {law.error}", file=sys.stderr)


def _print_banner(run: BatchRun, path: Path) -> None:
    banner = run.banner
    print(
        f"Batch: {banner.laws_attempted} of {banner.laws_selected} laws attempted, "
        f"{banner.laws_complete} complete, {banner.laws_partial} partial, "
        f"{banner.laws_failed} failed; {banner.amendments_covered:,} amendments covered"
    )
    missing = ", ".join(f"{layer} {count}" for layer, count in banner.layers_missing.items())
    print(f"  layers not complete (laws): {missing or 'none'}")
    failed = ", ".join(f"{step} {count}" for step, count in banner.steps_failed.items())
    print(f"  steps failed (laws): {failed or 'none'}")
    print(f"  hardware: {banner.hardware}")
    print(f"  started {banner.started_at}, finished {banner.finished_at}")
    print(f"batch: {path.absolute()}")


def _batch(
    data_root: Path | None,
    selection: BatchSelection,
    steps: tuple[BatchStep, ...],
    *,
    refresh: bool,
    attachments: bool,
) -> int:
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    root = data_root if data_root is not None else default_data_root()
    inputs = CollectInputs.under(root)
    fetcher = CachedFetcher(cache=HttpCache(root / "cache"), fetcher=UrllibFetcher())
    absent = inputs.missing()
    if absent:
        listed = ", ".join(str(path) for path in absent)
        print(f"error: required input files are missing: {listed}", file=sys.stderr)
        print("Run `make setup` first.", file=sys.stderr)
        return 1
    try:
        catalog = load_catalog(inputs.dossiers, root / "catalog")
        if selection.since is None:
            planned = batching.plan_named(selection.laws, catalog, fetcher)
        else:
            print(
                f"Scanning the amendment dumps for amendments tabled since {selection.since}",
                flush=True,
            )
            counts = batching.amended_since(
                (inputs.committee_amendments, inputs.plenary_amendments), selection.since
            )
            planned = batching.plan_since(catalog, counts, selection.limit)
    except (CollectError, ParltrackError) as error:
        print(f"error: {error}", file=sys.stderr)
        print("No law was run.", file=sys.stderr)
        return 1
    print(f"Batch of {len(planned)} laws; steps: collect, {', '.join(steps)}", flush=True)
    settings = batching.BatchSettings(
        collect=CollectSettings(
            data_root=root,
            code_revision=source_revision(Path(influence.__file__).parent),
            attachments=attachments,
            refresh=refresh,
            hardware=platform.platform(),
        ),
        steps=steps,
        selection=selection,
    )
    run, path = batching.run_batch(
        planned,
        inputs=inputs,
        settings=settings,
        fetcher=fetcher,
        clock=lambda: datetime.now(UTC),
        on_law=_print_batch_law,
    )
    _print_banner(run, path)
    return 0 if run.banner.laws_complete == len(run.laws) else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="influence", description="influence commands that run without the server."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser(
        "setup",
        help="download the Parltrack dumps and the register; build the Have Your Say index",
        description=(
            "Fetch, once per machine, the global files `influence collect` reads into the "
            "data root. A file already present is kept unless --refresh is given."
        ),
    )
    setup.add_argument("--data-root", type=Path, default=None, help="overrides INFLUENCE_DATA_ROOT")
    setup.add_argument(
        "--refresh", action="store_true", help="fetch every chosen file again and replace it"
    )
    setup.add_argument(
        "--only",
        type=_groups,
        default=GROUPS,
        metavar="GROUPS",
        help=(
            f"comma-separated subset of {','.join(GROUPS)} (default: all); the index "
            "crawl takes about 35 minutes uncached"
        ),
    )
    for name, summary in (
        ("collect", "collect one law's public record into data/laws/<procedure>/"),
        ("atlas", "collect one law, then build the explorer's view of it (parts 1 to 7)"),
        (
            "coordinated",
            "collect one law, then list near-identical amendments tabled by different "
            "political groups",
        ),
        (
            "lineage",
            "collect one law, then trace the final act's new wording to the amendments and "
            "consultation documents that carry it",
        ),
        ("channels", "collect one law, then count the channels it was lobbied through"),
        (
            "directions",
            "collect one law, then count which way its amendments and, through published "
            "links, each actor's asks move it",
        ),
    ):
        command = commands.add_parser(
            name,
            help=summary,
            description=(
                "Resolve a law (procedure number, CELEX, COM reference, common name or "
                f"title), then {summary}."
            ),
        )
        command.add_argument(
            "query", nargs="+", help="for example 2021/0106(COD), 32024R1689 or 'AI Act'"
        )
        command.add_argument(
            "--data-root", type=Path, default=None, help="overrides INFLUENCE_DATA_ROOT"
        )
        command.add_argument(
            "--refresh", action="store_true", help="redo every stage and refetch cached answers"
        )
        command.add_argument(
            "--no-attachments",
            action="store_true",
            help="skip submission attachments (faster; the asks layer is then partial)",
        )
        if name == "lineage":
            command.add_argument(
                "--jev",
                action="store_true",
                help=f"add reworded origins judged by Jev; reads the key from {JEV_KEY_VARIABLE}",
            )
            command.add_argument(
                "--jev-max-usd",
                type=float,
                default=1.0,
                help="stop asking Jev before this much could be spent (default 1)",
            )
    audit = commands.add_parser(
        "audit",
        help="blind audit: draw two readers' sheets from a view, then score them",
        description="Blind audit of a law's links; labels live under data/audit/ only.",
    )
    audits = audit.add_subparsers(dest="audit_command", required=True)
    sample = audits.add_parser(
        "sample",
        help="draw a seeded stratified sample into two blind sheets and a private key",
        description=(
            "Read the law's atlas.json and write data/audit/<slug>/<sample id>/reader-a.csv, "
            "reader-b.csv and key.json. The sheets carry no link ID, score, tier or status."
        ),
    )
    sample.add_argument(
        "law", type=_slug, help="procedure number or slug, for example 2021/0106(COD)"
    )
    sample.add_argument("--size", type=_count, default=40, help="links to draw (default 40)")
    sample.add_argument("--seed", type=int, required=True, help="seed of the draw, recorded")
    sample.add_argument(
        "--status",
        choices=("published", "unconfirmed"),
        default="published",
        help=(
            "published (default, gate 7) or unconfirmed (the PROPOSED re-scope: sample held-back "
            "prose links to propose a threshold)"
        ),
    )
    sample.add_argument(
        "--tier", choices=("copied", "reworded"), default=None, help="sample one tier only"
    )
    sample.add_argument(
        "--data-root", type=Path, default=None, help="overrides INFLUENCE_DATA_ROOT"
    )
    score = audits.add_parser(
        "score",
        help="score two filled sheets against the key: precision with Wilson intervals",
        description=(
            "Read reader-a.csv, reader-b.csv and key.json in DIRECTORY and write "
            "audit-result.json and audit-summary.md beside them."
        ),
    )
    score.add_argument("directory", type=Path, help="the sample directory audit sample wrote")
    forecast = commands.add_parser(
        "forecast",
        help="forecast the open asks of named laws from every written atlas view",
        description=(
            "Read every atlas view under the data root, validate the forecast on the completed "
            "laws' decided asks with rolling time splits, and forecast the open asks of the "
            "named laws into data/laws/forecast.json. A probability is published only when "
            "validation beats the prevalence baseline; otherwise each forecast is a scenario."
        ),
    )
    forecast.add_argument(
        "laws",
        nargs="+",
        help="laws with an atlas view: slug, procedure number, CELEX, COM reference or name",
    )
    forecast.add_argument(
        "--data-root", type=Path, default=None, help="overrides INFLUENCE_DATA_ROOT"
    )
    batch = commands.add_parser(
        "batch",
        help="collect many laws and run the per-law steps on each, resumably",
        description=(
            "Collect each selected law, then run the chosen steps on it, writing "
            "data/laws/batch.json after every law. A law already collected is not collected "
            "again, and a step whose output carries the current collect run is skipped, "
            "unless --refresh is given. A failing law is recorded and the batch goes on."
        ),
    )
    chosen = batch.add_mutually_exclusive_group(required=True)
    chosen.add_argument(
        "--laws",
        type=_law_names,
        metavar="NAMES",
        help="comma-separated procedure numbers, CELEX, COM references or names: 'AI Act,DSA'",
    )
    chosen.add_argument(
        "--since",
        type=_year,
        metavar="YEAR",
        help="with --with-amendments: every catalog procedure amended since 1 January YEAR",
    )
    batch.add_argument(
        "--with-amendments",
        action="store_true",
        help="select by amendments tabled (the one --since rule built so far)",
    )
    batch.add_argument(
        "--limit", type=_count, default=None, help="with --since: the N most amended procedures"
    )
    batch.add_argument(
        "--steps",
        type=_steps,
        default=batching.DEFAULT_STEPS,
        metavar="STEPS",
        help=(
            f"comma-separated subset of {','.join(batching.STEPS)} "
            f"(default: {','.join(batching.DEFAULT_STEPS)}; atlas takes minutes a law)"
        ),
    )
    batch.add_argument(
        "--attachments",
        action="store_true",
        help="read submission attachments (slower; skipped by default, so asks are partial)",
    )
    batch.add_argument(
        "--refresh", action="store_true", help="collect every law again and redo every step"
    )
    batch.add_argument("--data-root", type=Path, default=None, help="overrides INFLUENCE_DATA_ROOT")
    report = commands.add_parser(
        "report",
        help="write the public report from the files the other commands wrote",
        description=(
            "Write the Markdown report (WHO, WHAT, TOWARDS, HOW, NEXT, links side by side) "
            "for one or more collected laws. It reads atlas.json, coordinated.json, "
            "channels.json, directions.json, lineage.json and forecast.json, and says which "
            "are missing; it collects and computes nothing."
        ),
    )
    report.add_argument(
        "laws", nargs="+", help="procedure numbers, CELEX, COM references or titles; commas split"
    )
    report.add_argument(
        "--data-root", type=Path, default=None, help="overrides INFLUENCE_DATA_ROOT"
    )
    report.add_argument(
        "--out", type=Path, default=None, help=f"default: <data root>/laws/{REPORT_FILE}"
    )
    report.add_argument(
        "--links",
        type=_count,
        default=DEFAULT_LINKS,
        help=f"published links to draw at random and show side by side (default {DEFAULT_LINKS})",
    )
    report.add_argument(
        "--seed", type=int, default=DEFAULT_SEED, help=f"sample seed (default {DEFAULT_SEED})"
    )
    args = parser.parse_args(argv)
    if args.command == "setup":
        return _setup(
            cast("Path | None", args.data_root),
            cast("tuple[SetupGroup, ...]", args.only),
            refresh=cast("bool", args.refresh),
        )
    if args.command == "audit":
        if args.audit_command == "score":
            return _audit_score(cast("Path", args.directory))
        return _audit_sample(
            cast("str", args.law),
            cast("Path | None", args.data_root),
            size=cast("int", args.size),
            seed=cast("int", args.seed),
            status=cast("SampledStatus", args.status),
            tier=cast("LinkTier | None", args.tier),
        )
    if args.command == "forecast":
        return _forecast(cast("list[str]", args.laws), cast("Path | None", args.data_root))
    if args.command == "batch":
        since = cast("date | None", args.since)
        limit = cast("int | None", args.limit)
        if (since is not None) != cast("bool", args.with_amendments):
            parser.error("--since and --with-amendments go together")
        if since is None and limit is not None:
            parser.error("--limit applies to --since only")
        laws = cast("tuple[str, ...] | None", args.laws) or ()
        return _batch(
            cast("Path | None", args.data_root),
            BatchSelection(
                mode="laws" if since is None else "since", laws=laws, since=since, limit=limit
            ),
            cast("tuple[BatchStep, ...]", args.steps),
            refresh=cast("bool", args.refresh),
            attachments=cast("bool", args.attachments),
        )
    judge: JevJudge | None = None
    if args.command == "lineage" and cast("bool", args.jev):
        try:
            judge = _jev_judge(
                cast("Path | None", args.data_root) or default_data_root(),
                cast("float", args.jev_max_usd),
            )
        except JevError as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
    after: dict[str, Callable[[CollectResult], int] | None] = {
        "collect": None,
        "atlas": _build_view,
        "coordinated": _list_coordinated,
        "lineage": lambda result: _list_lineage(result, judge),
        "channels": lambda result: _list_channels(
            result,
            CollectInputs.under(
                cast("Path | None", args.data_root) or default_data_root()
            ).hys_index,
        ),
        "directions": _list_directions,
    }
    if args.command == "report":
        return _report(
            cast("list[str]", args.laws),
            cast("Path | None", args.data_root),
            cast("Path | None", args.out),
            cast("int", args.links),
            cast("int", args.seed),
        )
    return _collect(
        " ".join(cast("list[str]", args.query)),
        cast("Path | None", args.data_root),
        refresh=cast("bool", args.refresh),
        attachments=not cast("bool", args.no_attachments),
        then=after[cast("str", args.command)],
    )
