"""Part 7, forecast: will an open ask appear in a later stage of the law? A cautious baseline.

A forecast is built only from what was known at its as-of cutoff. Every feature carries the
date it was observed, and `check_no_leakage` rejects any that is later than the cutoff, or
any training example whose outcome was decided on or after it. The model is a smoothed rate
per (topic, has an amendment) group, shrunk toward the overall rate, and it is compared with
a prevalence baseline (the overall rate for everyone) on rolling time splits: train on what
was decided before a cutoff, test on the next block, never with a procedure on both sides.
A number is published only when that validation shows the model beating prevalence on enough
splits; otherwise the forecast is a reasoned scenario with no score, because an unvalidated
probability would pass for a calibrated one. Linear in the examples per split.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from statistics import fmean

from influence.practice.metrics import auc
from influence.schemas.atlas import Forecast, id_part

MODEL_REVISION = "group-rates-1"
SHRINKAGE = 2.0
MIN_TESTED_SPLITS = 3
MIN_TEST_EXAMPLES = 100
# Placeholder: a model that is only slightly better than prevalence has not shown skill that
# survives a new law, so a number needs a clear margin. Calibration evidence should replace it.
MIN_BRIER_GAIN = 0.05
EVENT = "The requested wording appears in the next stage of the law"

type Group = tuple[str | None, bool]


class LeakageError(Exception):
    """Something observed after the cutoff reached a forecast or its training data."""


@dataclass(frozen=True, slots=True)
class Features:
    """What was known about one ask, and when. `missing` names inputs we could not get."""

    topic: str | None
    amendment_count: int
    observed_at: datetime
    missing: tuple[str, ...] = ()

    @property
    def group(self) -> Group:
        return self.topic, self.amendment_count > 0


@dataclass(frozen=True, slots=True)
class Example:
    """A past ask whose outcome is known: `decided_at` is when that outcome was settled.

    Its features must have been observed before the outcome was decided, or the example
    would teach (or test) the model with what the outcome itself revealed. Every example,
    training or test, is checked when it is made.
    """

    procedure_id: str
    features: Features
    decided_at: datetime
    won: bool

    def __post_init__(self) -> None:
        if self.features.observed_at >= self.decided_at:
            raise ValueError(
                f"Features observed {self.features.observed_at} are not before the outcome "
                f"decided {self.decided_at}"
            )


@dataclass(frozen=True, slots=True)
class Split:
    as_of: datetime
    train: tuple[int, ...]
    test: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Validation:
    """How the model did against prevalence on rolling splits, and whether that is enough."""

    splits: int
    tested_splits: int
    test_examples: int
    model_auc: float | None
    baseline_auc: float | None
    model_brier: float | None
    baseline_brier: float | None
    adequate: bool
    reasons: tuple[str, ...]


def check_no_leakage(as_of: datetime, features: Features, history: Sequence[Example] = ()) -> None:
    """Raise unless every input was observed, and every outcome decided, before `as_of`."""
    if features.observed_at > as_of:
        raise LeakageError(f"Features observed {features.observed_at} are after the cutoff {as_of}")
    late = [
        item for item in history if item.decided_at >= as_of or item.features.observed_at > as_of
    ]
    if late:
        raise LeakageError(f"{len(late)} training examples are not known before the cutoff {as_of}")


@dataclass(frozen=True, slots=True)
class RateModel:
    """Win rate per (topic, has an amendment) group, shrunk toward the overall rate."""

    prevalence: float
    rates: dict[Group, tuple[int, int]]
    trained: int

    def predict(self, features: Features) -> float:
        wins, total = self.rates.get(features.group, (0, 0))
        return (wins + SHRINKAGE * self.prevalence) / (total + SHRINKAGE)


def fit(as_of: datetime, examples: Sequence[Example]) -> RateModel:
    """Fit on examples decided before `as_of`. Raises LeakageError on any that were not."""
    check_no_leakage(as_of, Features(None, 0, as_of), examples)
    counts: dict[Group, list[int]] = defaultdict(lambda: [0, 0])
    for item in examples:
        counts[item.features.group][0] += item.won
        counts[item.features.group][1] += 1
    wins = sum(item.won for item in examples)
    return RateModel(
        prevalence=wins / len(examples) if examples else 0.0,
        rates={group: (won, total) for group, (won, total) in counts.items()},
        trained=len(examples),
    )


def rolling_splits(examples: Sequence[Example], blocks: int) -> tuple[Split, ...]:
    """Expanding-window splits: block i is tested on a model trained only on earlier outcomes.

    Examples are ordered by decision date and cut into `blocks` + 1 equal blocks; block 0 only
    ever trains. A training example is dropped when its procedure also appears in the test
    block, so one law never sits on both sides. O(n log n).
    """
    if blocks < 1:
        raise ValueError("Need at least one test block")
    order = sorted(range(len(examples)), key=lambda index: examples[index].decided_at)
    size = len(order) // (blocks + 1)
    splits: list[Split] = []
    for block in range(1, blocks + 1):
        start = block * size
        end = len(order) if block == blocks else start + size
        test = tuple(order[start:end])
        if not test:
            continue
        cutoff = min(examples[index].decided_at for index in test)
        procedures = {examples[index].procedure_id for index in test}
        train = tuple(
            index
            for index in order[:start]
            if examples[index].decided_at < cutoff
            and examples[index].procedure_id not in procedures
        )
        splits.append(Split(as_of=cutoff, train=train, test=test))
    return tuple(splits)


def validate(examples: Sequence[Example], blocks: int = 4) -> Validation:
    """Compare the model with prevalence on rolling splits and decide if a number is earned.

    A split is tested only when its test block holds both outcomes and it has training data.
    The model must beat prevalence on Brier score and rank better than chance (AUC > 0.5)
    over at least MIN_TESTED_SPLITS splits and MIN_TEST_EXAMPLES tested examples.
    """
    splits = rolling_splits(examples, blocks)
    model_auc: list[float] = []
    baseline_auc: list[float] = []
    model_errors: list[float] = []
    baseline_errors: list[float] = []
    tested = 0
    for split in splits:
        labels = [examples[index].won for index in split.test]
        if not split.train or all(labels) or not any(labels):
            continue
        model = fit(split.as_of, [examples[index] for index in split.train])
        scores = [model.predict(examples[index].features) for index in split.test]
        tested += 1
        model_auc.append(auc(scores, labels))
        baseline_auc.append(auc([model.prevalence] * len(labels), labels))
        model_errors.extend((s - label) ** 2 for s, label in zip(scores, labels, strict=True))
        baseline_errors.extend((model.prevalence - label) ** 2 for label in labels)
    model_brier = fmean(model_errors) if model_errors else None
    baseline_brier = fmean(baseline_errors) if baseline_errors else None
    model_mean_auc = fmean(model_auc) if model_auc else None
    reasons: list[str] = []
    if tested < MIN_TESTED_SPLITS:
        reasons.append(f"Only {tested} rolling splits could be tested; {MIN_TESTED_SPLITS} needed.")
    if len(model_errors) < MIN_TEST_EXAMPLES:
        reasons.append(
            f"Only {len(model_errors)} test examples; {MIN_TEST_EXAMPLES} needed for a probability."
        )
    if (
        model_brier is not None
        and baseline_brier is not None
        and model_brier > baseline_brier * (1 - MIN_BRIER_GAIN)
    ):
        reasons.append(
            "The model's Brier score does not beat the prevalence baseline "
            f"by {MIN_BRIER_GAIN:.0%}."
        )
    if model_mean_auc is not None and model_mean_auc <= 0.5:
        reasons.append("The model does not rank better than chance.")
    return Validation(
        splits=len(splits),
        tested_splits=tested,
        test_examples=len(model_errors),
        model_auc=model_mean_auc,
        baseline_auc=fmean(baseline_auc) if baseline_auc else None,
        model_brier=model_brier,
        baseline_brier=baseline_brier,
        adequate=not reasons,
        reasons=tuple(reasons),
    )


def forecast_ask(
    *,
    ask_id: str,
    procedure_id: str,
    as_of: datetime,
    features: Features,
    history: Sequence[Example],
    validation: Validation,
    horizon: str | None = None,
) -> Forecast:
    """One forecast for an open ask, from pre-cutoff inputs only.

    A probability when `validation` earned one; otherwise a scenario with no score. Either
    way it carries its reasons and the inputs that were missing. Raises LeakageError if any
    feature or training example is not known before `as_of`.
    """
    check_no_leakage(as_of, features, history)
    model = fit(as_of, history)
    supported = features.amendment_count > 0
    reasons = [
        f"{features.amendment_count} amendment(s) carry the ask."
        if supported
        else "No amendment carries the ask yet."
    ]
    missing = [*features.missing, *([] if history else ["historical_outcomes"])]
    forecast_id = f"forecast:{id_part(ask_id)}"
    if validation.adequate:
        reasons.append(
            f"Estimated from {model.trained} past asks decided before the cutoff, shrunk toward "
            f"the overall rate of {model.prevalence:.2f}."
        )
        return Forecast(
            forecast_id=forecast_id,
            procedure_id=procedure_id,
            ask_id=ask_id,
            as_of=as_of,
            event=EVENT,
            horizon=horizon,
            score_type="probability",
            score=model.predict(features),
            reasons=tuple(reasons),
            missing_features=tuple(missing),
            model_revision=MODEL_REVISION,
        )
    reasons.extend(validation.reasons or ("No validation was run.",))
    scenario = (
        "Plausible only if the amendment carrying the ask is adopted unchanged"
        if supported
        else "Unlikely unless an amendment carrying the ask is tabled"
    )
    return Forecast(
        forecast_id=forecast_id,
        procedure_id=procedure_id,
        ask_id=ask_id,
        as_of=as_of,
        event=EVENT,
        horizon=horizon,
        score_type="scenario",
        scenario=scenario,
        reasons=tuple(reasons),
        missing_features=tuple(missing),
        model_revision=MODEL_REVISION,
    )
