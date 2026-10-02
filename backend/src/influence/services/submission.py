"""Architecture parts 1-4 as one batch run: supplied pairs in, validated `pairs.csv` out.

Part 1 reads our JSON Lines contract (the organizers' format is open decision D5, so an
adapter converts it at 19:00). Parts 2-3 are the existing `compare_texts` service. Part 4
passes that score through until a trained combiner exists. Every score is written beside
the signals that produced it (`pairs.evidence.jsonl`), and nothing here imports the web
server, the demo or the graph. A missing or invalid required input stops the run.
"""

import csv
import io
import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from pydantic import ValidationError

from influence.schemas.submission import PairEvidence, SubmissionPair
from influence.services.comparison import compare_texts

PAIRS_CSV = "pairs.csv"
EVIDENCE_JSONL = "pairs.evidence.jsonl"
CSV_HEADER = ("pair_id", "influence_score")


class SubmissionError(Exception):
    """Every problem found in one pass, so a single fix-and-rerun cycle clears them all."""

    def __init__(self, summary: str, problems: Sequence[str]) -> None:
        super().__init__(summary)
        self.summary = summary
        self.problems = tuple(problems)


@dataclass(frozen=True)
class SubmissionFiles:
    pairs_csv: Path
    evidence: Path


@dataclass(frozen=True)
class SubmissionRun:
    files: SubmissionFiles
    scored: tuple[PairEvidence, ...]


def _raw_pair_id(record: object) -> str | None:
    """The identifier as written, so problems on an invalid line still name its pair."""
    match record:
        case {"pair_id": str() as pair_id}:
            return pair_id
        case _:
            return None


def parse_pairs(data: bytes, expected_pairs: int) -> tuple[SubmissionPair, ...]:
    """Validate every line before any scoring, and report every problem at once.

    Lines split on `\\n` only: a JSON string may legally contain U+2028 and other
    characters that `str.splitlines` treats as line breaks. A leading UTF-8 byte-order
    mark is accepted because common editors add one. Texts are never truncated: the
    scorer's limits from `SubmissionPair` reject oversized input. O(input size).
    """
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        line = data.count(b"\n", 0, error.start) + 1
        raise SubmissionError(
            "The pairs file is not UTF-8", [f"line {line}: {error.reason}"]
        ) from error
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    problems: list[str] = []
    pairs: list[SubmissionPair] = []
    first_seen: dict[str, int] = {}
    records = 0
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            problems.append(f"line {number}: blank; each line must hold one JSON object")
            continue
        records += 1
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            problems.append(f"line {number}: invalid JSON: {error.msg} at column {error.colno}")
            continue
        raw_id = _raw_pair_id(record)
        label = f"line {number}" if raw_id is None else f"line {number} (pair_id {raw_id!r})"
        first = number if raw_id is None else first_seen.setdefault(raw_id, number)
        if first != number:
            problems.append(f"{label}: duplicate pair_id, first on line {first}")
        try:
            pair = SubmissionPair.model_validate(record)
        except ValidationError as error:
            problems.extend(
                f"{label}: {'.'.join(map(str, detail['loc'])) or 'record'}: {detail['msg']}"
                for detail in error.errors(include_url=False, include_input=False)
            )
            continue
        pairs.append(pair)
    if records == 0:
        problems.append("the file holds no pairs; expected one JSON object per line")
    elif records != expected_pairs:
        problems.append(f"expected {expected_pairs} pairs (--expected-pairs), found {records}")
    if problems:
        raise SubmissionError(f"Invalid pairs input: {len(problems)} problem(s)", problems)
    return tuple(pairs)


def read_pairs(path: Path, expected_pairs: int) -> tuple[SubmissionPair, ...]:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise SubmissionError("Cannot read the pairs file", [str(error)]) from error
    return parse_pairs(data, expected_pairs)


def score_pairs(pairs: Sequence[SubmissionPair]) -> tuple[PairEvidence, ...]:
    """Score in input order. Part 4 passes the comparison score through unchanged.

    The pass-through ends when a combiner is trained and calibrated on held-out practice
    evidence (`rev-zzur`). Each comparison is bounded by the scorer's 800-token limit,
    so the run is linear in the number of pairs.
    """
    scored: list[PairEvidence] = []
    for pair in pairs:
        comparison = compare_texts(pair)
        scored.append(
            PairEvidence(
                pair_id=pair.pair_id, influence_score=comparison.score, comparison=comparison
            )
        )
    return tuple(scored)


def check_scores(
    expected_ids: Sequence[str], scored: Sequence[PairEvidence], expected_pairs: int
) -> None:
    """The last gate before any file is written; it also guards a future combiner."""
    problems: list[str] = []
    actual_ids = [item.pair_id for item in scored]
    if len(actual_ids) != expected_pairs:
        problems.append(f"expected {expected_pairs} scores, got {len(actual_ids)}")
    if actual_ids != list(expected_ids):
        problems.append("scored pair_ids differ from the input pair_ids or their order")
    if len(set(actual_ids)) != len(actual_ids):
        problems.append("scored pair_ids are not unique")
    problems.extend(
        f"pair_id {item.pair_id!r}: influence_score {item.influence_score!r} "
        "is not a finite number in [0, 1]"
        for item in scored
        # NaN fails every comparison, and infinities fail the bounds.
        if not 0.0 <= item.influence_score <= 1.0
    )
    if problems:
        raise SubmissionError("Scores failed validation; nothing was written", problems)


def format_score(score: float) -> str:
    """The shortest decimal that parses back to the identical float, never in exponent form.

    `repr` gives the shortest round-tripping digits, so tied scores stay tied and distinct
    scores stay distinct in the ranking; `Decimal` renders `1e-05` as `0.00001`.
    """
    return format(Decimal(repr(score)), "f")


def render_pairs_csv(scored: Sequence[PairEvidence]) -> bytes:
    """UTF-8 without a byte-order mark, `\\n` line endings, quoting only when needed."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    writer.writerows((item.pair_id, format_score(item.influence_score)) for item in scored)
    return buffer.getvalue().encode()


def render_evidence(scored: Sequence[PairEvidence]) -> bytes:
    return "".join(item.model_dump_json() + "\n" for item in scored).encode()


def write_files_atomically(files: Sequence[tuple[Path, bytes]]) -> None:
    """Stage every file beside its target, then rename them in the given order.

    A failure while staging leaves every target untouched and removes the staged copies.
    Each rename is atomic within one filesystem; the sequence is not, so the file whose
    presence signals completion goes last. Content is fsynced before its rename, so a
    file that survives a power loss under its final name also has its complete content.
    """
    staged: list[Path] = []
    try:
        for target, content in files:
            descriptor, name = tempfile.mkstemp(
                dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
            )
            staged.append(Path(name))
            # mkstemp creates owner-only files; give outputs a plain write's permissions.
            os.fchmod(descriptor, 0o644)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        for (target, _), path in zip(files, staged, strict=True):
            path.replace(target)
    except BaseException:
        for path in staged:
            path.unlink(missing_ok=True)
        raise


def write_submission(out_dir: Path, scored: Sequence[PairEvidence]) -> SubmissionFiles:
    """Write the evidence first and `pairs.csv` last: a `pairs.csv` means a complete run."""
    out_dir.mkdir(parents=True, exist_ok=True)
    files = SubmissionFiles(pairs_csv=out_dir / PAIRS_CSV, evidence=out_dir / EVIDENCE_JSONL)
    write_files_atomically(
        (
            (files.evidence, render_evidence(scored)),
            (files.pairs_csv, render_pairs_csv(scored)),
        )
    )
    return files


def run_submission(pairs_path: Path, out_dir: Path, expected_pairs: int) -> SubmissionRun:
    """Read, score, validate, then write; any failure before writing leaves no file."""
    pairs = read_pairs(pairs_path, expected_pairs)
    scored = score_pairs(pairs)
    check_scores([pair.pair_id for pair in pairs], scored, expected_pairs)
    return SubmissionRun(files=write_submission(out_dir, scored), scored=scored)
