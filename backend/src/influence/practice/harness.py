"""Score every labelled pair out of fold, then measure it on simulated hidden tests.

A scorer is one callable: given a fold's training pairs (with labels) and its test pairs
(without), it returns one score in [0, 1] per test pair. An unsupervised scorer ignores the
training pairs; part 4's trained combiner will fit on them, including any preprocessing
such as phrase rarity, so nothing it learns comes from the test fold. Test labels cannot
reach a scorer: the test pairs' type has no label field.

AGENTS.md: model changes are accepted on evaluation evidence, reported before and after on
the same folds and seeds. The folds are a deterministic function of the data, and the
draws of the seed, so two runs on the same snapshot measure every scorer on identical tests.
"""

import json
import math
import random
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from os import getpid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from influence.practice.folds import FoldPlan, Grouping
from influence.practice.labels import (
    LabelledPair,
    LabelSource,
    PracticeDataError,
    PracticePair,
    PracticeSet,
)
from influence.practice.metrics import Summary, auc, precision_at_k, recall_at, summarize

type Scorer = Callable[[Sequence[LabelledPair], Sequence[PracticePair]], Sequence[float]]


class ScorerContractError(Exception):
    """A scorer returned the wrong number of scores, or a score outside [0, 1]."""


@dataclass(frozen=True, slots=True)
class Draw:
    """One simulated hidden test: indices of the real pairs, then of the decoys."""

    members: tuple[int, ...]
    tie_order: tuple[int, ...]


def simulated_tests(
    influenced: Sequence[bool], count: int, per_class: int, seed: int
) -> tuple[Draw, ...]:
    """Draw `count` tests of `per_class` real pairs and `per_class` decoys, without replacement.

    Every scorer is measured on the same draws and tie orders, so a comparison is paired
    (R4): a difference between scorers is never a difference in luck. The draws reuse the
    same few hundred pairs, so they are not independent tests of new data. O(count * per_class).
    """
    real = [index for index, label in enumerate(influenced) if label]
    decoys = [index for index, label in enumerate(influenced) if not label]
    if min(len(real), len(decoys)) < per_class:
        raise PracticeDataError(
            f"Each test needs {per_class} real pairs and {per_class} decoys; "
            f"the labelled data has {len(real)} and {len(decoys)}"
        )
    # Deliberate: a seeded, reproducible generator is the requirement; nothing is secret.
    rng = random.Random(seed)  # noqa: S311
    size = 2 * per_class
    return tuple(
        Draw(
            members=(*rng.sample(real, per_class), *rng.sample(decoys, per_class)),
            tie_order=tuple(rng.sample(range(size), size)),
        )
        for _ in range(count)
    )


def out_of_fold_scores(
    scorer: Scorer, pairs: Sequence[LabelledPair], plan: FoldPlan
) -> tuple[float, ...]:
    """Score each pair once, in the fold where it is tested."""
    scores: dict[int, float] = {}
    for fold in plan.folds:
        test = [pairs[index].pair for index in fold.test]
        result = scorer([pairs[index] for index in fold.train], test)
        if len(result) != len(test):
            raise ScorerContractError(f"Expected {len(test)} scores, got {len(result)}")
        for index, score in zip(fold.test, result, strict=True):
            if not (math.isfinite(score) and 0 <= score <= 1):
                candidate = pairs[index].pair.candidate_id
                raise ScorerContractError(f"Score {score!r} for {candidate} is outside [0, 1]")
            scores[index] = score
    return tuple(scores[index] for index in range(len(pairs)))


class Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class MetricSummary(Contract):
    mean: float
    p10: float


class DrawResults(Contract):
    precision_at_top: MetricSummary
    recall: MetricSummary
    auc: MetricSummary


class FoldMetrics(Contract):
    """`None` where a fold lacks the class the metric needs."""

    fold: int
    auc: float | None
    recall: float | None


class ScorerResults(Contract):
    description: str
    full_set_auc: float
    full_set_recall: float
    draws: DrawResults
    folds: tuple[FoldMetrics, ...]


class LabelReport(Contract):
    candidates: int
    duplicate_candidate_rows: int
    merged_crowd_tallies: int
    outcomes: dict[str, int]
    excluded: dict[str, int]
    identical_input_groups: int
    pairs_in_identical_input_groups: int
    conflicting_identical_input_groups: int
    positives: int
    weak_negatives: int
    weak_negative_crowd_checks: dict[str, int]
    document_languages: dict[str, int]
    rules: dict[str, str]


class ComponentReport(Contract):
    positives: int
    negatives: int
    organizations: int
    amendments: int


class FoldReport(Contract):
    fold: int
    organizations: tuple[str, ...]
    positives: int
    negatives: int
    training_pairs: int
    purged_training_pairs: int


class FoldsReport(Contract):
    k: int
    grouping: Grouping
    components: tuple[ComponentReport, ...]
    folds: tuple[FoldReport, ...]


class SimulationSettings(Contract):
    draws: int = Field(ge=1)
    per_class: int = Field(ge=1)
    seed: int
    generator: Literal["Python random.Random (Mersenne Twister)"]
    top_k: int = Field(ge=1)
    recall_threshold: float = Field(ge=0, le=1)


class PairRow(Contract):
    candidate_id: str
    amendment_id: str
    proposal_id: str
    organization_id: str
    label_source: LabelSource
    crowd_checks: int
    crowd_yes_votes: int
    document_language: str
    fold: int
    scores: dict[str, float]


class PracticeResults(Contract):
    kind: Literal["practice-harness-results-v1"]
    input_sha256: dict[str, str]
    labels: LabelReport
    folds: FoldsReport
    simulated_tests: SimulationSettings
    scorers: dict[str, ScorerResults]
    pairs: tuple[PairRow, ...]


LABEL_RULES = {
    "positive": "plags.json verified is true: a volunteer verified the copy",
    "weak_negative": (
        "verified is false, processing.checked > 0 and processing.verified == 0: crowd-checked "
        "and never voted a copy; weaker than a positive (review finding R1)"
    ),
    "unlabelled": "every other candidate; excluded, never treated as a negative (R2)",
}


def _summary(summary: Summary) -> MetricSummary:
    return MetricSummary(mean=round(summary.mean, 4), p10=round(summary.p10, 4))


def evaluate(
    description: str,
    scores: Sequence[float],
    pairs: Sequence[LabelledPair],
    plan: FoldPlan,
    draws: Sequence[Draw],
    settings: SimulationSettings,
) -> ScorerResults:
    """O(D m log m) for D draws of m pairs, plus O(n log n) for the full set and folds."""
    influenced = [item.influenced for item in pairs]
    per_draw: list[tuple[float, float, float]] = []
    for draw in draws:
        drawn = [scores[index] for index in draw.members]
        labels = [influenced[index] for index in draw.members]
        per_draw.append(
            (
                precision_at_k(drawn, labels, settings.top_k, draw.tie_order),
                recall_at(drawn, labels, settings.recall_threshold),
                auc(drawn, labels),
            )
        )
    folds: list[FoldMetrics] = []
    for number, fold in enumerate(plan.folds):
        fold_scores = [scores[index] for index in fold.test]
        labels = [influenced[index] for index in fold.test]
        real = sum(labels)
        folds.append(
            FoldMetrics(
                fold=number,
                auc=round(auc(fold_scores, labels), 4) if 0 < real < len(labels) else None,
                recall=(
                    round(recall_at(fold_scores, labels, settings.recall_threshold), 4)
                    if real
                    else None
                ),
            )
        )
    return ScorerResults(
        description=description,
        full_set_auc=round(auc(scores, influenced), 4),
        full_set_recall=round(recall_at(scores, influenced, settings.recall_threshold), 4),
        draws=DrawResults(
            precision_at_top=_summary(summarize([row[0] for row in per_draw])),
            recall=_summary(summarize([row[1] for row in per_draw])),
            auc=_summary(summarize([row[2] for row in per_draw])),
        ),
        folds=tuple(folds),
    )


def label_report(
    practice: PracticeSet, candidates: int, duplicate_rows: int, merged_tallies: int
) -> LabelReport:
    positives = [item for item in practice.pairs if item.influenced]
    negatives = [item for item in practice.pairs if not item.influenced]
    checks = Counter(str(item.crowd_checks) for item in negatives)
    languages = Counter(item.document_language for item in practice.pairs)
    return LabelReport(
        candidates=candidates,
        duplicate_candidate_rows=duplicate_rows,
        merged_crowd_tallies=merged_tallies,
        outcomes=dict(practice.outcomes),
        excluded=dict(practice.excluded),
        identical_input_groups=practice.identical_inputs.groups,
        pairs_in_identical_input_groups=practice.identical_inputs.pairs,
        conflicting_identical_input_groups=practice.identical_inputs.conflicting_groups,
        positives=len(positives),
        weak_negatives=len(negatives),
        weak_negative_crowd_checks=dict(sorted(checks.items())),
        document_languages=dict(sorted(languages.items())),
        rules=LABEL_RULES,
    )


def folds_report(plan: FoldPlan, pairs: Sequence[LabelledPair]) -> FoldsReport:
    return FoldsReport(
        k=len(plan.folds),
        grouping=plan.grouping,
        components=tuple(
            ComponentReport(
                positives=size.positives,
                negatives=size.negatives,
                organizations=size.organizations,
                amendments=size.amendments,
            )
            for size in plan.components
        ),
        folds=tuple(
            FoldReport(
                fold=number,
                organizations=tuple(sorted({pairs[i].pair.organization_id for i in fold.test})),
                positives=sum(pairs[i].influenced for i in fold.test),
                negatives=sum(not pairs[i].influenced for i in fold.test),
                training_pairs=len(fold.train),
                purged_training_pairs=len(fold.purged),
            )
            for number, fold in enumerate(plan.folds)
        ),
    )


def pair_rows(
    pairs: Sequence[LabelledPair], plan: FoldPlan, scores: dict[str, tuple[float, ...]]
) -> tuple[PairRow, ...]:
    fold_of = {index: number for number, fold in enumerate(plan.folds) for index in fold.test}
    return tuple(
        PairRow(
            candidate_id=item.pair.candidate_id,
            amendment_id=item.pair.amendment_id,
            proposal_id=item.pair.proposal_id,
            organization_id=item.pair.organization_id,
            label_source=item.source,
            crowd_checks=item.crowd_checks,
            crowd_yes_votes=item.crowd_yes_votes,
            document_language=item.document_language,
            fold=fold_of[index],
            scores={name: values[index] for name, values in scores.items()},
        )
        for index, item in enumerate(pairs)
    )


def render(results: PracticeResults) -> str:
    """Indented JSON, except one line per pair, so the per-pair table reads well in a diff."""
    head = json.dumps(results.model_dump(mode="json", exclude={"pairs"}), indent=2, sort_keys=True)
    rows = ",\n".join(
        "    " + json.dumps(row.model_dump(mode="json"), sort_keys=True) for row in results.pairs
    )
    return head.removesuffix("\n}") + ',\n  "pairs": [\n' + rows + "\n  ]\n}\n"


def write_atomically(path: Path, text: str) -> None:
    """Readers see the old file or the complete new one, never a partial write."""
    staged = path.with_name(f".{path.name}.{getpid()}.tmp")
    try:
        staged.write_text(text, encoding="utf-8")
        staged.replace(path)
    finally:
        staged.unlink(missing_ok=True)
