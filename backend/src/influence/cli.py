"""The `influence` command: the 19:00 run without the web server, thin over the services.

`influence submit` covers architecture parts 1-4 and writes `pairs.csv`. Plan step 4
(`rev-e5xh`) adds `--proposals` to the same subcommand for `proposals.csv`.
Exit status: 0 when every output was written, 1 on any input or output failure,
2 on a command-line usage error.
"""

import argparse
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from time import perf_counter
from typing import cast

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
    args = parser.parse_args(argv)
    return _submit(
        cast("Path", args.pairs), cast("Path", args.out), cast("int", args.expected_pairs)
    )
