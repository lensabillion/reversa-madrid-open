"""Mode labels: each of the plan's four labels follows from typed coverage, never from guesses."""

import pytest

from influence.schemas.atlas import LawRecord, LawStatus, Layer, LayerCoverage, LayerStatus
from influence.services import modes

AI_ACT = "2021/0106(COD)"


def row(layer: Layer, status: LayerStatus = "complete", count: int | None = 3) -> LayerCoverage:
    return LayerCoverage(
        layer=layer, status=status, count=count, reason=None if status == "complete" else "why"
    )


FULL = (
    row("asks"),
    row("committee_amendments"),
    row("plenary_amendments"),
    row("final_act", count=None),
)


def law(*changed: LayerCoverage, status: LawStatus = "completed") -> LawRecord:
    """A fully covered law with the given rows replaced."""
    rows = {item.layer: item for item in (*FULL, *changed)}
    return LawRecord(
        procedure_id=AI_ACT,
        title="Artificial Intelligence Act",
        status=status,
        coverage=tuple(rows.values()),
    )


def test_a_fully_covered_closed_law_has_no_label() -> None:
    assert modes.mode_labels(law()) == ()


@pytest.mark.parametrize(
    "asks",
    [
        row("asks", "missing", 0),
        row("asks", "missing", None),
        row("asks", "not_collected", None),
        row("asks", "not_applicable", None),
        row("asks", "complete", 0),
    ],
)
def test_a_law_without_asks_is_contextual_evidence(asks: LayerCoverage) -> None:
    assert modes.mode_labels(law(asks)) == (modes.CONTEXTUAL,)


def test_partial_asks_are_still_textual_evidence() -> None:
    assert modes.mode_labels(law(row("asks", "partial", 2))) == ()


def test_no_amendment_stage_needs_both_layers_to_hold_none() -> None:
    committee = row("committee_amendments", "missing", 0)
    plenary = row("plenary_amendments", "not_applicable", None)

    assert modes.mode_labels(law(committee, plenary)) == (modes.NO_AMENDMENT_STAGE,)
    assert modes.mode_labels(law(committee)) == ()
    assert modes.mode_labels(law(plenary)) == ()
    counted_zero = row("plenary_amendments", "complete", 0)
    assert modes.mode_labels(law(committee, counted_zero)) == (modes.NO_AMENDMENT_STAGE,)


def test_amendments_nobody_looked_for_are_not_called_absent() -> None:
    unknown = (
        row("committee_amendments", "not_collected", None),
        row("plenary_amendments", "not_collected", None),
    )

    assert modes.mode_labels(law(*unknown)) == ()


@pytest.mark.parametrize("status", ["not_applicable", "missing", "not_collected"])
def test_an_open_file_without_its_final_act_is_in_negotiation(status: LayerStatus) -> None:
    final_act = row("final_act", status, None)

    assert modes.mode_labels(law(final_act, status="ongoing")) == (modes.IN_PROGRESS,)
    # A closed file with no final act has a missing source, not an open negotiation.
    assert modes.mode_labels(law(final_act)) == ()


def test_an_open_file_whose_final_act_was_read_is_not_in_negotiation() -> None:
    assert modes.mode_labels(law(status="ongoing")) == ()


@pytest.mark.parametrize("layer", ["committee_amendments", "plenary_amendments"])
@pytest.mark.parametrize("status", ["partial", "stale"])
def test_a_partial_or_stale_amendment_layer_is_partial_coverage(
    layer: Layer, status: LayerStatus
) -> None:
    assert modes.mode_labels(law(row(layer, status))) == (modes.PARTIAL_AMENDMENTS,)


def test_a_law_with_no_coverage_rows_claims_only_what_was_not_tried() -> None:
    """Rows nobody wrote read as not collected: no asks, an open file, amendments unknown."""
    bare = LawRecord(procedure_id=AI_ACT, title="Bare", status="ongoing", coverage=())

    assert modes.mode_labels(bare) == (modes.CONTEXTUAL, modes.IN_PROGRESS)


def test_labels_keep_the_order_of_the_plan_table() -> None:
    everything = law(
        row("asks", "missing", 0),
        row("committee_amendments", "missing", 0),
        row("plenary_amendments", "missing", 0),
        row("final_act", "not_applicable", None),
        status="ongoing",
    )
    open_and_partial = law(
        row("committee_amendments", "partial", 9),
        row("final_act", "not_applicable", None),
        status="ongoing",
    )

    assert modes.mode_labels(everything) == (
        modes.CONTEXTUAL,
        modes.NO_AMENDMENT_STAGE,
        modes.IN_PROGRESS,
    )
    assert modes.mode_labels(open_and_partial) == (modes.IN_PROGRESS, modes.PARTIAL_AMENDMENTS)
