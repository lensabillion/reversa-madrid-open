"""Known fixture counts and aggregation invariants, not model accuracy evidence."""

from dataclasses import replace
from datetime import date

import pytest
from atlas_fixture import CITY, LAW_A, LAW_B, MAKERS, WATCH, AtlasFixture, build_fixture
from hypothesis import given, settings
from hypothesis import strategies as st

from influence.schemas.atlas import LayerCoverage
from influence.services.atlas_analysis import OutcomeAnalysis, OutcomeCounts, aggregate_outcomes


def analyse(
    fixture: AtlasFixture, *, topic: str | None = None, year: int | None = None
) -> OutcomeAnalysis:
    return aggregate_outcomes(
        laws=fixture.laws,
        actors=fixture.actors,
        asks=fixture.asks,
        outcomes=fixture.outcomes,
        topic=topic,
        year=year,
    )


def test_fixture_counts_include_unmatched_and_keep_stages_separate() -> None:
    fixture = build_fixture()
    result = analyse(fixture)
    assert result.totals == (
        OutcomeCounts("heard", 6, 2, 2, 0, 0, 4, 1.0),
        OutcomeCounts("parliament_position", 6, 1, 1, 0, 0, 5, 1.0),
        OutcomeCounts("final_act", 6, 5, 2, 1, 2, 1, 0.4),
    )
    assert result.ask_ids == tuple(sorted(ask.ask_id for ask in fixture.asks))
    by_actor_stage = {(row.actor_id, row.counts.stage): row for row in result.rows}
    makers = by_actor_stage[MAKERS, "final_act"]
    assert makers.counts.full == 2
    assert "outcome:a-ask-makers-final" in makers.outcome_ids
    assert "art:32099R0001:article-6-1" in makers.evidence_record_ids
    assert set(makers.evidence_record_ids) >= {
        ask.document_id for ask in fixture.asks if ask.ask_id in makers.ask_ids
    }
    assert by_actor_stage[CITY, "final_act"].counts.partial == 1
    assert by_actor_stage[WATCH, "final_act"].counts.not_observed == 1
    assert by_actor_stage[WATCH, "heard"].counts.unknown == 1
    assert by_actor_stage[WATCH, "heard"].outcome_ids == ()
    assert all(row.incomplete for row in result.rows)
    assert any("final_act missing" in gap for row in result.rows for gap in row.coverage_gaps)
    assert tuple(item.procedure_id for item in result.coverage) == (LAW_A, LAW_B)


def test_partial_and_unknown_denominators_are_not_fractional_credit() -> None:
    fixture = build_fixture()
    fixture = replace(
        fixture,
        asks=tuple(ask.model_copy(update={"actor_id": MAKERS}) for ask in fixture.asks),
    )
    result = analyse(fixture)
    final = result.rows[-1]
    assert final.counts == OutcomeCounts("final_act", 6, 5, 2, 1, 2, 1, 0.4)
    without_outcomes = analyse(replace(fixture, outcomes=()))
    assert all(row.counts.assessed_asks == 0 for row in without_outcomes.rows)
    assert all(row.counts.full_win_rate is None for row in without_outcomes.rows)
    assert all(row.counts.unknown == 6 for row in without_outcomes.rows)


def test_exact_duplicates_and_multiple_support_records_do_not_multiply_wins() -> None:
    fixture = build_fixture()
    assert analyse(
        replace(
            fixture,
            asks=fixture.asks * 2,
            outcomes=fixture.outcomes * 2,
            laws=fixture.laws * 2,
            actors=fixture.actors * 2,
        )
    ) == analyse(fixture)
    extra = fixture.outcomes[2].model_copy(
        update={
            "outcome_id": "outcome:a-duplicate-amendment",
            "amendment_id": "am:a-other-amendment",
        }
    )
    result = analyse(replace(fixture, outcomes=(*fixture.outcomes, extra)))
    assert result.totals == analyse(fixture).totals
    makers = next(
        row for row in result.rows if row.actor_id == MAKERS and row.counts.stage == "final_act"
    )
    assert makers.outcome_ids == (
        "outcome:a-ask-makers-final",
        "outcome:a-ask-undated-final",
        "outcome:a-duplicate-amendment",
    )
    assert makers.counts.observed_asks == 2


def test_coalition_members_receive_joint_attribution_but_totals_count_ask_once() -> None:
    fixture = build_fixture()
    ask = fixture.asks[0].model_copy(update={"joint_actor_ids": (WATCH, WATCH, MAKERS)})
    result = analyse(replace(fixture, asks=(ask, *fixture.asks[1:])))
    assert result.totals == analyse(fixture).totals
    watch = next(
        row for row in result.rows if row.actor_id == WATCH and row.counts.stage == "final_act"
    )
    assert watch.ask_ids == ("ask:a-makers", "ask:a-watch")
    assert watch.joint_ask_ids == ("ask:a-makers",)
    assert watch.counts == OutcomeCounts("final_act", 2, 2, 1, 0, 1, 0, 0.5)
    makers = next(
        row for row in result.rows if row.actor_id == MAKERS and row.counts.stage == "final_act"
    )
    assert makers.joint_ask_ids == ("ask:a-makers",)
    assert makers.counts.observed_asks == 2


def test_topic_filter_and_procedure_year_do_not_infer_dates_or_topics() -> None:
    fixture = build_fixture()
    laws = tuple(law.model_copy(update={"proposed_on": date(2001, 1, 1)}) for law in fixture.laws)
    topic = fixture.laws[1].subjects[0]
    selected = analyse(replace(fixture, laws=laws), topic=topic, year=2099)
    assert selected.ask_ids == ("ask:b-labels",)
    assert selected.coverage[0].procedure_year == 2099
    assert selected.coverage[0].subjects == (topic,)
    assert selected.totals[-1] == OutcomeCounts("final_act", 1, 0, 0, 0, 0, 1, None)
    assert selected.topic == topic
    assert selected.procedure_year == 2099
    assert analyse(fixture, year=2001).rows == ()
    assert analyse(fixture, topic="Consumer information").rows == ()
    no_dates = replace(
        fixture, laws=tuple(law.model_copy(update={"proposed_on": None}) for law in laws)
    )
    assert analyse(no_dates, year=2099).ask_ids == analyse(fixture).ask_ids


def test_coverage_preserves_unreported_layers_and_unknown_outcomes() -> None:
    fixture = build_fixture()
    ask = fixture.asks[0]
    law = fixture.laws[0].model_copy(
        update={
            "coverage": (
                LayerCoverage(layer="asks", status="complete"),
                LayerCoverage(layer="actors", status="complete"),
                LayerCoverage(layer="final_act", status="complete"),
                LayerCoverage(layer="parliament_position", status="complete"),
                LayerCoverage(layer="committee_amendments", status="complete"),
                LayerCoverage(
                    layer="plenary_amendments",
                    status="not_applicable",
                    reason="No plenary amendments",
                ),
            )
        }
    )
    clean = replace(fixture, laws=(law,), asks=(ask,), outcomes=fixture.outcomes[:3])
    assert all(not row.incomplete for row in analyse(clean).rows)
    assert all(row.incomplete for row in analyse(replace(clean, outcomes=())).rows)
    empty_coverage = replace(clean, laws=(law.model_copy(update={"coverage": ()}),))
    assert analyse(empty_coverage).rows[-1].coverage_gaps == (
        f"{LAW_A}: asks coverage unreported",
        f"{LAW_A}: actors coverage unreported",
        f"{LAW_A}: final_act coverage unreported",
    )
    empty = aggregate_outcomes(laws=(), actors=(), asks=(), outcomes=())
    assert empty.rows == ()
    assert empty.coverage == ()
    assert all(counts.full_win_rate is None for counts in empty.totals)


def test_conflicting_records_or_results_and_dangling_references_fail_explicitly() -> None:
    fixture = build_fixture()
    changed_ask = fixture.asks[0].model_copy(update={"direction": "weaker"})
    with pytest.raises(ValueError, match="Conflicting records for ask:a-makers"):
        analyse(replace(fixture, asks=(*fixture.asks, changed_ask)))
    conflict = fixture.outcomes[2].model_copy(
        update={"outcome_id": "outcome:conflict", "result": "partial"}
    )
    with pytest.raises(ValueError, match="Conflicting outcomes for ask ask:a-makers at final_act"):
        analyse(replace(fixture, outcomes=(*fixture.outcomes, conflict)), topic="excluded")
    with pytest.raises(ValueError, match="Conflicting records for outcome:a-ask-makers-final"):
        analyse(
            replace(
                fixture,
                outcomes=(
                    *fixture.outcomes,
                    conflict.model_copy(update={"outcome_id": fixture.outcomes[2].outcome_id}),
                ),
            )
        )
    with pytest.raises(ValueError, match="references unknown law"):
        analyse(replace(fixture, laws=()))
    with pytest.raises(ValueError, match="references unknown actor"):
        analyse(replace(fixture, actors=()))
    with pytest.raises(ValueError, match="references unknown ask"):
        analyse(replace(fixture, asks=()))
    with pytest.raises(ValueError, match="different procedure from its ask"):
        analyse(
            replace(
                fixture, outcomes=(fixture.outcomes[0].model_copy(update={"procedure_id": LAW_B}),)
            )
        )


@settings(max_examples=20, derandomize=True)
@given(st.permutations(tuple(range(6))), st.permutations(tuple(range(9))))
def test_input_permutations_preserve_counts_and_provenance(
    ask_order: list[int], outcome_order: list[int]
) -> None:
    fixture = build_fixture()
    permuted = replace(
        fixture,
        laws=tuple(reversed(fixture.laws)),
        actors=tuple(reversed(fixture.actors)),
        asks=tuple(fixture.asks[index] for index in ask_order),
        outcomes=tuple(fixture.outcomes[index] for index in outcome_order),
    )
    assert analyse(permuted) == analyse(fixture)


def test_rank_order_uses_rates_then_assessed_counts_and_unknown_last() -> None:
    fixture = build_fixture()
    extra = fixture.asks[0].model_copy(update={"ask_id": "ask:city-full", "actor_id": CITY})
    extra_outcome = fixture.outcomes[2].model_copy(
        update={"ask_id": extra.ask_id, "outcome_id": "outcome:city-full"}
    )
    result = analyse(
        replace(fixture, asks=(*fixture.asks, extra), outcomes=(*fixture.outcomes, extra_outcome))
    )
    finals = [row for row in result.rows if row.counts.stage == "final_act"]
    assert [row.actor_id for row in finals[:2]] == [MAKERS, CITY]
    assert [row.counts.full_win_rate for row in finals[:2]] == [1.0, 0.5]
    assert finals[-1].counts.full_win_rate is None
    assert finals[-1].counts.unknown == 1
    assert "Raw observed" in result.ranking_basis
    # Equal zero rates use assessed sample size before stable actor identity.
    shared = fixture.asks[3].model_copy(update={"joint_actor_ids": (WATCH,)})
    tied = analyse(replace(fixture, asks=(*fixture.asks[:3], shared, *fixture.asks[4:])))
    zeros = [
        row
        for row in tied.rows
        if row.counts.stage == "final_act" and row.counts.full_win_rate == 0
    ]
    assert zeros[0].actor_id == WATCH
    assert zeros[0].counts.assessed_asks == 2
    assert [row.actor_id for row in zeros[1:]] == sorted(row.actor_id for row in zeros[1:])


def test_complete_ask_inventory_count_mismatch_is_visible_with_or_without_rows() -> None:
    fixture = build_fixture()
    law = fixture.laws[0].model_copy(
        update={
            "coverage": (
                LayerCoverage(layer="asks", status="complete", count=5),
                LayerCoverage(layer="actors", status="complete"),
                LayerCoverage(layer="final_act", status="complete"),
            )
        }
    )
    partial_inventory = replace(
        fixture, laws=(law,), asks=fixture.asks[:1], outcomes=fixture.outcomes[:3]
    )
    result = analyse(partial_inventory)
    final = result.rows[-1]
    assert final.counts.unknown == 0
    assert final.incomplete
    assert any(
        "coverage reports 5, supplied 1 canonical asks" in gap for gap in final.coverage_gaps
    )
    assert result.incomplete
    empty = analyse(replace(partial_inventory, asks=(), outcomes=()))
    assert empty.rows == ()
    assert empty.incomplete
    assert any(
        "coverage reports 5, supplied 0 canonical asks" in gap for gap in empty.coverage_gaps
    )
    consistent = law.model_copy(
        update={
            "coverage": (
                LayerCoverage(layer="asks", status="complete", count=1),
                LayerCoverage(layer="actors", status="complete"),
                LayerCoverage(layer="final_act", status="complete"),
            )
        }
    )
    assert not analyse(replace(partial_inventory, laws=(consistent,))).rows[-1].incomplete
