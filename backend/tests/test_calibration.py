"""Fitted signals and sample-qualified thresholds, never invented publication probabilities."""

from collections.abc import Sequence
from math import inf, nan
from typing import cast

import pytest
from pydantic import ValidationError

from influence.services.calibration import (
    CalibrationError,
    FittedCombiner,
    fit_combiner,
    precision_report,
    select_threshold,
)

X = ((-3.0, 7.0), (-2.0, 7.0), (-1.0, 7.0), (1.0, 7.0), (2.0, 7.0), (3.0, 7.0))
Y = (False, False, False, True, True, True)
NAMES = ("same_direction", "constant")


@pytest.fixture
def fitted() -> FittedCombiner:
    return fit_combiner(X, Y, NAMES, training_id="training:group-fold-1")


def test_fit_learns_order_and_uses_frozen_training_statistics(fitted: FittedCombiner) -> None:
    scores = [fitted.score(row) for row in X]
    assert scores == sorted(scores)
    assert scores[2] < 0.5 < scores[3]
    assert fitted.means == (0.0, 7.0)
    assert fitted.weights[1] == fitted.scales[1] == 0
    assert fitted.score((2.0, -999.0)) == fitted.score((2.0, 7.0))
    assert fitted.gradient_norm <= fitted.tolerance
    before = fitted.model_dump_json()
    assert fitted.score((20.0, 7.0)) > scores[-1]
    assert fitted.model_dump_json() == before
    assert fit_combiner(X, Y, NAMES, training_id="training:group-fold-1") == fitted


def test_fit_round_trips_and_is_immutable(fitted: FittedCombiner) -> None:
    restored = FittedCombiner.model_validate_json(fitted.model_dump_json())
    assert restored.score((1.4, 7.0)) == fitted.score((1.4, 7.0))
    assert restored.training_id == "training:group-fold-1"
    assert restored.score_type == "sigmoid_support"
    with pytest.raises(ValidationError, match="frozen"):
        restored.intercept = 0


def test_constant_and_zero_features_fit_only_the_class_prior() -> None:
    model = fit_combiner(((0.0, 0.1),) * 4, (True, False, False, False), NAMES, training_id="prior")
    assert model.iterations == 1
    assert model.weights == (0, 0)
    assert model.score((1e308, -1e308)) == pytest.approx(0.25)


def test_standardization_is_invariant_to_units_and_large_finite_values(
    fitted: FittedCombiner,
) -> None:
    scaled = tuple((row[0] * 1e307, row[1]) for row in X)
    model = fit_combiner(scaled, Y, NAMES, training_id="large-units")
    assert model.score((2e307, 7.0)) == pytest.approx(fitted.score((2.0, 7.0)), abs=1e-12)
    assert fitted.model_copy(update={"intercept": 1_000.0}).score((0.0, 7.0)) == 1.0
    assert fitted.model_copy(update={"intercept": -1_000.0}).score((0.0, 7.0)) == 0.0


@pytest.mark.parametrize(
    ("x", "y", "names"),
    [
        ((), (), NAMES),
        (X, Y, ()),
        (X, Y[:-1], NAMES),
        (X, Y, ("repeat", "repeat")),
        (X, Y, ("ok", " ")),
        (((0.0,),) * 6, Y, NAMES),
        (((nan, 0.0),) * 6, Y, NAMES),
        (((inf, 0.0),) * 6, Y, NAMES),
        (X, (True,) * 6, NAMES),
        (X, (False,) * 6, NAMES),
    ],
)
def test_bad_training_samples_fail(
    x: Sequence[Sequence[float]], y: Sequence[bool], names: Sequence[str]
) -> None:
    with pytest.raises(CalibrationError):
        fit_combiner(x, y, names, training_id="invalid")


def test_labels_must_not_silently_coerce_integers() -> None:
    labels = cast("Sequence[bool]", (0, 0, 0, 1, 1, 1))
    with pytest.raises(CalibrationError, match="booleans"):
        fit_combiner(X, labels, NAMES, training_id="invalid")


@pytest.mark.parametrize("l2", [0, -1, nan, inf])
def test_invalid_regularization_fails(l2: float) -> None:
    with pytest.raises(CalibrationError, match="settings"):
        fit_combiner(X, Y, NAMES, training_id="invalid", l2=l2)


@pytest.mark.parametrize("tolerance", [0, -1, nan, inf])
def test_invalid_tolerance_fails(tolerance: float) -> None:
    with pytest.raises(CalibrationError, match="settings"):
        fit_combiner(X, Y, NAMES, training_id="invalid", tolerance=tolerance)


def test_missing_provenance_invalid_iterations_and_nonconvergence_fail() -> None:
    for iterations in (0, -1, True):
        with pytest.raises(CalibrationError, match="settings"):
            fit_combiner(X, Y, NAMES, training_id="invalid", max_iterations=iterations)
    with pytest.raises(CalibrationError, match="provenance"):
        fit_combiner(X, Y, NAMES, training_id=" ")
    with pytest.raises(CalibrationError, match="did not converge"):
        fit_combiner(X, Y, NAMES, training_id="too-short", max_iterations=1)


@pytest.mark.parametrize("features", [(1.0,), (nan, 7.0), (inf, 7.0)])
def test_bad_prediction_features_fail(fitted: FittedCombiner, features: Sequence[float]) -> None:
    with pytest.raises(CalibrationError, match="finite"):
        fitted.score(features)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("feature_names", ()),
        ("means", (1.0,)),
        ("training_positives", 6),
        ("iterations", 2001),
        ("gradient_norm", 1.0),
        ("weights", (1.0, 1.0)),
    ],
)
def test_serialized_fit_rejects_inconsistent_state(
    fitted: FittedCombiner, key: str, value: object
) -> None:
    data = fitted.model_dump()
    data[key] = value
    with pytest.raises(ValidationError):
        FittedCombiner.model_validate(data)


def test_prediction_numerical_overflow_is_explicit(fitted: FittedCombiner) -> None:
    tiny = fitted.model_copy(update={"scales": (1e-308, 0.0)})
    with pytest.raises(CalibrationError, match="standardized"):
        tiny.score((1e308, 7.0))
    subnormal = fitted.model_copy(update={"scales": (5e-324, 0.0)})
    with pytest.raises(CalibrationError, match="standardized"):
        subnormal.score((1.0, 7.0))
    overflow = fitted.model_copy(update={"weights": (1e308, 0.0)})
    with pytest.raises(CalibrationError, match="Combined"):
        overflow.score((1e308, 7.0))
    sums = fitted.model_copy(update={"weights": (1e308, 0.0), "intercept": 1e308})
    with pytest.raises(CalibrationError, match="Combined"):
        sums.score((3.0, 7.0))


def test_wilson_report_matches_known_interval_and_keeps_empty_unknown() -> None:
    report = precision_report([0.8] * 40, [True] * 40, threshold=0.8)
    assert report.selected == report.correct == 40
    assert report.precision == 1
    assert report.lower == pytest.approx(0.9123783988)
    assert report.upper == pytest.approx(1)
    none = precision_report([0.2], [False], threshold=0.8)
    assert none.selected == 0
    assert none.precision is none.lower is none.upper is None
    wider = precision_report([0.8] * 40, [True] * 40, threshold=0.8, confidence=0.99)
    assert wider.lower is not None
    assert report.lower is not None
    assert wider.lower < report.lower


def test_threshold_chooses_lowest_supported_cutoff_without_splitting_ties() -> None:
    scores, labels = [0.9] * 40 + [0.8] * 10 + [0.1] * 10, [True] * 50 + [False] * 10
    result = select_threshold(
        scores, labels, development_id="dev", minimum_precision=0.9, minimum_samples=30
    )
    assert result.threshold == 0.8
    assert result.report.selected == result.report.correct == 50
    assert result.development_samples == 60
    assert "independent_audit" in result.evidence_role
    tied = select_threshold(
        [0.8] * 50,
        [True] * 40 + [False] * 10,
        development_id="ties",
        minimum_precision=0.9,
        minimum_samples=30,
    )
    assert tied.threshold is None
    assert tied.report.precision is None
    assert (
        select_threshold(
            list(reversed(scores)),
            list(reversed(labels)),
            development_id="dev",
            minimum_precision=0.9,
            minimum_samples=30,
        )
        == result
    )


def test_no_threshold_without_enough_precision_or_samples() -> None:
    for scores, labels in [([], []), ([0.9], [True]), ([0.9] * 40, [False] * 40)]:
        selection = select_threshold(
            scores, labels, development_id="insufficient", minimum_precision=0.9, minimum_samples=30
        )
        assert selection.threshold is None
    audit = precision_report([0.9] * 10, [False] * 10, threshold=0.8)
    assert audit.precision == 0
    assert audit.lower == 0


@pytest.mark.parametrize(
    ("scores", "labels"),
    [
        ([nan], [True]),
        ([inf], [True]),
        ([-0.1], [True]),
        ([1.1], [True]),
        ([0.1], []),
        ([0.1], [1]),
    ],
)
def test_invalid_development_data_fails(scores: Sequence[float], labels: Sequence[bool]) -> None:
    with pytest.raises(CalibrationError, match="Scores"):
        select_threshold(
            scores, labels, development_id="invalid", minimum_precision=0.9, minimum_samples=30
        )


@pytest.mark.parametrize("confidence", [0, 1, nan])
def test_invalid_confidence_fails_even_for_empty_samples(confidence: float) -> None:
    with pytest.raises(CalibrationError, match="Confidence"):
        precision_report([], [], threshold=0.5, confidence=confidence)


@pytest.mark.parametrize("threshold", [nan, inf, -0.1, 1.1])
def test_invalid_threshold_fails(threshold: float) -> None:
    with pytest.raises(CalibrationError, match="Threshold"):
        precision_report([], [], threshold=threshold)


def test_threshold_requires_explicit_targets_and_sample_provenance() -> None:
    for precision in (0, -1, 1.1, nan):
        with pytest.raises(CalibrationError, match="requirements"):
            select_threshold(
                [], [], development_id="dev", minimum_precision=precision, minimum_samples=30
            )
    for minimum_samples in (0, -1, True):
        with pytest.raises(CalibrationError, match="requirements"):
            select_threshold(
                [], [], development_id="dev", minimum_precision=0.9, minimum_samples=minimum_samples
            )
    with pytest.raises(CalibrationError, match="provenance"):
        select_threshold([], [], development_id=" ", minimum_precision=0.9, minimum_samples=30)
