"""Blind-audit files: two readers' sheets and a private key, then the scored result.

`write_sample` draws a seeded sample of one law's links with `audit.draw_sample` and writes,
under `<audit root>/<slug>/<sample id>/`, one CSV sheet per reader and a key. A sheet shows
what a reader needs to judge a link (the ask's quote and source, the amendment's old and
new wording and source, both dates) under an opaque item ID, and nothing the pipeline
concluded: no link ID, score, tier or status, so a reader cannot defer to the model. The
key maps each item to its link and is kept from the readers. `score_sample` reads both
filled sheets and the key and reports precision per stratum and overall with Wilson
intervals, every split verdict counted as incorrect (`audit.summarise`).

Labels live only in these files. Nothing here writes to a law's bundle or its `atlas.json`,
and no threshold is changed: for a sample of unconfirmed links (the proposed re-scope of
plan gate 7) the score proposes a support-score cut and leaves adopting it to a person.
Linear in the number of links, plus one pass over the sample per cut.
"""

import csv
import io
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from influence.extraction.files import write_bytes_atomic
from influence.schemas.atlas import LinkAssessment, LinkTier
from influence.schemas.atlas_view import AtlasView
from influence.schemas.scoring import FrozenModel
from influence.services.audit import Verdict, draw_sample, summarise

type SampledStatus = Literal["published", "unconfirmed"]

READERS = ("a", "b")
KEY_FILE = "key.json"
RESULT_FILE = "audit-result.json"
SUMMARY_FILE = "audit-summary.md"
SHEET_COLUMNS: tuple[str, ...] = (
    "item_id",
    "actor",
    "ask_quote",
    "ask_submitted_at",
    "ask_source_url",
    "amendment_id",
    "amendment_provision",
    "amendment_old_text",
    "amendment_new_text",
    "amendment_tabled_on",
    "amendment_source_url",
    "verdict",
    "note",
)
# A link is correct only when a reader says yes: "unsure" is not support.
ANSWERS: Mapping[str, Verdict] = {"yes": "correct", "no": "incorrect", "unsure": "incorrect"}
# The precision a copied-like link must show: its Wilson 95% lower bound at or above this.
FLOOR = 0.90
CUTS = tuple(round(step / 20, 2) for step in range(1, 20))
PURPOSES: Mapping[SampledStatus, str] = {
    "published": "Precision of the published links (plan gate 7).",
    "unconfirmed": (
        "PROPOSED re-scope of plan gate 7, not adopted: a sample of unconfirmed links, "
        "read to propose a prose support-score threshold. Nothing is applied automatically."
    ),
}


class AuditFileError(Exception):
    """An audit file is missing, unreadable, or does not describe the sample it belongs to."""


class KeyItem(FrozenModel):
    item_id: str
    stratum: str
    link: LinkAssessment


class AuditKey(FrozenModel):
    """Private to whoever runs the audit: which link each opaque item is."""

    schema_version: Literal["audit-key-1"] = "audit-key-1"
    sample_id: str
    procedure_id: str
    slug: str
    run_id: str
    status: SampledStatus
    tier: LinkTier | None
    seed: int
    size: int
    # Links of `status` (and `tier`, when given) the sample was drawn from.
    population: int
    purpose: str
    items: tuple[KeyItem, ...]


class StratumResult(FrozenModel):
    stratum: str
    sampled: int
    agreed_correct: int
    agreed_incorrect: int
    # Counted as incorrect in `precision`.
    disagreements: int
    unlabelled: int
    precision: float | None
    low: float
    high: float


class CutResult(FrozenModel):
    cut: float
    judged: int
    correct: int
    precision: float | None
    low: float


class ThresholdProposal(FrozenModel):
    floor: float
    cuts: tuple[CutResult, ...]
    # The lowest cut whose Wilson lower bound reaches `floor`; None when none does.
    proposed_cut: float | None
    note: str


class AuditResult(FrozenModel):
    schema_version: Literal["audit-result-1"] = "audit-result-1"
    sample_id: str
    procedure_id: str
    run_id: str
    status: SampledStatus
    purpose: str
    overall: StratumResult
    strata: tuple[StratumResult, ...]
    floor: float
    clears_floor: bool
    threshold: ThresholdProposal | None


@dataclass(frozen=True, slots=True)
class SampleFiles:
    key: AuditKey
    directory: Path


def sample_name(status: SampledStatus, tier: LinkTier | None, seed: int, size: int) -> str:
    return "-".join([status, *([tier] if tier else []), f"seed{seed}", f"n{size}"])


def _stratum(link: LinkAssessment) -> str:
    return f"{link.procedure_id} {link.tier or 'no-tier'}"


def _text(value: str | date | datetime | None) -> str:
    return "unknown" if value is None else str(value)


def _csv(rows: Sequence[Mapping[str, str]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=SHEET_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _sheet_rows(view: AtlasView, items: Sequence[KeyItem]) -> list[dict[str, str]]:
    bundle = view.bundle
    asks = {ask.ask_id: ask for ask in bundle.asks}
    amendments = {amendment.amendment_id: amendment for amendment in bundle.amendments}
    urls = {document.document_id: document.url for document in bundle.documents}
    names = {actor.actor_id: actor.name for actor in bundle.actors}
    rows: list[dict[str, str]] = []
    for item in items:
        try:
            ask = asks[item.link.ask_id]
            amendment = amendments[item.link.amendment_id]
        except KeyError as error:
            raise AuditFileError(
                f"The view of {view.slug} lacks record {error} of link {item.link.link_id}"
            ) from error
        rows.append(
            {
                "item_id": item.item_id,
                "actor": names.get(ask.actor_id, ask.actor_id),
                "ask_quote": ask.span.text,
                "ask_submitted_at": _text(ask.submitted_at),
                "ask_source_url": urls.get(ask.document_id, "unknown"),
                "amendment_id": amendment.amendment_id,
                "amendment_provision": _text(amendment.target_provision),
                "amendment_old_text": _text(amendment.old_text),
                "amendment_new_text": amendment.new_text,
                "amendment_tabled_on": _text(amendment.tabled_on),
                "amendment_source_url": urls.get(amendment.document_id, "unknown"),
                "verdict": "",
                "note": "",
            }
        )
    return rows


def write_sample(
    view: AtlasView,
    audit_root: Path,
    *,
    size: int,
    seed: int,
    status: SampledStatus = "published",
    tier: LinkTier | None = None,
) -> SampleFiles:
    """Draw the sample and write `reader-a.csv`, `reader-b.csv` and `key.json`, atomically.

    Refuses a sample directory that already exists, so a rerun cannot overwrite sheets a
    reader has filled. Items are numbered in a seeded shuffle, so neither the number nor
    the order gives away a link's ID or stratum.
    """
    links = [link for link in view.bundle.links if tier is None or link.tier == tier]
    chosen = list(draw_sample(links, size, seed, status))
    if not chosen:
        raise AuditFileError(
            f"The view of {view.slug} (run {view.run_id}) has no {status} links"
            f"{f' of tier {tier}' if tier else ''} to sample"
        )
    directory = audit_root / view.slug / sample_name(status, tier, seed, size)
    if directory.exists():
        raise AuditFileError(
            f"{directory} already exists; its sheets may hold labels. Choose another seed "
            "or move it away"
        )
    # Deliberate: a seeded, reproducible order is the requirement; nothing here is secret.
    random.Random(seed).shuffle(chosen)  # noqa: S311
    items = tuple(
        KeyItem(item_id=f"item-{number:03d}", stratum=_stratum(link), link=link)
        for number, link in enumerate(chosen, start=1)
    )
    key = AuditKey(
        sample_id=directory.name,
        procedure_id=view.procedure_id,
        slug=view.slug,
        run_id=view.run_id,
        status=status,
        tier=tier,
        seed=seed,
        size=size,
        population=sum(link.status == status for link in links),
        purpose=PURPOSES[status],
        items=items,
    )
    sheet = _csv(_sheet_rows(view, items))
    for reader in READERS:
        write_bytes_atomic(directory / f"reader-{reader}.csv", sheet)
    write_bytes_atomic(directory / KEY_FILE, key.model_dump_json(indent=2).encode("utf-8"))
    return SampleFiles(key=key, directory=directory)


def read_key(directory: Path) -> AuditKey:
    path = directory / KEY_FILE
    try:
        return AuditKey.model_validate_json(path.read_bytes())
    except OSError as error:
        raise AuditFileError(f"Cannot read the key {path}: {error}") from error
    except ValidationError as error:
        raise AuditFileError(f"The key {path} is invalid: {error}") from error


def read_sheet(path: Path, item_ids: Sequence[str]) -> dict[str, Verdict]:
    """One reader's verdicts by item ID; a blank verdict is left out (unlabelled).

    The sheet must list exactly the key's items, once each, and every verdict must be
    yes, no, unsure or blank; anything else is an error, never a guess.
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as error:
        raise AuditFileError(f"Cannot read the sheet {path}: {error}") from error
    reader = csv.DictReader(io.StringIO(text, newline=""))
    absent = sorted({"item_id", "verdict"} - set(reader.fieldnames or ()))
    if absent:
        raise AuditFileError(f"The sheet {path} lacks the column(s) {absent}")
    seen: list[str] = []
    verdicts: dict[str, Verdict] = {}
    invalid: list[str] = []
    for row in reader:
        item = (row["item_id"] or "").strip()
        answer = (row["verdict"] or "").strip().lower()
        seen.append(item)
        if answer and answer not in ANSWERS:
            invalid.append(f"{item}: {answer!r}")
        elif answer:
            verdicts[item] = ANSWERS[answer]
    if sorted(seen) != sorted(item_ids):
        raise AuditFileError(
            f"The sheet {path} does not list the sample's items once each: "
            f"unknown {sorted(set(seen) - set(item_ids))}, "
            f"missing {sorted(set(item_ids) - set(seen))}, {len(seen)} rows"
        )
    if invalid:
        raise AuditFileError(
            f"The sheet {path} has verdicts other than yes, no, unsure or blank: {invalid}"
        )
    return verdicts


def _measure(
    name: str, links: Sequence[LinkAssessment], labels: Mapping[str, Mapping[str, Verdict]]
) -> StratumResult:
    report = summarise(links, {link.link_id: labels[link.link_id] for link in links})
    return StratumResult(
        stratum=name,
        sampled=report.sampled,
        agreed_correct=report.correct,
        agreed_incorrect=report.resolved - report.correct,
        disagreements=report.unresolved,
        unlabelled=report.unlabelled,
        precision=report.precision,
        low=report.low,
        high=report.high,
    )


def propose_threshold(
    links: Sequence[LinkAssessment],
    labels: Mapping[str, Mapping[str, Verdict]],
    floor: float = FLOOR,
    cuts: Sequence[float] = CUTS,
) -> ThresholdProposal:
    """Precision of the sampled links at or above each support-score cut, and a proposal.

    The proposal is the lowest cut whose Wilson lower bound reaches `floor`. The sample
    is spread over strata in proportion to their size, so it is close to self-weighting
    and each cut's precision estimates that of every link at or above it. A proposal only:
    adopting it is a person's decision, recorded in the plan. O(cuts x sample).
    """
    rows: list[CutResult] = []
    for cut in cuts:
        measured = _measure(
            f">= {cut}", [link for link in links if link.support_score >= cut], labels
        )
        rows.append(
            CutResult(
                cut=cut,
                judged=measured.agreed_correct + measured.agreed_incorrect + measured.disagreements,
                correct=measured.agreed_correct,
                precision=measured.precision,
                low=measured.low,
            )
        )
    proposed = next((row.cut for row in rows if row.low >= floor), None)
    return ThresholdProposal(
        floor=floor,
        cuts=tuple(rows),
        proposed_cut=proposed,
        note=(
            "PROPOSAL only, never applied automatically: a person decides whether the prose "
            "threshold moves, and the shown graph is rebuilt by the pipeline, not edited."
        ),
    )


def score_sample(directory: Path) -> AuditResult:
    """Both readers' verdicts against the key: precision per stratum and overall."""
    key = read_key(directory)
    item_ids = [item.item_id for item in key.items]
    sheets = [read_sheet(directory / f"reader-{reader}.csv", item_ids) for reader in READERS]
    labels: dict[str, dict[str, Verdict]] = {
        item.link.link_id: {
            reader: sheet[item.item_id]
            for reader, sheet in zip(READERS, sheets, strict=True)
            if item.item_id in sheet
        }
        for item in key.items
    }
    links = [item.link for item in key.items]
    overall = _measure("all", links, labels)
    strata = tuple(
        _measure(name, [item.link for item in key.items if item.stratum == name], labels)
        for name in sorted({item.stratum for item in key.items})
    )
    return AuditResult(
        sample_id=key.sample_id,
        procedure_id=key.procedure_id,
        run_id=key.run_id,
        status=key.status,
        purpose=key.purpose,
        overall=overall,
        strata=strata,
        floor=FLOOR,
        clears_floor=overall.low >= FLOOR,
        threshold=propose_threshold(links, labels) if key.status == "unconfirmed" else None,
    )


def _share(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def render_summary(result: AuditResult) -> str:
    lines = [
        f"# Blind audit {result.sample_id}",
        "",
        f"{result.purpose}",
        "",
        f"Law {result.procedure_id}, run `{result.run_id}`. Precision counts every link the "
        "two readers split on as incorrect; the interval is Wilson's at 95%.",
        "",
        "| Stratum | Sampled | Agreed correct | Agreed incorrect | Split | Unlabelled "
        "| Precision | 95% interval |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        f"| {row.stratum} | {row.sampled} | {row.agreed_correct} | {row.agreed_incorrect} "
        f"| {row.disagreements} | {row.unlabelled} | {_share(row.precision)} "
        f"| {row.low:.3f} to {row.high:.3f} |"
        for row in (*result.strata, result.overall)
    )
    verdict = "reaches" if result.clears_floor else "does not reach"
    lines += ["", f"The overall lower bound {verdict} the floor of {result.floor:.2f}."]
    if result.threshold is not None:
        proposal = result.threshold
        lines += [
            "",
            "## Proposed prose threshold",
            "",
            proposal.note,
            "",
            "| Cut | Judged | Correct | Precision | Lower bound |",
            "| --- | --- | --- | --- | --- |",
        ]
        lines.extend(
            f"| {row.cut:.2f} | {row.judged} | {row.correct} | {_share(row.precision)} "
            f"| {row.low:.3f} |"
            for row in proposal.cuts
        )
        cut = (
            "No cut"
            if proposal.proposed_cut is None
            else f"The lowest cut is {proposal.proposed_cut:.2f}, which"
        )
        lines += ["", f"{cut} reaches a lower bound of {proposal.floor:.2f}."]
    return "\n".join(lines) + "\n"


def write_result(result: AuditResult, directory: Path) -> tuple[Path, Path]:
    """`audit-result.json` and `audit-summary.md` beside the sheets; nothing else."""
    data = directory / RESULT_FILE
    summary = directory / SUMMARY_FILE
    write_bytes_atomic(data, result.model_dump_json(indent=2).encode("utf-8"))
    write_bytes_atomic(summary, render_summary(result).encode("utf-8"))
    return data, summary
