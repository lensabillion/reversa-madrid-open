"""Part 8, mode labels: what a law's missing layers mean for whoever reads its view.

`docs/plan.md`, section 6, names each gap once ("Negotiation in progress", not an empty
outcomes table), so the explorer shows a label instead of leaving a reader to guess why a
law has no links or no wins. The labels are derived here, from the typed coverage part 1
recorded, and nowhere else: the page renders them and never infers one from an empty list.
"""

from influence.schemas.atlas import LawRecord, LayerCoverage, LayerStatus
from influence.schemas.atlas_view import ModeLabel

CONTEXTUAL: ModeLabel = "Contextual evidence, not textual"
NO_AMENDMENT_STAGE: ModeLabel = "No amendment stage"
IN_PROGRESS: ModeLabel = "Negotiation in progress"
PARTIAL_AMENDMENTS: ModeLabel = "Partial amendment coverage"

# No row for a layer is read as `not_collected`: the run did not try.
_NO_ASKS: frozenset[LayerStatus] = frozenset({"missing", "not_collected", "not_applicable"})
# `not_collected` is left out on purpose: amendments nobody looked for are unknown, and
# "No amendment stage" would state as a finding what the run never checked.
_NO_AMENDMENTS: frozenset[LayerStatus] = frozenset({"missing", "not_applicable"})
_ACT_READ: frozenset[LayerStatus] = frozenset({"complete", "partial", "stale"})
_INCOMPLETE: frozenset[LayerStatus] = frozenset({"partial", "stale"})


def _without_asks(row: LayerCoverage | None) -> bool:
    return row is None or row.status in _NO_ASKS or row.count == 0


def _without_amendments(row: LayerCoverage | None) -> bool:
    return row is not None and (row.status in _NO_AMENDMENTS or row.count == 0)


def mode_labels(law: LawRecord) -> tuple[ModeLabel, ...]:
    """The labels that apply to the law, in the order of the plan's table.

    A label is added only on what the coverage rows say. An open file whose final act was
    read anyway carries no "Negotiation in progress", and a closed file with no final act
    carries none either: its gap is a missing source, which the coverage row already says.
    """
    rows = {item.layer: item for item in law.coverage}
    amendments = (rows.get("committee_amendments"), rows.get("plenary_amendments"))
    final_act = rows.get("final_act")
    applies: tuple[tuple[ModeLabel, bool], ...] = (
        (CONTEXTUAL, _without_asks(rows.get("asks"))),
        (NO_AMENDMENT_STAGE, all(_without_amendments(row) for row in amendments)),
        (
            IN_PROGRESS,
            law.status == "ongoing" and (final_act is None or final_act.status not in _ACT_READ),
        ),
        (
            PARTIAL_AMENDMENTS,
            any(row is not None and row.status in _INCOMPLETE for row in amendments),
        ),
    )
    return tuple(label for label, holds in applies if holds)
