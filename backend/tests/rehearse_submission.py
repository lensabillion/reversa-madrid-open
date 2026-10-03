"""Rehearse the 19:00 command end to end on 60 public LobbyPlag pairs, against a timer.

Run with `uv run --directory backend --locked python tests/rehearse_submission.py DATA_DIR`.
Thirty historically verified and thirty unverified English candidate links are drawn with
a fixed seed. The verified flag only balances the sample; it never reaches the command.
This rehearses plumbing and time (input contract, console script, validation, atomic
outputs), not accuracy: LobbyPlag proposals are short extracts, not whole lobby papers.
The record names the exact inputs by hash; times describe this machine and run only.
"""

import argparse
import csv
import hashlib
import io
import json
import os
import platform
import random
import re
import statistics
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import cast

from pydantic import ValidationError

from influence.repositories.lobbyplag import DemoRepository
from influence.schemas.comparison import ComparisonRequest
from influence.schemas.submission import PairEvidence
from influence.services.submission import (
    CSV_HEADER,
    EVIDENCE_JSONL,
    PAIRS_CSV,
    write_files_atomically,
)

DATA_FILES = ("amendments", "proposals", "plags", "documents", "lobbyists")
SEED = 20261003
PER_GROUP = 30
RUNS = 3
BACKEND = Path(__file__).resolve().parents[1]
# The interpreter's own directory holds the console scripts of this environment.
INFLUENCE = Path(sys.executable).parent / "influence"
ELAPSED = re.compile(r"^Scored \d+ pairs in (\d+\.\d+) s ", re.MULTILINE)

type Record = dict[str, object]


def file_hash(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def select_pairs(repository: DemoRepository) -> tuple[list[tuple[str, Record]], Record]:
    """Seeded sample of eligible candidates; O(C log C) for C candidate links."""
    eligible: dict[bool, list[tuple[str, Record]]] = {True: [], False: []}
    excluded: Counter[str] = Counter()
    for candidate in sorted(repository.candidates.values(), key=lambda item: item.uid):
        amendment = repository.amendments[candidate.amendment]
        proposal = repository.proposals[candidate.proposal]
        document = repository.documents[proposal.doc_uid]
        english = next((text for text in amendment.text if text.lang == "en"), None)
        if english is None or document.lang != "en" or proposal.text.lang != "en":
            excluded["not_english"] += 1
            continue
        record: Record = {
            "amendment": {"old": english.old, "new": english.new},
            "submission": {"old": proposal.text.old, "new": proposal.text.new},
        }
        try:
            ComparisonRequest.model_validate(record)
        except ValidationError:
            excluded["outside_scorer_limits"] += 1
            continue
        eligible[candidate.verified].append((candidate.uid, record))
    # Deliberate exception, not debt: a seeded, reproducible sample, not a secret.
    generator = random.Random(SEED)  # noqa: S311
    chosen = generator.sample(eligible[True], PER_GROUP) + generator.sample(
        eligible[False], PER_GROUP
    )
    generator.shuffle(chosen)
    selection: Record = {
        "seed": SEED,
        "verified_sampled": PER_GROUP,
        "unverified_sampled": PER_GROUP,
        "eligible_verified": len(eligible[True]),
        "eligible_unverified": len(eligible[False]),
        "excluded_not_english": excluded["not_english"],
        "excluded_outside_scorer_limits": excluded["outside_scorer_limits"],
    }
    return chosen, selection


def validate_outputs(out_dir: Path, pair_ids: list[str]) -> tuple[list[float], list[str]]:
    """Check the files on disk independently of the command's own validation."""
    leftovers = sorted(path.name for path in out_dir.iterdir())
    if leftovers != [PAIRS_CSV, EVIDENCE_JSONL]:
        raise RuntimeError(f"Unexpected files in the output directory: {leftovers}")
    header, *rows = csv.reader(
        io.StringIO((out_dir / PAIRS_CSV).read_text(encoding="utf-8"), newline="")
    )
    if tuple(header) != CSV_HEADER or [row[0] for row in rows] != pair_ids:
        raise RuntimeError("pairs.csv header or pair_ids differ from the input")
    scores = [float(row[1]) for row in rows]
    if not all(0.0 <= score <= 1.0 for score in scores):
        raise RuntimeError("pairs.csv holds a score outside [0, 1]")
    lines = (out_dir / EVIDENCE_JSONL).read_text(encoding="utf-8").removesuffix("\n").split("\n")
    evidence = [PairEvidence.model_validate_json(line) for line in lines]
    if [(item.pair_id, item.influence_score) for item in evidence] != list(
        zip(pair_ids, scores, strict=True)
    ):
        raise RuntimeError("Evidence pair_ids or scores differ from pairs.csv")
    return scores, [item.comparison.mode for item in evidence]


def cpu_name() -> str:
    if platform.system() != "Darwin":
        return platform.processor()
    # Deliberate exception, not debt: a fixed system binary with fixed arguments.
    return subprocess.run(
        ["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def rehearse(directory: Path) -> Record:
    hashes = {f"{name}.json": file_hash(directory / f"{name}.json") for name in DATA_FILES}
    build_started = perf_counter()
    chosen, selection = select_pairs(DemoRepository.load(directory))
    pair_ids = [f"R{index:02d}" for index in range(1, len(chosen) + 1)]
    lines = [
        json.dumps({"pair_id": pair_id, **record}, ensure_ascii=False)
        for pair_id, (_, record) in zip(pair_ids, chosen, strict=True)
    ]
    build_seconds = perf_counter() - build_started

    with tempfile.TemporaryDirectory() as temporary:
        pairs_path = Path(temporary) / "pairs.jsonl"
        pairs_path.write_text("\n".join(lines) + "\n")
        out_dir = Path(temporary) / "out"
        command = [
            str(INFLUENCE),
            "submit",
            "--pairs",
            str(pairs_path),
            "--out",
            str(out_dir),
            "--expected-pairs",
            str(len(pair_ids)),
        ]
        wall: list[float] = []
        inside: list[float] = []
        digests: set[str] = set()
        scores: list[float] = []
        modes: list[str] = []
        for _ in range(RUNS):
            started = perf_counter()
            # Deliberate exception, not debt: this environment's own console script, with
            # arguments built in this file.
            result = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
            wall.append(round(perf_counter() - started, 6))
            if result.returncode != 0:
                raise RuntimeError(f"influence submit exited {result.returncode}: {result.stderr}")
            reported = ELAPSED.search(result.stdout)
            if reported is None:
                raise RuntimeError(f"Unexpected command output: {result.stdout}")
            inside.append(float(reported.group(1)))
            scores, modes = validate_outputs(out_dir, pair_ids)
            digests.add(file_hash(out_dir / PAIRS_CSV))
        input_hash = file_hash(pairs_path)
        sizes = {name: (out_dir / name).stat().st_size for name in (PAIRS_CSV, EVIDENCE_JSONL)}

    return {
        "purpose": "Plumbing and timing rehearsal of `influence submit`; not an accuracy result",
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "input_sha256": {**hashes, "pairs.jsonl": input_hash},
        "selection": selection,
        "candidates_in_pair_order": [uid for uid, _ in chosen],
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "cpu": cpu_name(),
            "cpu_count": os.cpu_count(),
            "python": platform.python_version(),
        },
        "command": "influence submit --pairs <tmp>/pairs.jsonl --out <tmp>/out --expected-pairs 60",
        "seconds": {
            "build_input_from_lobbyplag": round(build_seconds, 6),
            "command_wall_per_run": wall,
            "command_reported_per_run": inside,
        },
        "outputs": {
            "pairs": len(scores),
            "identical_pairs_csv_across_runs": len(digests) == 1,
            "pairs_csv_sha256": sorted(digests),
            "bytes": sizes,
            "comparison_modes": dict(sorted(Counter(modes).items())),
            "zero_scores": sum(score == 0.0 for score in scores),
            "score_min": min(scores),
            "score_median": statistics.median(scores),
            "score_max": max(scores),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "data_dir", type=Path, help="Directory containing five LobbyPlag JSON files"
    )
    parser.add_argument(
        "--record",
        type=Path,
        default=BACKEND / "validation" / f"submission-rehearsal-{datetime.now(UTC).date()}.json",
        help="where to write the result JSON (default: backend/validation/)",
    )
    args = parser.parse_args()
    result = json.dumps(rehearse(cast("Path", args.data_dir)), indent=2, sort_keys=True) + "\n"
    write_files_atomically([(cast("Path", args.record), result.encode())])
    print(result, end="")


if __name__ == "__main__":
    main()
