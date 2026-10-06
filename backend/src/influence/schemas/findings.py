"""The report's five questions for one law, as data the explorer's Outcomes tab can show.

`influence report` writes these answers as Markdown; `report.law_findings` returns the
same lines, split into a headline, details, evidence references and the limitation, so
a reader of the data and the report never disagree on a number.
"""

from typing import Literal

from influence.schemas.atlas import NonEmpty, ProcedureId
from influence.schemas.scoring import FrozenModel

type Question = Literal["WHO", "WHAT", "TOWARDS", "HOW", "NEXT"]
# `computed`: at least one file the question reads is written and valid. `not_run`: none
# is, and `command` writes the first of them.
type FindingStatus = Literal["computed", "not_run"]


class EvidenceRef(FrozenModel):
    """A file under the data root and, when the report names one, the field holding the rows."""

    file: NonEmpty
    field: NonEmpty | None


class Finding(FrozenModel):
    question: Question
    title: NonEmpty
    status: FindingStatus
    # The report's headline line; None only when nothing the question reads is written.
    headline: NonEmpty | None
    # The section's other lines, in report order, Markdown backticks kept.
    details: tuple[NonEmpty, ...]
    evidence: tuple[EvidenceRef, ...]
    limitation: NonEmpty
    # Set when `status` is `not_run`: the command that writes the missing input.
    command: NonEmpty | None
    # Each input that is missing or invalid, with the command that writes it.
    notes: tuple[NonEmpty, ...]


class LawFindings(FrozenModel):
    schema_version: Literal["findings-1"] = "findings-1"
    procedure_id: ProcedureId
    slug: NonEmpty
    title: NonEmpty
    run_id: NonEmpty
    findings: tuple[Finding, ...]
