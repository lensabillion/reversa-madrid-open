"""Fit signal weights on training data; choose thresholds on separate development labels.

Neither sigmoid output nor a development-set Wilson interval establishes a calibrated
influence probability. The caller owns group separation and an untouched publication
audit; provenance identifies the samples but cannot prove how the caller selected them.
"""

from collections.abc import Sequence
from math import exp, fsum, isfinite, log, sqrt
from statistics import NormalDist
from typing import Annotated, Self

from pydantic import Field, model_validator

from influence.schemas.scoring import FrozenModel
from influence.services.audit import wilson_interval

Finite = Annotated[float, Field(allow_inf_nan=False)]


class CalibrationError(ValueError):
    """The supplied data or numerical fit cannot support a usable result."""


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + exp(-value))
    small = exp(value)
    return small / (1 + small)


def _standardize(value: float, mean: float, scale: float) -> float:
    if scale == 0:
        return 0.0
    magnitude = max(abs(value), abs(mean), scale)
    denominator = scale / magnitude
    if denominator == 0:
        raise CalibrationError("Feature magnitude exceeds representable standardized range")
    result = (value / magnitude - mean / magnitude) / denominator
    if not isfinite(result):
        raise CalibrationError("Feature magnitude exceeds representable standardized range")
    return result


class FittedCombiner(FrozenModel):
    """Pure-data fit; `.score` uses only these frozen training statistics and weights."""

    feature_names: tuple[str, ...]
    means: tuple[Finite, ...]
    # Zero marks a constant training feature, which contributes nothing even out of sample.
    scales: tuple[Annotated[Finite, Field(ge=0)], ...]
    weights: tuple[Finite, ...]
    intercept: Finite
    l2: Annotated[Finite, Field(gt=0)]
    max_iterations: int = Field(ge=1)
    tolerance: Annotated[Finite, Field(gt=0)]
    iterations: int = Field(ge=1)
    gradient_norm: Annotated[Finite, Field(ge=0)]
    training_id: str = Field(min_length=1)
    training_samples: int = Field(ge=2)
    training_positives: int = Field(ge=1)
    method: str = "standardized-logistic-l2-v1"
    score_type: str = "sigmoid_support"

    @model_validator(mode="after")
    def consistent_fit(self) -> Self:
        size = len(self.feature_names)
        if (
            not size
            or len(set(self.feature_names)) != size
            or any(not name.strip() for name in self.feature_names)
            or any(len(values) != size for values in (self.means, self.scales, self.weights))
        ):
            raise CalibrationError(
                "Feature names and fitted vectors must have equal unique dimensions"
            )
        if self.training_positives >= self.training_samples:
            raise CalibrationError("A fit needs both label classes")
        if self.iterations > self.max_iterations or self.gradient_norm > self.tolerance:
            raise CalibrationError("Fit has not converged within its recorded settings")
        if any(
            scale == 0 and weight != 0
            for scale, weight in zip(self.scales, self.weights, strict=True)
        ):
            raise CalibrationError("Constant features must have zero weight")
        return self

    def score(self, features: Sequence[float]) -> float:
        """O(p) support calculation; input order must match feature_names, never a probability."""
        if len(features) != len(self.feature_names) or any(not isfinite(v) for v in features):
            raise CalibrationError("Expected one finite value per fitted feature")
        terms = tuple(
            weight * _standardize(value, mean, scale)
            for value, mean, scale, weight in zip(
                features, self.means, self.scales, self.weights, strict=True
            )
        )
        try:
            linear = fsum((self.intercept, *terms))
        except (OverflowError, ValueError) as error:
            raise CalibrationError("Combined features exceed representable range") from error
        if not isfinite(linear):
            raise CalibrationError("Combined features exceed representable range")
        return _sigmoid(linear)


def fit_combiner(
    x: Sequence[Sequence[float]],
    y: Sequence[bool],
    feature_names: Sequence[str],
    *,
    training_id: str,
    l2: float = 0.01,
    max_iterations: int = 2_000,
    tolerance: float = 1e-7,
) -> FittedCombiner:
    """Full-batch descent on mean log loss plus l2/2 * ||weights||²; intercept unpenalized.

    Standardization uses x alone. The step is the reciprocal of an upper bound on the
    Hessian norm, so it needs no stochastic schedule. Stop on the infinity norm of the
    regularized gradient, or raise instead of returning a nonconverged model.
    O(I*n*p) time, O(n*p) memory for n rows, p signals and at most I iterations. Intended
    for the few hundred practice pairs and tens of signals, not corpus-scale training.
    """
    size, count = len(feature_names), len(x)
    if (
        not size
        or not count
        or count != len(y)
        or len(set(feature_names)) != size
        or any(not name.strip() for name in feature_names)
        or any(len(row) != size or any(not isfinite(value) for value in row) for row in x)
    ):
        raise CalibrationError(
            "Training rows, labels and unique feature names must match and be finite"
        )
    if any(type(label) is not bool for label in y) or not 0 < sum(y) < count:
        raise CalibrationError("Training labels must be booleans containing both classes")
    if (
        not training_id.strip()
        or not isfinite(l2)
        or l2 <= 0
        or not isfinite(tolerance)
        or tolerance <= 0
        or type(max_iterations) is not int
        or max_iterations < 1
    ):
        raise CalibrationError("Invalid training provenance or optimizer settings")
    means = tuple(
        x[0][j] if all(row[j] == x[0][j] for row in x) else fsum(row[j] / count for row in x)
        for j in range(size)
    )
    scales: list[float] = []
    for j, mean in enumerate(means):
        magnitude = max(abs(row[j]) for row in x)
        variance = (
            fsum((row[j] / magnitude - mean / magnitude) ** 2 / count for row in x)
            if magnitude
            else 0.0
        )
        scales.append(magnitude * sqrt(variance))
    rows = tuple(
        tuple(
            _standardize(v, mean, scale) for v, mean, scale in zip(row, means, scales, strict=True)
        )
        for row in x
    )
    # Trace bounds the spectral norm, and sigmoid'(z) <= 1/4 everywhere.
    curvature = 0.25 * (1 + fsum(v * v / count for row in rows for v in row)) + l2
    step = 1 / curvature
    weights = [0.0] * size
    positives = sum(y)
    intercept = log(positives / (count - positives))
    for iteration in range(1, max_iterations + 1):
        errors = tuple(
            _sigmoid(intercept + fsum(w * v for w, v in zip(weights, row, strict=True))) - label
            for row, label in zip(rows, y, strict=True)
        )
        bias_gradient = fsum(errors) / count
        gradient = tuple(
            fsum(error * row[j] for error, row in zip(errors, rows, strict=True)) / count
            + l2 * weights[j]
            for j in range(size)
        )
        norm = max(abs(bias_gradient), *(abs(value) for value in gradient))
        if norm <= tolerance:
            return FittedCombiner(
                feature_names=tuple(feature_names),
                means=means,
                scales=tuple(scales),
                weights=tuple(weights),
                intercept=intercept,
                l2=l2,
                max_iterations=max_iterations,
                tolerance=tolerance,
                iterations=iteration,
                gradient_norm=norm,
                training_id=training_id,
                training_samples=count,
                training_positives=positives,
            )
        intercept -= step * bias_gradient
        weights = [weight - step * value for weight, value in zip(weights, gradient, strict=True)]
    raise CalibrationError(f"Combiner did not converge in {max_iterations} iterations")


class PrecisionReport(FrozenModel):
    selected: int
    correct: int
    precision: float | None
    lower: float | None
    upper: float | None
    confidence: float


def _precision(correct: int, total: int, confidence: float) -> PrecisionReport:
    if not 0 < confidence < 1:
        raise CalibrationError("Confidence must be strictly between zero and one")
    if total == 0:
        return PrecisionReport(
            selected=0, correct=0, precision=None, lower=None, upper=None, confidence=confidence
        )
    z = -NormalDist().inv_cdf((1 - confidence) / 2)
    observed = correct / total
    lower, upper = wilson_interval(correct, total, z=z)
    return PrecisionReport(
        selected=total,
        correct=correct,
        precision=observed,
        lower=lower,
        upper=upper,
        confidence=confidence,
    )


def _scored_labels(
    scores: Sequence[float], labels: Sequence[bool]
) -> tuple[tuple[float, bool], ...]:
    if (
        len(scores) != len(labels)
        or any(not isfinite(score) or not 0 <= score <= 1 for score in scores)
        or any(type(label) is not bool for label in labels)
    ):
        raise CalibrationError(
            "Scores must be finite support values in [0,1] with matching boolean labels"
        )
    return tuple(zip(scores, labels, strict=True))


class ThresholdSelection(FrozenModel):
    threshold: float | None
    report: PrecisionReport
    development_id: str
    development_samples: int
    minimum_precision: float
    minimum_samples: int
    # Selection reuses development labels, so this is not an unbiased publication audit.
    evidence_role: str = "development_threshold_selection_requires_independent_audit"


def select_threshold(
    scores: Sequence[float],
    labels: Sequence[bool],
    *,
    development_id: str,
    minimum_precision: float,
    minimum_samples: int,
    confidence: float = 0.95,
) -> ThresholdSelection:
    """Pick the lowest qualifying inclusive cutoff; never manufacture one if none qualifies.

    The Wilson lower bound must reach minimum_precision with at least minimum_samples
    selected rows. Evaluate complete tied groups only. O(n log n) time and O(n) memory;
    development labels must be independent of fitting, and a fresh audit must follow.
    """
    rows = sorted(_scored_labels(scores, labels), reverse=True)
    if (
        not development_id.strip()
        or not 0 < minimum_precision <= 1
        or type(minimum_samples) is not int
        or minimum_samples < 1
    ):
        raise CalibrationError(
            "Explicit development provenance and precision/sample requirements are needed"
        )
    selected_report = _precision(0, 0, confidence)
    threshold: float | None = None
    correct = 0
    for index, (score, label) in enumerate(rows):
        correct += label
        count = index + 1
        if count < len(rows) and rows[count][0] == score:
            continue
        report = _precision(correct, count, confidence)
        if (
            count >= minimum_samples
            and report.lower is not None
            and report.lower >= minimum_precision
        ):
            threshold, selected_report = score, report
    return ThresholdSelection(
        threshold=threshold,
        report=selected_report,
        development_id=development_id,
        development_samples=len(rows),
        minimum_precision=minimum_precision,
        minimum_samples=minimum_samples,
    )
