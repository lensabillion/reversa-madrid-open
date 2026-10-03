"""Blind audit: Wilson intervals, a reproducible proportional sample, two-reader summaries."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from influence.schemas.atlas import LinkAssessment
from influence.services.audit import (
    AuditError,
    Verdict,
    draw_sample,
    summarise,
    wilson_interval,
)

SPAN = {"record_id": "am:x", "field": "new_text", "start": 0, "end": 1, "text": "P"}


def _link(
    key: str, tier: str | None = "copied", law: str = "2099/0001(COD)", status: str = "published"
) -> LinkAssessment:
    data: dict[str, object] = {
        "link_id": f"link:{key}",
        "procedure_id": law,
        "amendment_id": "am:x",
        "ask_id": "ask:x",
        "status": status,
        "support_score": 0.5,
        "time_eligibility": "ask_first",
        "method": "test",
        "method_revision": "t1",
        "tier": tier,
    }
    if status == "published":
        data |= {"amendment_spans": [SPAN], "ask_spans": [SPAN]}
    return LinkAssessment.model_validate(data)


def test_thirty_of_thirty_bounds_precision_near_point_886_from_below() -> None:
    low, high = wilson_interval(30, 30)
    assert round(low, 3) == 0.886
    assert high == pytest.approx(1.0)


def test_no_trials_means_nothing_is_known() -> None:
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_known_wilson_value() -> None:
    low, high = wilson_interval(8, 10)
    assert (round(low, 3), round(high, 3)) == (0.490, 0.943)


@given(total=st.integers(1, 500), data=st.data())
def test_interval_is_ordered_inside_unit_range_and_holds_the_estimate(
    total: int, data: st.DataObject
) -> None:
    correct = data.draw(st.integers(0, total))
    low, high = wilson_interval(correct, total)
    assert 0.0 <= low <= correct / total <= high <= 1.0


def test_sample_is_exact_size_published_only_and_reproducible() -> None:
    links = [_link(f"a{i}") for i in range(30)] + [_link("draft", status="unconfirmed", tier=None)]
    first = draw_sample(links, 10, seed=7)
    assert len(first) == 10
    assert all(link.status == "published" for link in first)
    assert first == draw_sample(links, 10, seed=7)
    assert first != draw_sample(links, 10, seed=8)


def test_sample_is_spread_over_law_and_tier_in_proportion() -> None:
    links = (
        [_link(f"c{i}") for i in range(90)]
        + [_link(f"r{i}", tier="reworded") for i in range(9)]
        + [_link("b0", law="2099/0002(COD)")]
    )
    sample = draw_sample(links, 10, seed=1)
    counts = {
        (link.procedure_id, link.tier): sum(
            1
            for other in sample
            if (other.procedure_id, other.tier) == (link.procedure_id, link.tier)
        )
        for link in sample
    }
    assert sum(counts.values()) == 10
    # Regression: the one link of the second law had an exact share of 0.1 and got no seat,
    # so a weak stratum could hide. It now takes one from the stratum most over its share.
    assert counts[("2099/0001(COD)", "copied")] == 8
    assert counts[("2099/0001(COD)", "reworded")] == 1
    assert counts[("2099/0002(COD)", "copied")] == 1


def test_every_stratum_has_a_seat_even_when_seats_are_fewer_than_strata() -> None:
    links = [_link(f"l{i}", law=f"2099/{i:04d}(COD)") for i in range(1, 6)] + [
        _link(f"x{i}") for i in range(20)
    ]
    sample = draw_sample(links, 3, seed=4)
    assert len(sample) == 5
    assert len({link.procedure_id for link in sample}) == 5


def test_a_short_pool_is_returned_whole() -> None:
    links = [_link(f"a{i}") for i in range(3)]
    assert len(draw_sample(links, 40, seed=0)) == 3
    assert draw_sample([], 40, seed=0) == ()


def _labels(**verdicts: dict[str, Verdict]) -> dict[str, dict[str, Verdict]]:
    return {f"link:{key}": value for key, value in verdicts.items()}


def test_a_split_verdict_counts_as_incorrect_in_the_headline_precision() -> None:
    sample = [_link(key) for key in "abcde"] + [_link("f", tier="reworded")]
    labels = _labels(
        a={"r1": "correct", "r2": "correct"},
        b={"r1": "correct", "r2": "correct"},
        c={"r1": "incorrect", "r2": "incorrect"},
        d={"r1": "correct", "r2": "incorrect"},
        e={"r1": "correct"},
    )
    report = summarise(sample, labels)
    assert (report.sampled, report.resolved, report.correct) == (6, 3, 2)
    assert (report.unresolved, report.unlabelled) == (1, 2)
    # Regression: the split link was dropped from the denominator, biasing precision up.
    assert report.precision == pytest.approx(2 / 4)
    assert (report.low, report.high) == wilson_interval(2, 4)
    assert report.agreed_precision == pytest.approx(2 / 3)
    assert report.by_tier == {"copied": (2, 3)}


def test_an_audit_with_no_resolved_links_has_no_precision() -> None:
    report = summarise([_link("a")], {})
    assert report.precision is None
    assert report.agreed_precision is None
    assert (report.low, report.high) == (0.0, 1.0)
    assert report.unlabelled == 1


def test_a_label_outside_the_sample_is_an_error() -> None:
    with pytest.raises(AuditError, match="outside the sample"):
        summarise([_link("a")], _labels(zzz={"r1": "correct", "r2": "correct"}))


def test_summarising_does_not_change_the_links() -> None:
    sample = [_link("a")]
    before = [link.model_dump() for link in sample]
    summarise(sample, _labels(a={"r1": "incorrect", "r2": "incorrect"}))
    assert [link.model_dump() for link in sample] == before
