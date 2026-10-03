"""Descriptive ask outcomes in observed coverage, independent of the public link graph.

Canonical ask IDs are supplied by extraction; this service does not guess whether two
separately identified requests mean the same thing. Coalition rows overlap: use the
sample totals, never sum actors, for a distinct-ask total.
"""

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from influence.schemas.atlas import (
    Actor,
    Ask,
    LawRecord,
    Layer,
    LayerCoverage,
    Outcome,
    OutcomeResult,
    OutcomeStage,
)

_STAGES: tuple[OutcomeStage, ...] = ("heard", "parliament_position", "final_act")
_REQUIRED: dict[OutcomeStage, tuple[Layer, ...]] = {
    "heard": ("asks", "actors", "committee_amendments", "plenary_amendments"),
    "parliament_position": ("asks", "actors", "parliament_position"),
    "final_act": ("asks", "actors", "final_act"),
}
# Plan section 4, part 7: a row needs this many assessed asks before its rate is compared,
# so "1 of 1" cannot lead. Rows below it are sorted after every row that meets it.
MIN_ASSESSED_ASKS = 3


@dataclass(frozen=True)
class OutcomeCounts:
    """Partial outcomes are assessed but never receive fractional full-win credit."""

    stage: OutcomeStage
    observed_asks: int
    assessed_asks: int
    full: int
    partial: int
    not_observed: int
    unknown: int
    full_win_rate: float | None


@dataclass(frozen=True)
class ActorOutcomeRow:
    """Reproducible counts for one actor and stage; coalition asks overlap actor rows."""

    actor_id: str
    actor_name: str
    counts: OutcomeCounts
    ask_ids: tuple[str, ...]
    joint_ask_ids: tuple[str, ...]
    outcome_ids: tuple[str, ...]
    evidence_record_ids: tuple[str, ...]
    procedure_ids: tuple[str, ...]
    coverage_gaps: tuple[str, ...]
    incomplete: bool


@dataclass(frozen=True)
class ProcedureCoverage:
    """Preserve supplied layer coverage and procedure-year/topic filter provenance."""

    procedure_id: str
    procedure_year: int
    subjects: tuple[str, ...]
    layers: tuple[LayerCoverage, ...]


@dataclass(frozen=True)
class OutcomeAnalysis:
    """Service result, not an alternative pipeline schema or an all-EU estimate."""

    rows: tuple[ActorOutcomeRow, ...]
    totals: tuple[OutcomeCounts, ...]
    ask_ids: tuple[str, ...]
    coverage: tuple[ProcedureCoverage, ...]
    topic: str | None
    procedure_year: int | None
    coverage_gaps: tuple[str, ...]
    incomplete: bool
    scope: str = "Descriptive outcomes within observed coverage; no causal attribution."
    ranking_basis: str = (
        "Raw observed full-win rate; no smoothing or causal score. Rows with fewer than "
        f"{MIN_ASSESSED_ASKS} assessed asks are sorted after the rest."
    )


def _unique[T](records: Sequence[T], key: Callable[[T], str]) -> dict[str, T]:
    indexed: dict[str, T] = {}
    for record in records:
        record_id = key(record)
        if record_id in indexed and indexed[record_id] != record:
            raise ValueError(f"Conflicting records for {record_id}")
        indexed[record_id] = record
    return indexed


def _gaps(law: LawRecord, stage: OutcomeStage) -> tuple[str, ...]:
    coverage = {item.layer: item for item in law.coverage}
    gaps: list[str] = []
    for layer in _REQUIRED[stage]:
        item = coverage.get(layer)
        if item is None:
            gaps.append(f"{law.procedure_id}: {layer} coverage unreported")
        elif item.status not in ("complete", "not_applicable"):
            gaps.append(f"{law.procedure_id}: {layer} {item.status}: {item.reason}")
    return tuple(gaps)


def _counts(
    ask_ids: Sequence[str],
    stage: OutcomeStage,
    results: dict[tuple[str, OutcomeStage], OutcomeResult],
) -> OutcomeCounts:
    counts = Counter(results.get((ask_id, stage), "unknown") for ask_id in ask_ids)
    assessed = len(ask_ids) - counts["unknown"]
    return OutcomeCounts(
        stage=stage,
        observed_asks=len(ask_ids),
        assessed_asks=assessed,
        full=counts["full"],
        partial=counts["partial"],
        not_observed=counts["not_observed"],
        unknown=counts["unknown"],
        full_win_rate=counts["full"] / assessed if assessed else None,
    )


def aggregate_outcomes(
    *,
    laws: Sequence[LawRecord],
    actors: Sequence[Actor],
    asks: Sequence[Ask],
    outcomes: Sequence[Outcome],
    topic: str | None = None,
    year: int | None = None,
    ask_inventory: bool = True,
) -> OutcomeAnalysis:
    """Count every canonical ask once, including unmatched asks and missing outcomes.

    Topic matches a supplied law subject exactly; year is the procedure-reference year,
    not an inferred submission or completion date. Equal classifications from multiple
    amendments count once with all support IDs retained. Conflicting classifications or
    duplicate IDs with different records fail explicitly, including outside the filter.
    Within each stage, rows with at least MIN_ASSESSED_ASKS assessed asks come first; then
    raw full-win rates descend (unknown last), then assessed counts descend, then actor IDs
    break ties. `ask_inventory` compares a complete asks layer's count with the canonical
    asks supplied; turn it off when that layer counts something else (submissions, while
    each passage stands in for an ask), or every law reports a mismatch. Small samples are
    not smoothed or causal scores.

    For one-law runs and cached batches: O(N + J log J + E log E), where N is input
    records, J is actor/ask memberships and E is retained evidence. Three stages are
    fixed; sorting provides input-order-independent results. Memory is O(N + J + E).
    """
    law_index = _unique(laws, lambda law: law.procedure_id)
    actor_index = _unique(actors, lambda actor: actor.actor_id)
    ask_index = _unique(asks, lambda ask: ask.ask_id)
    outcome_index = _unique(outcomes, lambda outcome: outcome.outcome_id)
    memberships: dict[str, set[str]] = {}
    selected_laws = {
        key: law
        for key, law in law_index.items()
        if (topic is None or topic in law.subjects)
        and (year is None or int(law.procedure_id[:4]) == year)
    }
    for ask in ask_index.values():
        if ask.procedure_id not in law_index:
            raise ValueError(f"Ask {ask.ask_id} references unknown law {ask.procedure_id}")
        for actor_id in {ask.actor_id, *ask.joint_actor_ids}:
            if actor_id not in actor_index:
                raise ValueError(f"Ask {ask.ask_id} references unknown actor {actor_id}")
            if ask.procedure_id in selected_laws:
                memberships.setdefault(actor_id, set()).add(ask.ask_id)

    results: dict[tuple[str, OutcomeStage], OutcomeResult] = {}
    support: dict[tuple[str, OutcomeStage], list[Outcome]] = {}
    for outcome in outcome_index.values():
        ask = ask_index.get(outcome.ask_id)
        if ask is None:
            raise ValueError(
                f"Outcome {outcome.outcome_id} references unknown ask {outcome.ask_id}"
            )
        if ask.procedure_id != outcome.procedure_id:
            raise ValueError(f"Outcome {outcome.outcome_id} has a different procedure from its ask")
        key = (outcome.ask_id, outcome.stage)
        if key in results and results[key] != outcome.result:
            raise ValueError(f"Conflicting outcomes for ask {outcome.ask_id} at {outcome.stage}")
        results[key] = outcome.result
        support.setdefault(key, []).append(outcome)

    ask_counts = Counter(ask.procedure_id for ask in ask_index.values())
    inventory_gaps: dict[str, tuple[str, ...]] = {}
    for procedure_id, law in selected_laws.items():
        inventory_gaps[procedure_id] = tuple(
            f"{procedure_id}: ask inventory mismatch: coverage reports {layer.count}, "
            f"supplied {ask_counts[procedure_id]} canonical asks"
            for layer in law.coverage
            if ask_inventory
            and layer.layer == "asks"
            and layer.status == "complete"
            and layer.count is not None
            and layer.count != ask_counts[procedure_id]
        )
    coverage_gaps = {
        (procedure_id, stage): (*_gaps(law, stage), *inventory_gaps[procedure_id])
        for procedure_id, law in selected_laws.items()
        for stage in _STAGES
    }
    rows: list[ActorOutcomeRow] = []
    for actor_id in sorted(memberships):
        ids = tuple(sorted(memberships[actor_id]))
        row_asks = [ask_index[ask_id] for ask_id in ids]
        procedure_ids = tuple(sorted({ask.procedure_id for ask in row_asks}))
        joint_ids = tuple(
            ask.ask_id for ask in row_asks if len({ask.actor_id, *ask.joint_actor_ids}) > 1
        )
        for stage in _STAGES:
            row_outcomes = [
                outcome for ask_id in ids for outcome in support.get((ask_id, stage), ())
            ]
            evidence = {ask.document_id for ask in row_asks}
            evidence.update(ask.span.record_id for ask in row_asks)
            evidence.update(span.record_id for outcome in row_outcomes for span in outcome.spans)
            evidence.update(
                outcome.article_id for outcome in row_outcomes if outcome.article_id is not None
            )
            counts = _counts(ids, stage, results)
            gaps = tuple(gap for law_id in procedure_ids for gap in coverage_gaps[law_id, stage])
            rows.append(
                ActorOutcomeRow(
                    actor_id=actor_id,
                    actor_name=actor_index[actor_id].name,
                    counts=counts,
                    ask_ids=ids,
                    joint_ask_ids=joint_ids,
                    outcome_ids=tuple(sorted(outcome.outcome_id for outcome in row_outcomes)),
                    evidence_record_ids=tuple(sorted(evidence)),
                    procedure_ids=procedure_ids,
                    coverage_gaps=gaps,
                    incomplete=bool(gaps) or counts.unknown > 0,
                )
            )
    rows.sort(
        key=lambda row: (
            _STAGES.index(row.counts.stage),
            row.counts.assessed_asks < MIN_ASSESSED_ASKS,
            row.counts.full_win_rate is None,
            -(row.counts.full_win_rate or 0),
            -row.counts.assessed_asks,
            row.actor_id,
        )
    )
    selected_asks = tuple(
        sorted(ask.ask_id for ask in ask_index.values() if ask.procedure_id in selected_laws)
    )
    totals = tuple(_counts(selected_asks, stage, results) for stage in _STAGES)
    all_gaps = tuple(
        sorted({f"{stage}: {gap}" for (_, stage), gaps in coverage_gaps.items() for gap in gaps})
    )
    return OutcomeAnalysis(
        rows=tuple(rows),
        totals=totals,
        ask_ids=selected_asks,
        coverage=tuple(
            ProcedureCoverage(
                procedure_id=law.procedure_id,
                procedure_year=int(law.procedure_id[:4]),
                subjects=tuple(sorted(law.subjects)),
                layers=tuple(sorted(law.coverage, key=lambda item: item.layer)),
            )
            for _, law in sorted(selected_laws.items())
        ),
        topic=topic,
        procedure_year=year,
        coverage_gaps=all_gaps,
        incomplete=not selected_laws or bool(all_gaps) or any(item.unknown for item in totals),
    )
