"""Forecast baseline: no post-cutoff inputs, honest validation, a number only when earned."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from influence.schemas.atlas import Forecast
from influence.services.forecast import (
    MIN_TEST_EXAMPLES,
    Example,
    Features,
    LeakageError,
    Validation,
    check_no_leakage,
    fit,
    forecast_ask,
    rolling_splits,
    validate,
)

BASE = datetime(2099, 1, 1, tzinfo=UTC)
FIXTURES = Path(__file__).parent / "fixtures" / "atlas"


def _day(offset: int) -> datetime:
    return BASE + timedelta(days=offset)


def _example(index: int, won: bool, topic: str = "t0", amendments: int = 1) -> Example:
    return Example(
        procedure_id=f"proc-{index // 3}",
        features=Features(topic=topic, amendment_count=amendments, observed_at=_day(index)),
        decided_at=_day(index + 1),
        won=won,
    )


def _signal(count: int) -> list[Example]:
    """Asks with an amendment in topic t0 win; all others lose, so the features carry signal."""
    return [_example(i, won=(i % 2 == 0), topic="t0" if i % 2 == 0 else "t1") for i in range(count)]


def _noise(count: int) -> list[Example]:
    """Outcomes unrelated to the features: a hash of the index, not of anything the model sees."""
    return [
        _example(i, won=hashlib.sha256(str(i).encode()).digest()[0] < 128, topic=f"t{i % 2}")
        for i in range(count)
    ]


def _weak(count: int) -> list[Example]:
    """Outcomes only slightly tied to the topic: the index scramble shares its parity."""
    return [_example(i, won=((i * 7919) % 10) < 5, topic=f"t{i % 2}") for i in range(count)]


def test_a_feature_observed_after_the_cutoff_is_rejected() -> None:
    late = Features(topic="t0", amendment_count=1, observed_at=_day(10))
    with pytest.raises(LeakageError, match="after the cutoff"):
        check_no_leakage(_day(5), late)
    with pytest.raises(LeakageError):
        forecast_ask(
            ask_id="ask:x",
            procedure_id="2099/0001(COD)",
            as_of=_day(5),
            features=late,
            history=[],
            validation=validate([]),
        )


def test_an_outcome_decided_on_or_after_the_cutoff_cannot_train() -> None:
    history = [_example(0, True)]  # decided on day 1
    assert fit(_day(2), history).trained == 1
    with pytest.raises(LeakageError, match="not known before the cutoff"):
        fit(_day(1), history)
    knew_late = Example(
        procedure_id="p",
        features=Features(topic="t0", amendment_count=1, observed_at=_day(6)),
        decided_at=_day(7),
        won=True,
    )
    with pytest.raises(LeakageError):
        check_no_leakage(_day(5), Features("t0", 1, _day(0)), [knew_late])


@pytest.mark.parametrize("observed", [1, 9])
def test_an_example_whose_features_were_not_observed_before_its_outcome_is_refused(
    observed: int,
) -> None:
    """Regression: features observed on or after the decision could train or test a model."""
    with pytest.raises(ValueError, match="not before the outcome"):
        Example(
            procedure_id="p",
            features=Features(topic="t0", amendment_count=1, observed_at=_day(observed)),
            decided_at=_day(1),
            won=True,
        )


@given(
    flags=st.lists(st.booleans(), min_size=1, max_size=30),
    topics=st.lists(st.sampled_from(["a", "b", None]), min_size=1, max_size=30),
)
def test_predictions_are_probabilities_and_ignore_example_order(
    flags: list[bool], topics: list[str | None]
) -> None:
    history = [
        _example(i, won=flag, topic=topics[i % len(topics)] or "none", amendments=i % 2)
        for i, flag in enumerate(flags)
    ]
    probe = Features(topic="a", amendment_count=1, observed_at=_day(0))
    forward = fit(_day(100), history).predict(probe)
    backward = fit(_day(100), history[::-1]).predict(probe)
    assert 0.0 <= forward <= 1.0
    assert forward == pytest.approx(backward)


def test_a_group_with_no_history_falls_back_to_prevalence() -> None:
    model = fit(_day(100), _signal(10))
    unseen = Features(topic="never-seen", amendment_count=3, observed_at=_day(0))
    assert model.predict(unseen) == pytest.approx(model.prevalence)
    assert fit(_day(100), []).predict(unseen) == 0.0


@given(count=st.integers(0, 80), blocks=st.integers(1, 6))
def test_rolling_splits_never_train_on_the_future_or_share_a_procedure(
    count: int, blocks: int
) -> None:
    examples = _noise(count)
    for split in rolling_splits(examples, blocks):
        assert split.test
        assert not set(split.train) & set(split.test)
        assert all(examples[i].decided_at < split.as_of for i in split.train)
        test_procedures = {examples[i].procedure_id for i in split.test}
        assert all(examples[i].procedure_id not in test_procedures for i in split.train)


def test_rolling_splits_need_a_block_and_skip_empty_ones() -> None:
    with pytest.raises(ValueError, match="at least one"):
        rolling_splits(_noise(10), 0)
    tiny = rolling_splits(_noise(3), 4)
    assert len(tiny) == 1
    assert tiny[0].train == ()


def test_a_real_signal_beats_prevalence_and_earns_a_number() -> None:
    result = validate(_signal(400))
    assert result.adequate, result.reasons
    assert result.test_examples >= MIN_TEST_EXAMPLES
    assert result.model_brier is not None
    assert result.baseline_brier is not None
    assert result.model_brier < result.baseline_brier
    assert result.model_auc is not None
    assert result.model_auc > 0.9
    assert result.baseline_auc == 0.5


def test_noise_does_not_earn_a_number() -> None:
    result = validate(_noise(400))
    assert not result.adequate
    assert any("Brier" in reason or "chance" in reason for reason in result.reasons)


def test_a_weak_edge_over_prevalence_is_not_enough_for_a_number() -> None:
    result = validate(_weak(400))
    assert result.model_brier is not None
    assert result.baseline_brier is not None
    assert result.model_brier < result.baseline_brier  # better than prevalence, but only barely
    assert not result.adequate
    assert any("by 5%" in reason for reason in result.reasons)


def test_too_little_data_is_reported_with_counts() -> None:
    few = validate(_signal(20))
    assert not few.adequate
    assert any("test examples" in reason for reason in few.reasons)
    tiny = validate(_signal(8))
    assert any("rolling splits" in reason for reason in tiny.reasons)


def test_blocks_with_one_outcome_are_not_tested() -> None:
    result = validate([_example(i, won=True) for i in range(40)])
    assert (result.tested_splits, result.test_examples) == (0, 0)
    assert result.model_brier is None
    assert not result.adequate


def _forecast(history: list[Example], validation: Validation, amendments: int = 1) -> Forecast:
    return forecast_ask(
        ask_id="ask:b-labels",
        procedure_id="2099/0002(COD)",
        as_of=_day(500),
        features=Features(
            topic="t0",
            amendment_count=amendments,
            observed_at=_day(400),
            missing=("rapporteur_draft", "council_position"),
        ),
        history=history,
        validation=validation,
        horizon="Before the plenary vote; no date is set",
    )


def test_with_earned_validation_the_forecast_is_a_probability_with_reasons() -> None:
    history = _signal(400)
    forecast = _forecast(history, validate(history))
    assert forecast.score_type == "probability"
    assert forecast.score is not None
    assert 0.0 <= forecast.score <= 1.0
    assert any("past asks decided before the cutoff" in reason for reason in forecast.reasons)
    assert forecast.missing_features == ("rapporteur_draft", "council_position")


def test_without_validation_the_forecast_is_a_scenario_with_no_score() -> None:
    forecast = _forecast([], validate([]))
    assert forecast.score_type == "scenario"
    assert forecast.score is None
    assert forecast.scenario
    assert "historical_outcomes" in forecast.missing_features
    assert any("rolling splits" in reason for reason in forecast.reasons)


def test_an_ask_no_amendment_carries_gets_an_unlikely_scenario() -> None:
    supported = _forecast([], validate([]), amendments=2)
    bare = _forecast([], validate([]), amendments=0)
    assert supported.scenario != bare.scenario
    assert "Unlikely" in (bare.scenario or "")
    assert "No amendment carries the ask yet." in bare.reasons


def test_a_missing_validation_run_still_gives_a_reason() -> None:
    skipped = Validation(0, 0, 0, None, None, None, None, adequate=False, reasons=())
    forecast = _forecast([], skipped)
    assert "No validation was run." in forecast.reasons


def test_the_scenario_has_the_shape_of_the_committed_fixture() -> None:
    lines = (FIXTURES / "forecasts.jsonl").read_text(encoding="utf-8").splitlines()
    expected = Forecast.model_validate(json.loads(lines[0]))
    got = _forecast([], validate([]))
    assert (got.score_type, got.score, got.ask_id, got.procedure_id) == (
        expected.score_type,
        expected.score,
        expected.ask_id,
        expected.procedure_id,
    )
    assert got.forecast_id == expected.forecast_id.replace("b-ask-labels", "ask-b-labels")
    # With no history the baseline also names historical outcomes as missing; the fixture
    # (written by hand, with a different forecast ID scheme) does not.
    assert got.missing_features == (*expected.missing_features, "historical_outcomes")
    assert got.horizon == expected.horizon
    assert got.reasons
