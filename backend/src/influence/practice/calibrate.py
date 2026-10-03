"""Calibrate part 4's publication threshold and compare a small combiner (`rev-zzur`).

Part 4 must publish only links whose precision is high enough to show a jury, so the cut
that separates "copied" and "reworded" links from the rest has to come from data, not from
a guess. This measures two scorers on LobbyPlag's labelled pairs, on the same grouped folds,
simulated tests and seeds as `python -m influence.practice`, so the difference is the
scorer's alone:

* `lexical-delta-v1`: the single lexical score the repository already ships ("before");
* `logistic-combiner-v1`: a logistic regression over five signals ("after"), fitted inside
  each training fold, so no test label reaches it.

The threshold rule is fixed here, before any result is read. Folds with an even index are
development folds and folds with an odd index are held out. On development pairs only,
the proposed threshold for a tier is the smallest value on a 0.01 grid at which at least
`MIN_PAIRS` development pairs score at or above it and the Wilson 95% lower bound of their
precision reaches the tier's floor (`COPIED_FLOOR` 0.90, `REWORDED_FLOOR` 0.80). The held-out
folds then show what that threshold does on pairs it was not chosen on. A threshold is a
proposal: the practice-loop owner freezes it, and nothing here establishes it.

Run from the repository root:

    uv run --directory backend --locked python -m influence.practice.calibrate \
        --data /absolute/path/to/data/lobbyplag --out evaluation/link-calibration.json

The JSON is a pure function of the input files and the options. It records the inputs'
SHA-256 digests and no timing.
"""

import argparse
import hashlib
import json
import math
import sys
from collections.abc import Iterable, Sequence
from math import sqrt
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict

from influence.practice.__main__ import DATA_FILES, PER_CLASS, TOP_K, lexical_scores
from influence.practice.folds import FoldPlan, make_folds
from influence.practice.harness import (
    Scorer,
    ScorerResults,
    SimulationSettings,
    evaluate,
    out_of_fold_scores,
    simulated_tests,
    write_atomically,
)
from influence.practice.labels import (
    LabelledPair,
    PracticeDataError,
    PracticePair,
    build_practice_set,
)
from influence.repositories.lobbyplag import (
    DatasetInvalidError,
    DatasetUnavailableError,
    DemoRepository,
)
from influence.schemas.scoring import ChangeSpan, ScoreRequest, TextChange
from influence.services.scoring import score_pair

type Direction = Literal["stricter", "weaker", "unknown"]

Z_95 = 1.959963984540054
MIN_PAIRS = 20
COPIED_FLOOR = 0.90
REWORDED_FLOOR = 0.80
GRID = tuple(step / 100 for step in range(101))
TABLE_THRESHOLDS = tuple(step / 10 for step in range(1, 10))
FEATURES = (
    "lexical_overlap",
    "short_edit",
    "negation_conflict",
    "direction_agrees",
    "direction_opposes",
)
SHORT_EDIT_WORDS = 3
_STRICTER_WORDS = frozenset({"shall", "must", "required", "least", "minimum"})
_WEAKER_WORDS = frozenset({"may", "can", "optional"})

CAVEATS = (
    "Every candidate was first proposed by LobbyPlag's own lexical matcher, so all pairs are "
    "lexically similar by construction; precision on real submissions can be lower.",
    "Negatives are weak: pairs a volunteer crowd-checked and never marked as a copy (review "
    "finding R1). Most rest on one check, so precision here is against weak negatives.",
    "One law (GDPR) in one year (2013); the 170 largest-group positives are mostly verbatim "
    "copies, so precision for reworded links is unmeasured.",
    "Folds are organization groups with purged training pairs, so a scorer never sees the "
    "organization or texts it is tested on; the development and held-out halves are folds, "
    "and the combiner for a development fold was fitted partly on held-out folds' labels, "
    "so the held-out check is optimistic by that overlap.",
    "A threshold here is a proposal only. The practice-loop owner freezes it before the "
    "blind audit; nothing in this file establishes it.",
)


class Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Counts(Contract):
    """Pairs scoring at or above a threshold, with their precision and its Wilson interval."""

    pairs: int
    positives: int
    precision: float | None
    wilson_low: float
    wilson_high: float


class ThresholdRow(Contract):
    threshold: float
    all_pairs: Counts
    recall: float


class Proposal(Contract):
    tier: Literal["copied", "reworded"]
    floor: float
    min_pairs: int
    threshold: float | None
    development: Counts | None
    held_out: Counts | None


class CalibrationReport(Contract):
    kind: Literal["link-calibration-v1"]
    input_sha256: dict[str, str]
    simulated_tests: SimulationSettings
    grouping: str
    positives: int
    weak_negatives: int
    development_folds: tuple[int, ...]
    held_out_folds: tuple[int, ...]
    rule: str
    features: tuple[str, ...]
    scorers: dict[str, ScorerResults]
    tables: dict[str, tuple[ThresholdRow, ...]]
    proposals: dict[str, tuple[Proposal, ...]]
    combiner_weights_all_pairs: dict[str, float]
    caveats: tuple[str, ...]


def wilson_interval(correct: int, total: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a proportion; (0, 1) when nothing was observed.

    Copied from the audit tooling (PR #33) so this module does not depend on an unmerged
    branch. The endpoints are pinned so the interval always holds the estimate.
    """
    if total <= 0:
        return 0.0, 1.0
    p = correct / total
    scale = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / scale
    half = z * sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / scale
    low = 0.0 if correct == 0 else max(0.0, centre - half)
    high = 1.0 if correct == total else min(1.0, centre + half)
    return low, high


def _direction(spans: Iterable[ChangeSpan]) -> Direction:
    """Stricter or weaker from obligation cue words in the changed text; else unknown."""
    stricter = weaker = 0
    for span in spans:
        inserted = span.operation == "insert"
        for word in span.text.casefold().split():
            word = word.strip(".,;:()'\"")
            if word in _STRICTER_WORDS:
                stricter, weaker = (stricter + 1, weaker) if inserted else (stricter, weaker + 1)
            elif word in _WEAKER_WORDS:
                stricter, weaker = (stricter, weaker + 1) if inserted else (stricter + 1, weaker)
    if stricter == weaker:
        return "unknown"
    return "stricter" if stricter > weaker else "weaker"


def signals(pair: PracticePair) -> tuple[float, ...]:
    """The five features of `FEATURES` for one pair, each in [0, 1]."""
    result = score_pair(
        ScoreRequest(
            amendment=TextChange(old=pair.amendment.old, new=pair.amendment.new),
            submission=TextChange(old=pair.submission.old, new=pair.submission.new),
        )
    )
    mine, theirs = _direction(result.amendment_changes), _direction(result.submission_changes)
    known = mine != "unknown" and theirs != "unknown"
    words = sum(len(span.text.split()) for span in result.amendment_changes)
    return (
        result.score,
        float(words < SHORT_EDIT_WORDS),
        float(result.negation_conflict),
        float(known and mine == theirs),
        float(known and mine != theirs),
    )


def _sigmoid(value: float) -> float:
    return 1 / (1 + math.exp(-max(-30.0, min(30.0, value))))


def _predict(weights: Sequence[float], features: Sequence[float]) -> float:
    return _sigmoid(sum(w * x for w, x in zip(weights, features, strict=False)) + weights[-1])


def fit_logistic(
    rows: Sequence[Sequence[float]],
    labels: Sequence[bool],
    *,
    steps: int = 400,
    rate: float = 0.5,
    l2: float = 0.01,
) -> tuple[float, ...]:
    """Batch gradient descent on log-loss with a small L2 penalty; the last weight is the bias.

    Starts from zero and uses no randomness, so the same rows give the same weights. O(steps
    * n * d). Features are already in [0, 1], so no scaling is needed. The penalty and step
    count are fixed, not tuned on any test label.
    """
    dimension = len(rows[0])
    weights = [0.0] * (dimension + 1)
    for _ in range(steps):
        gradient = [0.0] * (dimension + 1)
        for row, label in zip(rows, labels, strict=True):
            error = _predict(weights, row) - label
            for index, value in enumerate(row):
                gradient[index] += error * value
            gradient[dimension] += error
        count = len(rows)
        for index in range(dimension):
            weights[index] -= rate * (gradient[index] / count + l2 * weights[index])
        weights[dimension] -= rate * gradient[dimension] / count
    return tuple(weights)


def combiner_scores(training: Sequence[LabelledPair], test: Sequence[PracticePair]) -> list[float]:
    """Fit on the training fold's labels, then score the test fold. Test labels never enter."""
    weights = fit_logistic(
        [signals(item.pair) for item in training], [item.influenced for item in training]
    )
    return [_predict(weights, signals(pair)) for pair in test]


def counts(scores: Sequence[float], labels: Sequence[bool], threshold: float) -> Counts:
    kept = [label for score, label in zip(scores, labels, strict=True) if score >= threshold]
    low, high = wilson_interval(sum(kept), len(kept))
    return Counts(
        pairs=len(kept),
        positives=sum(kept),
        precision=round(sum(kept) / len(kept), 4) if kept else None,
        wilson_low=round(low, 4),
        wilson_high=round(high, 4),
    )


def choose_threshold(scores: Sequence[float], labels: Sequence[bool], floor: float) -> float | None:
    """The smallest grid threshold whose development precision clears `floor` (see module)."""
    for threshold in GRID:
        found = counts(scores, labels, threshold)
        if found.pairs >= MIN_PAIRS and found.wilson_low >= floor:
            return threshold
    return None


def _proposal(
    tier: Literal["copied", "reworded"],
    floor: float,
    scores: Sequence[float],
    labels: Sequence[bool],
    development: Sequence[int],
    held_out: Sequence[int],
) -> Proposal:
    def part(indices: Sequence[int]) -> tuple[list[float], list[bool]]:
        return [scores[i] for i in indices], [labels[i] for i in indices]

    threshold = choose_threshold(*part(development), floor)
    if threshold is None:
        return Proposal(
            tier=tier,
            floor=floor,
            min_pairs=MIN_PAIRS,
            threshold=None,
            development=None,
            held_out=None,
        )
    return Proposal(
        tier=tier,
        floor=floor,
        min_pairs=MIN_PAIRS,
        threshold=threshold,
        development=counts(*part(development), threshold),
        held_out=counts(*part(held_out), threshold),
    )


def _table(scores: Sequence[float], labels: Sequence[bool]) -> tuple[ThresholdRow, ...]:
    positives = sum(labels)
    return tuple(
        ThresholdRow(
            threshold=threshold,
            all_pairs=counts(scores, labels, threshold),
            recall=round(
                sum(
                    label and score >= threshold
                    for score, label in zip(scores, labels, strict=True)
                )
                / positives,
                4,
            ),
        )
        for threshold in TABLE_THRESHOLDS
    )


def _folds_of(plan: FoldPlan, parity: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
    numbers = tuple(number for number in range(len(plan.folds)) if number % 2 == parity)
    indices = tuple(index for number in numbers for index in plan.folds[number].test)
    return numbers, indices


def calibrate(
    repository: DemoRepository,
    input_sha256: dict[str, str],
    *,
    seed: int,
    draws: int,
    folds: int,
    recall_threshold: float,
) -> CalibrationReport:
    """Score every pair out of fold with both scorers, then tabulate and propose thresholds."""
    practice = build_practice_set(repository)
    pairs = practice.pairs
    plan = make_folds(pairs, folds)
    tests = simulated_tests([item.influenced for item in pairs], draws, PER_CLASS, seed)
    settings = SimulationSettings(
        draws=draws,
        per_class=PER_CLASS,
        seed=seed,
        generator="Python random.Random (Mersenne Twister)",
        top_k=TOP_K,
        recall_threshold=recall_threshold,
    )
    scorers: dict[str, tuple[str, Scorer]] = {
        "lexical-delta-v1": (
            "The existing lexical score on clean edits: the baseline, 'before'",
            lexical_scores,
        ),
        "logistic-combiner-v1": (
            f"Logistic regression over {', '.join(FEATURES)}, fitted in each training fold",
            combiner_scores,
        ),
    }
    labels = [item.influenced for item in pairs]
    development_folds, development = _folds_of(plan, 0)
    held_out_folds, held_out = _folds_of(plan, 1)
    scores = {
        name: out_of_fold_scores(scorer, pairs, plan) for name, (_, scorer) in scorers.items()
    }
    weights = fit_logistic([signals(item.pair) for item in pairs], labels)
    return CalibrationReport(
        kind="link-calibration-v1",
        input_sha256=input_sha256,
        simulated_tests=settings,
        grouping=plan.grouping,
        positives=sum(labels),
        weak_negatives=len(labels) - sum(labels),
        development_folds=development_folds,
        held_out_folds=held_out_folds,
        rule=(
            f"Development folds are the even-numbered ones. On development pairs only, the "
            f"threshold is the smallest 0.01-grid value with at least {MIN_PAIRS} pairs at or "
            f"above it and a Wilson 95% lower bound of precision of at least the tier's floor "
            f"(copied {COPIED_FLOOR}, reworded {REWORDED_FLOOR}). Held-out folds then check it."
        ),
        features=FEATURES,
        scorers={
            name: evaluate(description, scores[name], pairs, plan, tests, settings)
            for name, (description, _) in scorers.items()
        },
        tables={name: _table(values, labels) for name, values in scores.items()},
        proposals={
            name: (
                _proposal("copied", COPIED_FLOOR, values, labels, development, held_out),
                _proposal("reworded", REWORDED_FLOOR, values, labels, development, held_out),
            )
            for name, values in scores.items()
        },
        combiner_weights_all_pairs={
            **{name: round(weight, 4) for name, weight in zip(FEATURES, weights, strict=False)},
            "bias": round(weights[-1], 4),
        },
        caveats=CAVEATS,
    )


def render(report: CalibrationReport) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def _sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m influence.practice.calibrate",
        description="Calibrate the link publication threshold and compare a combiner.",
    )
    parser.add_argument("--data", type=Path, required=True, help="LobbyPlag snapshot directory")
    parser.add_argument("--out", type=Path, required=True, help="Results JSON to (re)write")
    parser.add_argument("--seed", type=int, default=0, help="Seed of the simulated tests")
    parser.add_argument("--draws", type=int, default=2000, help="Number of simulated tests")
    parser.add_argument("--folds", type=int, default=5, help="Number of grouped folds")
    parser.add_argument("--recall-threshold", type=float, default=0.5, help="Recall cut (D5)")
    return parser


def _print(report: CalibrationReport) -> None:
    print(
        f"{report.positives} positives, {report.weak_negatives} weak negatives; {report.grouping}"
    )
    print(f"{'scorer':<24}{'P@20':>8}{'recall':>8}{'AUC':>8}{'full AUC':>10}")
    for name, result in report.scorers.items():
        draw = result.draws
        print(
            f"{name:<24}{draw.precision_at_top.mean:>8.3f}{draw.recall.mean:>8.3f}"
            f"{draw.auc.mean:>8.3f}{result.full_set_auc:>10.3f}"
        )
    for name, tiers in report.proposals.items():
        for tier in tiers:
            held = tier.held_out
            text = "no threshold reaches the floor"
            if tier.threshold is not None and held is not None:
                text = f"{tier.threshold:.2f}; held out {held.positives}/{held.pairs}"
            print(f"{name} {tier.tier} (floor {tier.floor}): {text}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    data, out = cast("Path", args.data), cast("Path", args.out)
    seed, draws, folds = cast("int", args.seed), cast("int", args.draws), cast("int", args.folds)
    recall_threshold = cast("float", args.recall_threshold)
    if draws < 1 or folds < 2 or not 0 <= recall_threshold <= 1:
        parser.error("need --draws >= 1, --folds >= 2 and 0 <= --recall-threshold <= 1")
    if not out.parent.is_dir():
        parser.error(f"output directory does not exist: {out.parent}")
    try:
        repository = DemoRepository.load(data)
        hashes = {f"{name}.json": _sha256(data / f"{name}.json") for name in DATA_FILES}
        report = calibrate(
            repository,
            hashes,
            seed=seed,
            draws=draws,
            folds=folds,
            recall_threshold=recall_threshold,
        )
    except (OSError, DatasetUnavailableError, DatasetInvalidError, PracticeDataError) as error:
        cause = f" ({error.__cause__})" if error.__cause__ else ""
        print(f"error: {error}{cause}", file=sys.stderr)
        return 1
    write_atomically(out, render(report))
    _print(report)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
