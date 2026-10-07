"""Setup, collect and lineage commands that regenerate the explorer's saved public data."""

import argparse
import logging
import os
import platform
import ssl
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import cast

from pydantic import SecretStr

import influence
from influence.extraction.cache import CacheError, HttpCache
from influence.extraction.fetching import CachedFetcher, UrllibFetcher
from influence.extraction.layout import default_data_root
from influence.extraction.records import RecordError
from influence.repositories.parltrack import ParltrackError
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
from influence.services.collected import PipelineError, load_collected
from influence.services.jev import JevClient, JevError
from influence.services.jev_judge import JevJudge
from influence.services.lineage_assembly import build_lineage, write_lineage
from influence.services.setup import GROUPS, SetupError, SetupFile, SetupGroup, setup_data

JEV_KEY_VARIABLE = "TYPESAFE_API_KEY"
CREDITS_SHOWN = 10
CRAWL_REPORT_EVERY = 250


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
        for credit in [c for c in view.credits if c.holder_kind == "mep"][:CREDITS_SHOWN]:
            print(
                f"  {credit.name}: {credit.amendments} of {credit.amendments_tabled} amendments "
                f"adopted, {credit.phrases} phrase(s) ({credit.joint_phrases} joint)"
            )
    print(f"lineage: {path.absolute()}")
    print(f"explorer: http://localhost:3000/lineage?law={view.slug}")
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
        prog="influence", description="Collect public law records and trace their lineage."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser(
        "setup", help="download global public inputs and build the Have Your Say index"
    )
    setup.add_argument("--data-root", type=Path, default=None, help="overrides INFLUENCE_DATA_ROOT")
    setup.add_argument("--refresh", action="store_true", help="fetch every chosen file again")
    setup.add_argument(
        "--only",
        type=_groups,
        default=GROUPS,
        metavar="GROUPS",
        help=f"comma-separated subset of {','.join(GROUPS)} (default: all)",
    )
    for name, summary in (
        ("collect", "collect one law's public record"),
        ("lineage", "collect one law, then trace its adopted and tabled wording"),
    ):
        command = commands.add_parser(name, help=summary)
        command.add_argument(
            "query", nargs="+", help="procedure number, CELEX, COM reference, common name or title"
        )
        command.add_argument("--data-root", type=Path, default=None)
        command.add_argument("--refresh", action="store_true")
        command.add_argument("--no-attachments", action="store_true")
        if name == "lineage":
            command.add_argument(
                "--jev",
                action="store_true",
                help=f"judge reworded origins; key in {JEV_KEY_VARIABLE}",
            )
            command.add_argument("--jev-max-usd", type=float, default=1.0)
    args = parser.parse_args(argv)
    if args.command == "setup":
        return _setup(
            cast("Path | None", args.data_root),
            cast("tuple[SetupGroup, ...]", args.only),
            refresh=cast("bool", args.refresh),
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
    return _collect(
        " ".join(cast("list[str]", args.query)),
        cast("Path | None", args.data_root),
        refresh=cast("bool", args.refresh),
        attachments=not cast("bool", args.no_attachments),
        then=(lambda result: _list_lineage(result, judge)) if args.command == "lineage" else None,
    )
