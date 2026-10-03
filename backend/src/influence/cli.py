"""The `influence` command: the 19:00 run without the web server, thin over the services.

`influence submit` covers architecture parts 1-4 and writes `pairs.csv`. Plan step 4
(`rev-e5xh`) adds `--proposals` to the same subcommand for `proposals.csv`.
`influence collect` turns a law's name, procedure number, CELEX or COM number into that
law's normalised public record under the data root, with a run manifest.
Exit status: 0 when every output was written, 1 on any input or output failure,
2 on a command-line usage error.
"""

import argparse
import logging
import os
import platform
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from typing import cast

from influence.extraction.cache import HttpCache
from influence.extraction.fetching import CachedFetcher
from influence.services.collect import COLLECT_REVISION, CollectError, collect_law
from influence.services.submission import SubmissionError, run_submission

# The brief's hidden test supplies 60 amendment-submission pairs.
EXPECTED_PAIRS = 60
# The repository's git-ignored `data/` directory: this file is backend/src/influence/cli.py.
DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[3] / "data"


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


def _progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _collect(
    query: str, data_root: Path, attachment_limit: int | None, code_revision: str | None
) -> int:
    # pypdf warns about every odd font in every attachment; none of it changes the result.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    started = perf_counter()
    try:
        result = collect_law(
            query,
            data_root=data_root,
            fetcher=CachedFetcher(HttpCache(data_root / "cache")),
            clock=lambda: datetime.now(UTC),
            code_revision=code_revision or f"influence-{version('influence')}+{COLLECT_REVISION}",
            attachment_limit=attachment_limit,
            hardware=f"{platform.system()} {platform.machine()}, {os.cpu_count()} logical CPUs",
            progress=_progress,
        )
    except CollectError as error:
        print(f"error: {error}", file=sys.stderr)
        for choice in error.choices:
            print(f"  {choice}", file=sys.stderr)
        print("No manifest was published.", file=sys.stderr)
        return 1
    elapsed = perf_counter() - started
    law = result.law
    print(f"{law.procedure_id}  {law.title}  ({law.status})")
    print(
        f"proposal {law.celex_proposal or 'unknown'}, final act {law.celex_final or 'unknown'}, "
        f"{law.com_reference or 'no COM reference'}"
    )
    print("Coverage:")
    for row in law.coverage:
        count = "-" if row.count is None else str(row.count)
        print(f"  {row.layer:<22}{row.status:<16}{count:>7}  {row.reason or ''}".rstrip())
    print("Stages:")
    for stage in result.manifest.stages:
        counts = ", ".join(f"{name} {value}" for name, value in stage.counts.items())
        print(f"  {stage.stage:<12}{stage.status:<10}{stage.seconds:>8.2f} s  {counts}".rstrip())
        for problem in stage.errors:
            print(f"    error: {problem}")
    print(f"Collected in {elapsed:.2f} s")
    print(f"manifest: {result.manifest_path.absolute()}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="influence", description="Influence Graph batch commands for the 19:00 run."
    )
    commands = parser.add_subparsers(dest="command", required=True)
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
    collect = commands.add_parser(
        "collect",
        help="collect one law's public record",
        description=(
            "Resolve a law by name, procedure number, CELEX or COM number and write its "
            "texts, amendments, consultation feedback and actors with a run manifest."
        ),
    )
    collect.add_argument(
        "query",
        nargs="+",
        help='the law: "AI Act", "2021/0106(COD)", "32024R1689" or "COM(2021) 206"',
    )
    collect.add_argument(
        "--data-root",
        type=Path,
        default=DEFAULT_DATA_ROOT,
        help="directory holding raw/, catalog/, cache/ and laws/ (default: the repository's data/)",
    )
    collect.add_argument(
        "--attachment-limit",
        type=_count,
        default=None,
        help="read only the first N consultation attachments, for a fast first run (default: all)",
    )
    collect.add_argument(
        "--code-revision",
        default=None,
        help="revision recorded in the manifest and hashed into every stage (default: the "
        "package version and the collect revision)",
    )
    args = parser.parse_args(argv)
    if args.command == "collect":
        return _collect(
            " ".join(cast("list[str]", args.query)),
            cast("Path", args.data_root),
            cast("int | None", args.attachment_limit),
            cast("str | None", args.code_revision),
        )
    return _submit(
        cast("Path", args.pairs), cast("Path", args.out), cast("int", args.expected_pairs)
    )
