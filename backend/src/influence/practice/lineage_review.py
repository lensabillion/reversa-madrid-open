"""Human review of lineage claims: pick them, export them, read two readers' labels, gate.

The lineage pipeline traces the final law's new wording back to amendments, the MEPs who
tabled them and the documents that said it earlier. Its scores say how strong a claim looks,
not whether it is true, so the pipeline is promoted only when people read a selection of its
claims and call them real. This module is that step, and it only reads: it never writes a
`LineageView`, and labels live in their own file, apart from model output, so they can never
feed back into what the explorer shows (AGENTS.md, "Data and Challenge Rules").

A claim is one adopted phrase (one stretch of the final act) with every amendment that
carries it: "this wording of the law came from these amendments". Claiming per phrase, not
per (amendment, phrase) pair, keeps a phrase that twenty amendments share from filling the
review twenty times.

* `review_rows` draws `n` claims uniformly at random with a seed (a simple random sample
  over distinct phrases), so the precision it estimates is the precision of every claim the
  view makes. The `strongest` claims, by length and similarity, can be added for reading,
  marked as such; they are never pooled into the precision. (`services/audit.draw_sample`
  is the same seeded draw, stratified for part 4's links; it is typed on `LinkAssessment`,
  so this module draws the same way over phrases.)
* `export_rows` writes the selection as JSON Lines (for `summarise`), CSV and Markdown (for a
  person).
* `summarise` counts a claim only when at least two readers agree it is real or not real,
  and reports precision with a Wilson interval over the sampled claims alone; the strongest
  claims are counted apart. Splits and "unclear" are reported and never decided for the
  readers.
* `meets_gate` refuses to pass on too few resolved labels: an empty or tiny review never
  looks like a pass.

"Coalition wording" means a phrase carried by amendments of at least `COALITION_GROUPS` (2)
different known political groups, the rule `origin.coalition_phrase_ids` applies; an author
whose group is unknown counts for no group.

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
from influence.services.origin import coalition_phrase_ids

PHRASE_CHARACTERS = 200
type Selection = Literal["sample", "strongest"]
type Verdict = Literal["real", "not_real", "unclear"]

LEGEND = (
    "Leyenda: cada fila es una afirmacion del pipeline (un tramo de la ley final y las "
    "enmiendas que lo contienen). Lea la frase, la cita en la ley y los documentos de origen, "
    "y etiquete como real / not_real / unclear. 'eligibility' indica si el documento es "
    "anterior a todas las enmiendas (ask_first). Solo las filas 'sample' cuentan para la "
    "precision."
)
COLUMNS = (
    "claim_id",
    "selection",
    "kind",
    "amendment_ids",
    "stages",
    "earliest_tabled_on",
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
    eligibility: str
    is_citation: bool
    kind: MatchKind
    similarity: float | None


class ReviewRow(FrozenModel):
    """One claim of the lineage view, with everything needed to judge it and nothing else."""

    claim_id: str = Field(min_length=1)
    selection: Selection
    kind: MatchKind
    amendment_ids: tuple[str, ...]
    stages: tuple[str, ...]
    earliest_tabled_on: date | None
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
    """Precision of the sampled claims readers agree on; the strongest claims apart."""

    claims: int
    resolved: int
    real: int
    unresolved: int
    unlabelled: int
    precision: float | None
    low: float
    high: float
    by_kind: Mapping[str, tuple[int, int]]
    strongest_real: int = 0
    strongest_resolved: int = 0


@dataclass(frozen=True, slots=True)
class _Claim:
    claim_id: str
    phrase: AdoptedPhrase
    carriers: tuple[AmendmentAdoption, ...]

    @property
    def strength(self) -> tuple[int, float, str]:
        """Sort key, smallest first: verbatim by words, then semantic by similarity."""
        if self.phrase.kind == "verbatim":
            return (0, -float(self.phrase.words), self.claim_id)
        return (1, -(self.phrase.similarity or 0.0), self.claim_id)


def claim_id(phrase_id: str) -> str:
    return f"claim:{phrase_id}"


def _claims(view: LineageView) -> list[_Claim]:
    """One claim per adopted phrase that some amendment carries, ordered by identifier."""
    carriers: dict[str, list[AmendmentAdoption]] = defaultdict(list)
    for adoption in view.adoptions:
        for phrase_id in adoption.phrase_ids:
            carriers[phrase_id].append(adoption)
    return sorted(
        (
            _Claim(claim_id(phrase.phrase_id), phrase, tuple(carriers[phrase.phrase_id]))
            for phrase in view.adopted_phrases
            if carriers[phrase.phrase_id]
        ),
        key=lambda claim: claim.claim_id,
    )


def _origin_row(origin: OriginMatch) -> OriginRow:
    return OriginRow(
        document_id=origin.document_id,
        organisation=origin.organisation,
        published_at=origin.published_at,
        quote=origin.span.text[:PHRASE_CHARACTERS],
        eligibility=origin.eligibility,
        is_citation=origin.is_citation,
        kind=origin.kind,
        similarity=origin.similarity,
    )


def _row(
    claim: _Claim, selection: Selection, view: LineageView, coalitions: frozenset[str]
) -> ReviewRow:
    origins = sorted(
        (origin for origin in view.origins if origin.phrase_id == claim.phrase.phrase_id),
        key=lambda origin: (
            not origin.counts_as_origin,
            str(origin.published_at),
            origin.document_id,
        ),
    )
    span = claim.phrase.final_spans[0]
    adoptions = sorted(claim.carriers, key=lambda adoption: adoption.amendment_id)
    groups = tuple(
        sorted({g for adoption in adoptions for g in adoption.author_groups if g is not None})
    )
    dates = [adoption.tabled_on for adoption in adoptions]
    return ReviewRow(
        claim_id=claim.claim_id,
        selection=selection,
        kind=claim.phrase.kind,
        amendment_ids=tuple(adoption.amendment_id for adoption in adoptions),
        stages=tuple(sorted({adoption.stage for adoption in adoptions})),
        earliest_tabled_on=None if None in dates else min(d for d in dates if d is not None),
        authors=tuple(dict.fromkeys(n for adoption in adoptions for n in adoption.author_names)),
        groups=groups,
        phrase_words=claim.phrase.words,
        similarity=claim.phrase.similarity,
        shared_by_amendments=len(adoptions),
        coalition=claim.phrase.phrase_id in coalitions,
        phrase=claim.phrase.text[:PHRASE_CHARACTERS],
        final_provision=span.record_id,
        final_quote=span.text[:PHRASE_CHARACTERS],
        origins=tuple(_origin_row(origin) for origin in origins),
    )


def review_rows(
    view: LineageView, n: int, seed: int = 0, strongest: int = 0
) -> tuple[ReviewRow, ...]:
    """`n` claims drawn uniformly with `seed`, then up to `strongest` others marked apart.

    The draw is a simple random sample over distinct phrases, so every claim the view makes
    has the same chance and the precision it estimates is unbiased. The strongest claims
    (verbatim by words, then semantic by similarity) not already drawn are appended with
    selection "strongest", for reading only. With fewer than `n` claims, all are sampled.
    """
    if n < 1:
        raise AuditError("A review needs at least one claim")
    if strongest < 0:
        raise AuditError("The strongest claims to add cannot be negative")
    claims = _claims(view)
    # Deliberate: a seeded, reproducible draw is the requirement; nothing here is secret.
    sample = random.Random(seed).sample(claims, min(n, len(claims)))  # noqa: S311
    drawn = {claim.claim_id for claim in sample}
    top = [c for c in sorted(claims, key=lambda c: c.strength) if c.claim_id not in drawn]
    coalitions = coalition_phrase_ids(view.adoptions)
    return tuple(
        [_row(claim, "sample", view, coalitions) for claim in sample]
        + [_row(claim, "strongest", view, coalitions) for claim in top[:strongest]]
    )


def _origins_text(row: ReviewRow) -> str:
    return " | ".join(
        f"{origin.organisation or origin.document_id} "
        f"({origin.published_at.date() if origin.published_at else 'undated'}, "
        f"eligibility={origin.eligibility}, citation={origin.is_citation}): {origin.quote}"
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
                "; ".join(row.amendment_ids),
                "; ".join(row.stages),
                row.earliest_tabled_on or "",
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
            f"- amendments: {', '.join(row.amendment_ids)} ({', '.join(row.stages)}, earliest "
            f"tabled {row.earliest_tabled_on or 'unknown'})",
            f"- authors: {', '.join(row.authors) or 'committee text'}"
            f" | groups: {', '.join(row.groups) or 'none known'}",
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
                f" eligibility={origin.eligibility}, citation={origin.is_citation},"
                f" {origin.kind})",
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
    """Precision among sampled claims at least two readers agree on, with its Wilson interval.

    A claim counts as real or not real only when every reader gave that same verdict and
    there are at least two of them. Any split, or "unclear", is unresolved; fewer than two
    readers is unlabelled. Neither counts toward precision, and both are reported. Claims
    selected as "strongest" are not a random sample, so they are counted apart
    (`strongest_real` of `strongest_resolved`) and never pooled into the precision. A label
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
    real = resolved = unresolved = unlabelled = strongest_real = strongest_resolved = 0
    kinds: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for claim, row in known.items():
        given = verdicts.get(claim, {})
        agreed = set(given.values())
        decided = len(given) >= 2 and agreed in ({"real"}, {"not_real"})
        is_real = agreed == {"real"}
        if row.selection == "strongest":
            strongest_resolved += decided
            strongest_real += decided and is_real
        elif len(given) < 2:
            unlabelled += 1
        elif decided:
            resolved += 1
            real += is_real
            kinds[row.kind][0] += is_real
            kinds[row.kind][1] += 1
        else:
            unresolved += 1
    low, high = wilson_interval(real, resolved)
    return ReviewSummary(
        claims=sum(row.selection == "sample" for row in rows),
        resolved=resolved,
        real=real,
        unresolved=unresolved,
        unlabelled=unlabelled,
        precision=real / resolved if resolved else None,
        low=low,
        high=high,
        by_kind={kind: (counts[0], counts[1]) for kind, counts in sorted(kinds.items())},
        strongest_real=strongest_real,
        strongest_resolved=strongest_resolved,
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
    export.add_argument("--n", type=int, default=30, help="Claims to sample")
    export.add_argument("--seed", type=int, default=0, help="Seed of the sample")
    export.add_argument(
        "--strongest", type=int, default=0, help="Strongest claims to add, never pooled"
    )
    summary = commands.add_parser("summarise", help="Precision of the claims readers agree on")
    summary.add_argument("--rows", type=Path, required=True, help="rows.jsonl from export")
    summary.add_argument("--labels", type=Path, required=True, help="Labels JSON Lines")
    summary.add_argument("--floor", type=float, default=None, help="Gate on the lower bound")
    summary.add_argument("--minimum-resolved", type=int, default=20)
    return parser


def _export(args: argparse.Namespace) -> int:
    view = LineageView.model_validate_json(cast("Path", args.view).read_text(encoding="utf-8"))
    n, seed = cast("int", args.n), cast("int", args.seed)
    rows = review_rows(view, n, seed, cast("int", args.strongest))
    paths = export_rows(rows, seed, cast("Path", args.out))
    print(f"{len(rows)} claims selected (n {n}, seed {seed}) from {view.procedure_id}")
    for path in paths:
        print(f"wrote {path}")
    return 0


def _summarise(args: argparse.Namespace) -> int:
    summary = summarise(read_rows(cast("Path", args.rows)), read_labels(cast("Path", args.labels)))
    precision = "n/a" if summary.precision is None else f"{summary.precision:.3f}"
    print(
        f"{summary.claims} sampled claims: {summary.resolved} resolved, "
        f"{summary.unresolved} unresolved, {summary.unlabelled} unlabelled"
    )
    print(f"precision {precision} (Wilson 95% {summary.low:.3f} to {summary.high:.3f})")
    for kind, (real, total) in summary.by_kind.items():
        print(f"  {kind}: {real} of {total} real")
    print(
        f"strongest claims, not pooled: {summary.strongest_real} of "
        f"{summary.strongest_resolved} resolved real"
    )
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
