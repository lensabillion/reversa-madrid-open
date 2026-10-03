"""Human review of lineage claims: pick them, export them, read two readers' labels, gate.

The lineage pipeline traces the final law's new wording back to amendments, the MEPs who
tabled them and the documents that said it earlier. Its scores say how strong a claim looks,
not whether it is true, so the pipeline is promoted only when people read a selection of its
claims and call them real. This module is that step, and it only reads: it never writes a
`LineageView`, and labels live in their own file, apart from model output, so they can never
feed back into what the explorer shows (AGENTS.md, "Data and Challenge Rules").

* `review_rows` selects claims: the strongest first, then a seeded sample spread over the
  amendment stage, the match kind and the tabling group, so the review is not curated. The
  selection is a pure function of the view, the seed and the group map.
* `export_rows` writes the selection as JSON Lines (for `summarise`), CSV and Markdown (for a
  person).
* `summarise` counts a claim only when at least two readers agree it is real or not real,
  and reports precision with a Wilson interval; splits and "unclear" are reported apart and
  never decided for the readers.
* `meets_gate` refuses to pass on too few resolved labels: an empty or tiny review never
  looks like a pass.

Run from the repository root:

    uv run --directory backend --locked python -m influence.practice.lineage_review \
        export --view data/laws/2021-0106-COD/lineage.json --out review --n 30 --seed 0
    uv run --directory backend --locked python -m influence.practice.lineage_review \
        summarise --rows review/rows.jsonl --labels review/labels.jsonl --floor 0.9

Selection is O(C log C) for C claims; summarising is linear in rows and labels.
"""

import argparse
import csv
import io
import json
import random
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from math import ceil
from pathlib import Path
from typing import Literal, cast

from pydantic import Field, ValidationError

from influence.practice.harness import write_atomically
from influence.schemas.lineage import (
    AdoptedPhrase,
    AmendmentAdoption,
    LineageView,
    MatchKind,
    OriginMatch,
)
from influence.schemas.scoring import FrozenModel
from influence.services.audit import AuditError, wilson_interval

PHRASE_CHARACTERS = 200
type Selection = Literal["strongest", "sample"]
type Verdict = Literal["real", "not_real", "unclear"]

LEGEND = (
    "Leyenda: cada fila es una afirmacion del pipeline (una enmienda cuyo texto llego a la ley "
    "final). Lea la frase, la cita en la ley y los documentos de origen, y etiquete como "
    "real / not_real / unclear. 'precedes' indica si el documento es anterior a la enmienda."
)
COLUMNS = (
    "claim_id",
    "selection",
    "kind",
    "amendment_id",
    "stage",
    "tabled_on",
    "authors",
    "groups",
    "phrase_words",
    "similarity",
    "shared_by_amendments",
    "coalition",
    "phrase",
    "final_provision",
    "final_quote",
    "origins",
)


class OriginRow(FrozenModel):
    """A document that says the claim's wording too, as a reader needs to see it."""

    document_id: str
    organisation: str | None
    published_at: datetime | None
    quote: str
    precedes: bool | None
    is_citation: bool
    kind: MatchKind
    similarity: float | None


class ReviewRow(FrozenModel):
    """One claim of the lineage view, with everything needed to judge it and nothing else."""

    claim_id: str = Field(min_length=1)
    selection: Selection
    kind: MatchKind
    amendment_id: str
    stage: str
    tabled_on: date | None
    authors: tuple[str, ...]
    groups: tuple[str, ...]
    phrase_words: int
    similarity: float | None
    shared_by_amendments: int
    coalition: bool
    phrase: str
    final_provision: str
    final_quote: str
    origins: tuple[OriginRow, ...]


class LabelRecord(FrozenModel):
    """One reader's verdict on one claim. Kept apart from the pipeline's output."""

    claim_id: str = Field(min_length=1)
    reader: str = Field(min_length=1)
    verdict: Verdict
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ReviewSummary:
    """Precision of the claims that readers agree on, with the uncertainty a small review has."""

    claims: int
    resolved: int
    real: int
    unresolved: int
    unlabelled: int
    precision: float | None
    low: float
    high: float
    by_kind: Mapping[str, tuple[int, int]]


@dataclass(frozen=True, slots=True)
class _Claim:
    claim_id: str
    adoption: AmendmentAdoption
    phrase: AdoptedPhrase

    @property
    def strength(self) -> tuple[int, float, str]:
        """Sort key, smallest first: verbatim by words, then semantic by similarity."""
        if self.phrase.kind == "verbatim":
            return (0, -float(self.phrase.words), self.claim_id)
        return (1, -(self.phrase.similarity or 0.0), self.claim_id)


def claim_id(amendment_id: str, phrase_id: str) -> str:
    return f"claim:{amendment_id}:{phrase_id}"


def _claims(view: LineageView) -> list[_Claim]:
    phrases = {phrase.phrase_id: phrase for phrase in view.adopted_phrases}
    return [
        _Claim(claim_id(adoption.amendment_id, phrase_id), adoption, phrases[phrase_id])
        for adoption in view.adoptions
        for phrase_id in adoption.phrase_ids
    ]


def _group_of(claim: _Claim, groups: Mapping[str, str]) -> str:
    if not claim.adoption.author_ids:
        return "committee_text"
    return groups.get(claim.adoption.author_ids[0], "unknown")


def _stratum(claim: _Claim, groups: Mapping[str, str]) -> tuple[str, str, str]:
    return (claim.adoption.stage, claim.phrase.kind, _group_of(claim, groups))


def _pick(
    claims: Sequence[_Claim], count: int, seed: int, groups: Mapping[str, str]
) -> list[_Claim]:
    """Round-robin over the strata (stage, kind, group), shuffled within each by the seed."""
    # Deliberate: a seeded, reproducible draw is the requirement; nothing here is secret.
    rng = random.Random(seed)  # noqa: S311
    strata: dict[tuple[str, str, str], list[_Claim]] = defaultdict(list)
    for claim in sorted(claims, key=lambda item: item.claim_id):
        strata[_stratum(claim, groups)].append(claim)
    for members in strata.values():
        rng.shuffle(members)
    keys = sorted(strata)
    picked: list[_Claim] = []
    while len(picked) < count:
        for key in keys:
            if strata[key] and len(picked) < count:
                picked.append(strata[key].pop())
    return picked


def _origin_row(origin: OriginMatch) -> OriginRow:
    return OriginRow(
        document_id=origin.document_id,
        organisation=origin.organisation,
        published_at=origin.published_at,
        quote=origin.span.text[:PHRASE_CHARACTERS],
        precedes=origin.precedes,
        is_citation=origin.is_citation,
        kind=origin.kind,
        similarity=origin.similarity,
    )


def _row(
    claim: _Claim,
    selection: Selection,
    view: LineageView,
    shared: Mapping[str, int],
    groups: Mapping[str, str],
) -> ReviewRow:
    origins = sorted(
        (
            origin
            for origin in view.origins
            if origin.phrase_id == claim.phrase.phrase_id
            and claim.adoption.amendment_id in origin.amendment_ids
        ),
        key=lambda origin: (
            origin.precedes is not True,
            str(origin.published_at),
            origin.document_id,
        ),
    )
    span = claim.phrase.final_spans[0]
    members = shared[claim.phrase.phrase_id]
    group_names = tuple(
        dict.fromkeys(groups.get(author, "unknown") for author in claim.adoption.author_ids)
    )
    return ReviewRow(
        claim_id=claim.claim_id,
        selection=selection,
        kind=claim.phrase.kind,
        amendment_id=claim.adoption.amendment_id,
        stage=claim.adoption.stage,
        tabled_on=claim.adoption.tabled_on,
        authors=claim.adoption.author_names,
        groups=group_names or ("committee_text",),
        phrase_words=claim.phrase.words,
        similarity=claim.phrase.similarity,
        shared_by_amendments=members,
        coalition=members > 1,
        phrase=claim.phrase.text[:PHRASE_CHARACTERS],
        final_provision=span.record_id,
        final_quote=span.text[:PHRASE_CHARACTERS],
        origins=tuple(_origin_row(origin) for origin in origins),
    )


def review_rows(
    view: LineageView, n: int, seed: int = 0, groups: Mapping[str, str] | None = None
) -> tuple[ReviewRow, ...]:
    """The `n` claims to read: the strongest half, then a seeded stratified sample.

    Verbatim claims rank before semantic ones, by words and by similarity. The rest of the
    selection is drawn evenly from every (stage, kind, group) stratum, so a large group or
    kind cannot fill the review. `groups` maps an actor ID to a political group; a missing
    entry reads as "unknown", and an amendment with no author as "committee_text". With
    fewer than `n` claims, all of them are returned.
    """
    if n < 1:
        raise AuditError("A review needs at least one claim")
    names = groups or {}
    claims = _claims(view)
    shared: dict[str, int] = defaultdict(int)
    for claim in claims:
        shared[claim.phrase.phrase_id] += 1
    ranked = sorted(claims, key=lambda claim: claim.strength)
    top = ranked[: ceil(n / 2)]
    taken = {claim.claim_id for claim in top}
    rest = [claim for claim in claims if claim.claim_id not in taken]
    sample = _pick(rest, min(n - len(top), len(rest)), seed, names)
    return tuple(
        [_row(claim, "strongest", view, shared, names) for claim in top]
        + [_row(claim, "sample", view, shared, names) for claim in sample]
    )


def _origins_text(row: ReviewRow) -> str:
    return " | ".join(
        f"{origin.organisation or origin.document_id} "
        f"({origin.published_at.date() if origin.published_at else 'undated'}, "
        f"precedes={origin.precedes}, citation={origin.is_citation}): {origin.quote}"
        for origin in row.origins
    )


def to_csv(rows: Sequence[ReviewRow]) -> str:
    """CSV with a Spanish legend as a first line starting with '#', then the header."""
    buffer = io.StringIO()
    buffer.write(f"# {LEGEND}\n")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(COLUMNS)
    for row in rows:
        writer.writerow(
            [
                row.claim_id,
                row.selection,
                row.kind,
                row.amendment_id,
                row.stage,
                row.tabled_on or "",
                "; ".join(row.authors),
                "; ".join(row.groups),
                row.phrase_words,
                "" if row.similarity is None else f"{row.similarity:.3f}",
                row.shared_by_amendments,
                row.coalition,
                row.phrase,
                row.final_provision,
                row.final_quote,
                _origins_text(row),
            ]
        )
    return buffer.getvalue()


def to_markdown(rows: Sequence[ReviewRow], seed: int) -> str:
    """One readable block per claim, in the order they should be read."""
    lines = [f"# Lineage review ({len(rows)} claims, seed {seed})", "", f"> {LEGEND}", ""]
    for number, row in enumerate(rows, start=1):
        lines += [
            f"## {number}. {row.claim_id}",
            "",
            f"- selection: {row.selection} | kind: {row.kind} | words: {row.phrase_words}"
            + ("" if row.similarity is None else f" | similarity: {row.similarity:.3f}"),
            f"- amendment: {row.amendment_id} ({row.stage}, tabled {row.tabled_on or 'unknown'})",
            f"- authors: {', '.join(row.authors) or 'committee text'}"
            f" | groups: {', '.join(row.groups)}",
            f"- shared by {row.shared_by_amendments} amendment(s)"
            + (" (coalition wording)" if row.coalition else ""),
            f"- final law: {row.final_provision}",
            f"  > {row.final_quote}",
            f"- phrase: {row.phrase}",
        ]
        if not row.origins:
            lines.append("- origin: none found")
        for origin in row.origins:
            when = origin.published_at.date() if origin.published_at else "undated"
            lines += [
                f"- origin: {origin.organisation or origin.document_id} ({when},"
                f" precedes={origin.precedes}, citation={origin.is_citation}, {origin.kind})",
                f"  > {origin.quote}",
            ]
        lines.append("")
    return "\n".join(lines)


def export_rows(rows: Sequence[ReviewRow], seed: int, out: Path) -> tuple[Path, Path, Path]:
    """Write `rows.jsonl`, `rows.csv` and `rows.md` into `out` (created if absent)."""
    out.mkdir(parents=True, exist_ok=True)
    jsonl = out / "rows.jsonl"
    write_atomically(jsonl, "".join(f"{row.model_dump_json()}\n" for row in rows))
    write_atomically(out / "rows.csv", to_csv(rows))
    write_atomically(out / "rows.md", to_markdown(rows, seed))
    return jsonl, out / "rows.csv", out / "rows.md"


def _lines(path: Path) -> list[str]:
    """Lines split on the line feed alone: `splitlines()` also breaks at U+2028 inside JSON."""
    lines = path.read_text(encoding="utf-8").split("\N{LINE FEED}")
    return [line for line in lines if line.strip()]


def read_rows(path: Path) -> tuple[ReviewRow, ...]:
    try:
        return tuple(ReviewRow.model_validate_json(line) for line in _lines(path))
    except ValidationError as error:
        raise AuditError(f"{path.name} holds an invalid row: {error}") from error


def read_labels(path: Path) -> tuple[LabelRecord, ...]:
    """Validate every record, naming the line of the first failure."""
    labels: list[LabelRecord] = []
    for number, line in enumerate(_lines(path), start=1):
        try:
            labels.append(LabelRecord.model_validate_json(line))
        except ValidationError as error:
            raise AuditError(f"{path.name} line {number} is invalid: {error}") from error
    return tuple(labels)


def summarise(rows: Sequence[ReviewRow], labels: Sequence[LabelRecord]) -> ReviewSummary:
    """Precision among claims at least two readers agree on, with its Wilson interval.

    A claim counts as real or not real only when every reader gave that same verdict and
    there are at least two of them. Any split, or "unclear", is unresolved; fewer than two
    readers is unlabelled. Neither counts toward precision, and both are reported. A label
    for a claim outside `rows`, or two labels from one reader on one claim, is an error.
    """
    known = {row.claim_id: row for row in rows}
    stray = sorted({label.claim_id for label in labels} - known.keys())
    if stray:
        raise AuditError(f"Labels for claims outside the review: {stray}")
    verdicts: dict[str, dict[str, Verdict]] = defaultdict(dict)
    for label in labels:
        if label.reader in verdicts[label.claim_id]:
            raise AuditError(f"{label.reader} labelled {label.claim_id} more than once")
        verdicts[label.claim_id][label.reader] = label.verdict
    real = resolved = unresolved = unlabelled = 0
    kinds: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for claim, row in known.items():
        given = verdicts.get(claim, {})
        agreed = set(given.values())
        if len(given) < 2:
            unlabelled += 1
        elif agreed == {"real"} or agreed == {"not_real"}:
            resolved += 1
            is_real = agreed == {"real"}
            real += is_real
            kinds[row.kind][0] += is_real
            kinds[row.kind][1] += 1
        else:
            unresolved += 1
    low, high = wilson_interval(real, resolved)
    return ReviewSummary(
        claims=len(known),
        resolved=resolved,
        real=real,
        unresolved=unresolved,
        unlabelled=unlabelled,
        precision=real / resolved if resolved else None,
        low=low,
        high=high,
        by_kind={kind: (counts[0], counts[1]) for kind, counts in sorted(kinds.items())},
    )


def meets_gate(summary: ReviewSummary, floor: float, minimum_resolved: int) -> bool:
    """True only when enough claims were resolved and the interval's lower end clears `floor`.

    The lower end of the Wilson interval is used, not the point estimate, so a small review
    cannot pass on luck. `minimum_resolved` must be at least 1: a review with nothing
    resolved never passes.
    """
    if minimum_resolved < 1:
        raise ValueError("minimum_resolved must be at least 1")
    if not 0.0 <= floor <= 1.0:
        raise ValueError("floor must be between 0 and 1")
    return summary.resolved >= minimum_resolved and summary.low >= floor


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m influence.practice.lineage_review",
        description="Select, export and score a human review of lineage claims.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="Select claims and write rows.jsonl/.csv/.md")
    export.add_argument("--view", type=Path, required=True, help="A lineage.json view")
    export.add_argument("--out", type=Path, required=True, help="Directory for the review files")
    export.add_argument("--n", type=int, default=30, help="Claims to review")
    export.add_argument("--seed", type=int, default=0, help="Seed of the sample")
    export.add_argument("--groups", type=Path, default=None, help="JSON {actor_id: group}")
    summary = commands.add_parser("summarise", help="Precision of the claims readers agree on")
    summary.add_argument("--rows", type=Path, required=True, help="rows.jsonl from export")
    summary.add_argument("--labels", type=Path, required=True, help="Labels JSON Lines")
    summary.add_argument("--floor", type=float, default=None, help="Gate on the lower bound")
    summary.add_argument("--minimum-resolved", type=int, default=20)
    return parser


def _export(args: argparse.Namespace) -> int:
    view = LineageView.model_validate_json(cast("Path", args.view).read_text(encoding="utf-8"))
    groups_path = cast("Path | None", args.groups)
    groups = (
        cast("dict[str, str]", json.loads(groups_path.read_text(encoding="utf-8")))
        if groups_path
        else {}
    )
    n, seed = cast("int", args.n), cast("int", args.seed)
    rows = review_rows(view, n, seed, groups)
    paths = export_rows(rows, seed, cast("Path", args.out))
    print(f"{len(rows)} claims selected (n {n}, seed {seed}) from {view.procedure_id}")
    for path in paths:
        print(f"wrote {path}")
    return 0


def _summarise(args: argparse.Namespace) -> int:
    summary = summarise(read_rows(cast("Path", args.rows)), read_labels(cast("Path", args.labels)))
    precision = "n/a" if summary.precision is None else f"{summary.precision:.3f}"
    print(
        f"{summary.claims} claims: {summary.resolved} resolved, {summary.unresolved} unresolved, "
        f"{summary.unlabelled} unlabelled"
    )
    print(f"precision {precision} (Wilson 95% {summary.low:.3f} to {summary.high:.3f})")
    for kind, (real, total) in summary.by_kind.items():
        print(f"  {kind}: {real} of {total} real")
    floor = cast("float | None", args.floor)
    if floor is None:
        return 0
    passed = meets_gate(summary, floor, cast("int", args.minimum_resolved))
    print(
        f"gate (lower bound >= {floor}, at least {args.minimum_resolved} resolved): "
        f"{'PASS' if passed else 'FAIL'}"
    )
    return 0 if passed else 3


def main(argv: Sequence[str] | None = None) -> int:
    """0 on success or a passed gate, 3 for a failed gate, 1 for unusable input."""
    args = _parser().parse_args(argv)
    try:
        return _export(args) if args.command == "export" else _summarise(args)
    except (OSError, ValidationError, AuditError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
