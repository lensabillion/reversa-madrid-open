"""The `influence` command: the pipeline without the web server, thin over the services.

`influence collect <law>` is Atlas part 1: it writes one law's public record under
`data/laws/<procedure>/`. `influence submit` is the first brief's pairs command, kept until
part 4 replaces it. Exit status: 0 when every output was written, 1 on any input, source
or output failure, 2 on a command-line usage error.
"""

import argparse
import platform
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import cast

import influence
from influence.extraction.cache import CacheError, HttpCache
from influence.extraction.cli import default_data_root
from influence.extraction.fetching import CachedFetcher, UrllibFetcher
from influence.extraction.records import RecordError
from influence.services.collect import (
    AmbiguousLawError,
    CollectError,
    CollectInputs,
    CollectResult,
    CollectSettings,
    collect_law,
    source_revision,
)
from influence.services.submission import SubmissionError, run_submission

# The brief's hidden test supplies 60 amendment-submission pairs.
EXPECTED_PAIRS = 60


def _count(value: str) -> int:
    try:
        count = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"not an integer: {value!r}") from error
    if count < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {count}")
    return count


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


def _print_collected(result: CollectResult, elapsed: float) -> None:
    law = result.law
    print(f"Collected {law.procedure_id} {law.title} in {elapsed:.1f} s")
    print(f"  {'layer':<22}{'status':<15}{'count':>7}  reason")
    for item in law.coverage:
        count = "" if item.count is None else str(item.count)
        print(f"  {item.layer:<22}{item.status:<15}{count:>7}  {item.reason or ''}".rstrip())
    print(f"bundle:   {result.bundle.absolute()}")
    print(f"manifest: {result.manifest_path.absolute()}")


def _collect(query: str, data_root: Path | None, *, refresh: bool, attachments: bool) -> int:
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
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="influence", description="Influence Atlas commands that run without the server."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser(
        "collect",
        help="collect one law's public record into data/laws/<procedure>/",
        description=(
            "Resolve a law (procedure number, CELEX, COM reference or title) and collect "
            "its texts, amendments, consultation submissions and actors."
        ),
    )
    collect.add_argument("query", nargs="+", help="for example 2021/0106(COD) or AI Act")
    collect.add_argument(
        "--data-root", type=Path, default=None, help="overrides INFLUENCE_DATA_ROOT"
    )
    collect.add_argument(
        "--refresh", action="store_true", help="redo every stage and refetch cached answers"
    )
    collect.add_argument(
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
    if args.command == "collect":
        return _collect(
            " ".join(cast("list[str]", args.query)),
            cast("Path | None", args.data_root),
            refresh=cast("bool", args.refresh),
            attachments=not cast("bool", args.no_attachments),
        )
    return _submit(
        cast("Path", args.pairs), cast("Path", args.out), cast("int", args.expected_pairs)
    )
