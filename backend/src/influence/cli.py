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
(`directions.json`). `influence submit` is the first brief's pairs command, kept until
part 4 replaces it. Exit status: 0 when every output was written, 1 on any input, source
or output failure, 2 on a command-line usage error.
"""

import argparse
import logging
import platform
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import cast

import influence
from influence.extraction.cache import CacheError, HttpCache
from influence.extraction.cli import default_data_root
from influence.extraction.fetching import CachedFetcher, UrllibFetcher
from influence.extraction.records import RecordError
from influence.repositories.hys import HysError, read_index
from influence.repositories.parltrack import ParltrackError
from influence.schemas.coordinated import CoordinatedCluster, CoordinatedView
from influence.services.channels import build_channels, publication_types, write_channels
from influence.services.collect import (
    AmbiguousLawError,
    CollectError,
    CollectInputs,
    CollectResult,
    CollectSettings,
    ResolvedLaw,
    collect_law,
    source_revision,
)
from influence.services.coordinated import build_coordination, write_coordination
from influence.services.direction import build_directions, write_directions
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
from influence.services.setup import GROUPS, SetupError, SetupFile, SetupGroup, setup_data
from influence.services.submission import SubmissionError, run_submission

# The brief's hidden test supplies 60 amendment-submission pairs.
EXPECTED_PAIRS = 60
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


def _submit(pairs: Path, out: Path, expected_pairs: int) -> int:
    started = perf_counter()
    try:
        run = run_submission(pairs, out, expected_pairs)
    except SubmissionError as error:
        print(f"error: {error.summary}", file=sys.stderr)
        for problem in error.problems:
            print(f"  {problem}", file=sys.stderr)
        print("Nothing was written. Fix the input (or its adapter) and rerun.", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"error: cannot write outputs in {out}: {error}", file=sys.stderr)
        print(f"{out / 'pairs.csv'} was not replaced.", file=sys.stderr)
        return 1
    elapsed = perf_counter() - started
    modes = Counter(item.comparison.mode for item in run.scored)
    print(
        f"Scored {len(run.scored)} pairs in {elapsed:.2f} s "
        f"(comparison modes: edits {modes['edits']}, passages {modes['passages']})"
    )
    print(f"pairs.csv: {run.files.pairs_csv.absolute()}")
    print(f"evidence:  {run.files.evidence.absolute()}")
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
    print(f"explorer: http://localhost:3000/atlas?law={view.slug}")
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


def _list_lineage(result: CollectResult) -> int:
    try:
        view = build_lineage(load_collected(result.bundle), generated_at=datetime.now(UTC))
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="influence", description="Influence Atlas commands that run without the server."
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
    submit = commands.add_parser(
        "submit",
        help="score supplied pairs into pairs.csv",
        description="Score every supplied pair and write pairs.csv with its evidence.",
    )
    submit.add_argument(
        "--pairs",
        type=Path,
        required=True,
        help='JSON Lines file: {"pair_id", "amendment": {"old", "new"}, "submission": {...}}',
    )
    submit.add_argument(
        "--out", type=Path, required=True, help="output directory, created when missing"
    )
    submit.add_argument(
        "--expected-pairs",
        type=_count,
        default=EXPECTED_PAIRS,
        help=f"exact number of pairs the input must hold (default {EXPECTED_PAIRS})",
    )
    args = parser.parse_args(argv)
    if args.command == "setup":
        return _setup(
            cast("Path | None", args.data_root),
            cast("tuple[SetupGroup, ...]", args.only),
            refresh=cast("bool", args.refresh),
        )
    after: dict[str, Callable[[CollectResult], int] | None] = {
        "collect": None,
        "atlas": _build_view,
        "coordinated": _list_coordinated,
        "lineage": _list_lineage,
        "channels": lambda result: _list_channels(
            result,
            CollectInputs.under(
                cast("Path | None", args.data_root) or default_data_root()
            ).hys_index,
        ),
        "directions": _list_directions,
    }
    if args.command in after:
        return _collect(
            " ".join(cast("list[str]", args.query)),
            cast("Path | None", args.data_root),
            refresh=cast("bool", args.refresh),
            attachments=not cast("bool", args.no_attachments),
            then=after[cast("str", args.command)],
        )
    return _submit(
        cast("Path", args.pairs), cast("Path", args.out), cast("int", args.expected_pairs)
    )
