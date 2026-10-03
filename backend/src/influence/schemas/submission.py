"""Our normalized submission contract; a 19:00 adapter maps the organizers' format onto it.

The organizers' input format is still unknown (decision D5), so nothing here guesses it.
"""

import unicodedata
from typing import Annotated

from pydantic import AfterValidator

from influence.schemas.comparison import ComparisonRequest, ComparisonResult
from influence.schemas.scoring import FrozenModel

# Control characters (including NEL) and line or paragraph separators split lines in
# common CSV and text readers, which would corrupt the join on pair_id.
_LINE_BREAKING_CATEGORIES = frozenset({"Cc", "Zl", "Zp"})


def _plain_pair_id(value: str) -> str:
    """Reject identifiers that a grader's CSV reader could split, strip or misread."""
    if (
        not value
        or value != value.strip()
        or any(unicodedata.category(character) in _LINE_BREAKING_CATEGORIES for character in value)
    ):
        raise ValueError(
            "pair_id must be non-empty, without surrounding whitespace, control characters "
            "or line separators"
        )
    return value


PairId = Annotated[str, AfterValidator(_plain_pair_id)]


class SubmissionPair(ComparisonRequest):
    """One supplied pair: a comparison request plus the organizers' identifier.

    Subclassing keeps one copy of the text rules: `old: null` means the original wording
    is unknown, exactly as in `/compare`, and the scorer's length limits apply unchanged.
    """

    pair_id: PairId


class PairEvidence(FrozenModel):
    """One line of `pairs.evidence.jsonl`: the submitted score beside the signals behind it.

    `influence_score` is deliberately unconstrained here; the submission service
    validates it explicitly so a future combiner's bad output is reported, not coerced.
    """

    pair_id: str
    influence_score: float
    comparison: ComparisonResult
