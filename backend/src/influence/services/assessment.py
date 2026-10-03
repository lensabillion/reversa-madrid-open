"""Part 4, verify links: judge one candidate (an amendment and an ask) from explicit signals.

Every rule here is a readable lexical rule with a threshold that is a placeholder: no
calibration exists yet (the practice loop sets and freezes them, `rev-zzur`), so the output
carries a support score and the method, never a probability. A link is published only when
the ask was dated before the amendment, the original wording is known, the quoted spans
match their sources exactly, and the evidence tier is one the caller allows. Linear in the
text length; the scorer's token diff is O(n*m) at 800 tokens per side.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from influence.schemas.atlas import (
    Amendment,
    Ask,
    Direction,
    LinkAssessment,
    LinkStatus,
    LinkTier,
    SourceSpan,
    SpanField,
    TimeEligibility,
    id_part,
    span_matches,
)
from influence.schemas.retrieval import PassageChange
from influence.schemas.scoring import (
    ChangeSpan,
    Operation,
    ScoreRequest,
    ScoreResult,
    TextChange,
    TextSpan,
)
from influence.services.passage_change import read_changes
from influence.services.scoring import score_pair

METHOD = "lexical-rules"
METHOD_REVISION = "rules-1"
# Placeholders until the practice loop calibrates them on LobbyPlag and freezes them.
COPIED_THRESHOLD = 0.7
REWORDED_THRESHOLD = 0.4
SHORT_EDIT_TOKENS = 3
DEFAULT_PUBLISHABLE: frozenset[LinkTier] = frozenset({"copied", "reworded"})

_STRICTER_WORDS = frozenset({"shall", "must", "required", "least", "minimum"})
_WEAKER_WORDS = frozenset({"may", "can", "optional"})
_OPPOSITE: dict[Direction, Direction] = {"stricter": "weaker", "weaker": "stricter"}


@dataclass(frozen=True, slots=True)
class _Reading:
    change: PassageChange
    result: ScoreResult


def amendment_direction(spans: Iterable[ChangeSpan]) -> Direction:
    """Stricter or weaker from obligation cues in the changed words; otherwise unknown.

    Adding "shall" or "at least", or dropping "may", tightens; the reverse loosens. Only
    these cue words are read, so most edits come back unknown rather than guessed.
    """
    stricter = weaker = 0
    for span in spans:
        for word in span.text.casefold().split():
            word = word.strip(".,;:()'\"")
            if span.operation == "insert":
                stricter += word in _STRICTER_WORDS
                weaker += word in _WEAKER_WORDS
            else:
                weaker += word in _STRICTER_WORDS
                stricter += word in _WEAKER_WORDS
    if stricter == weaker:
        return "unknown"
    return "stricter" if stricter > weaker else "weaker"


def _time_eligibility(amendment: Amendment, ask: Ask) -> TimeEligibility:
    if amendment.tabled_on is None or ask.submitted_at is None:
        return "unknown_date"
    return "ask_first" if ask.submitted_at.date() < amendment.tabled_on else "amendment_first"


def _merge(spans: Iterable[TextSpan], text: str) -> list[tuple[int, int]]:
    """Join overlapping or space-adjacent spans into the runs they cover."""
    runs: list[tuple[int, int]] = []
    for span in sorted(spans, key=lambda item: item.start):
        if runs and span.start <= runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], max(runs[-1][1], span.end))
        else:
            runs.append((span.start, span.end))
    return [(start, end) for start, end in runs if text[start:end].strip()]


def _best_reading(ask: Ask, amendment_change: TextChange) -> _Reading:
    readings = [
        _Reading(
            change,
            score_pair(
                ScoreRequest(
                    amendment=amendment_change,
                    submission=TextChange(old=change.old or "", new=change.new),
                )
            ),
        )
        for change in read_changes(ask.span.text)
    ]
    return max(readings, key=lambda reading: reading.result.score)


def _amendment_spans(amendment: Amendment, result: ScoreResult) -> tuple[SourceSpan, ...]:
    spans: list[SourceSpan] = []
    sources: tuple[tuple[Operation, SpanField, str], ...] = (
        ("insert", "new_text", amendment.new_text),
        ("delete", "old_text", amendment.old_text or ""),
    )
    for operation, field, text in sources:
        matched = [item.amendment for item in result.evidence if item.operation == operation]
        spans.extend(
            SourceSpan(
                record_id=amendment.amendment_id,
                field=field,
                start=start,
                end=end,
                text=text[start:end],
            )
            for start, end in _merge(matched, text)
        )
    return tuple(spans)


def _ask_spans(ask: Ask, reading: _Reading) -> tuple[SourceSpan, ...]:
    """The instruction itself, or the shared words located inside the ask's own quotation."""
    base = ask.span.start
    if reading.change.kind != "statement":
        return (
            SourceSpan(
                record_id=ask.span.record_id,
                field=ask.span.field,
                start=base + reading.change.start,
                end=base + reading.change.end,
                text=reading.change.text,
            ),
        )
    shift = base + reading.change.start
    return tuple(
        SourceSpan(
            record_id=ask.span.record_id,
            field=ask.span.field,
            start=shift + start,
            end=shift + end,
            text=reading.change.new[start:end],
        )
        for start, end in _merge(
            (item.submission for item in reading.result.evidence), reading.change.new
        )
    )


def _tier(score: float, *, short_edit: bool, same_direction: bool) -> LinkTier | None:
    if score >= COPIED_THRESHOLD and not short_edit:
        return "copied"
    if score >= REWORDED_THRESHOLD and not short_edit:
        return "reworded"
    return "same_direction" if same_direction and score > 0 else None


def assess_link(
    amendment: Amendment,
    ask: Ask,
    ask_source_text: str,
    *,
    candidate_id: str | None = None,
    publishable: frozenset[LinkTier] = DEFAULT_PUBLISHABLE,
) -> LinkAssessment:
    """Judge whether `ask` supports `amendment`, with signals, quotations and limitations.

    `ask_source_text` is the document the ask was quoted from, so the ask's quotation can be
    checked against it. Contradicted wins over everything; a link that is not publishable
    for another reason stays "unconfirmed" with the reason in `limitations`.
    """
    amendment_change = TextChange(old=amendment.old_text or "", new=amendment.new_text)
    reading = _best_reading(ask, amendment_change)
    result = reading.result
    spans = (*result.amendment_changes,)
    direction = amendment_direction(spans)
    same_direction = ask.direction == direction and direction != "unknown"
    conflict = result.negation_conflict or _OPPOSITE.get(direction) == ask.direction
    short_edit = sum(len(span.text.split()) for span in spans) < SHORT_EDIT_TOKENS
    eligibility = _time_eligibility(amendment, ask)
    amendment_spans = _amendment_spans(amendment, result)
    ask_spans = _ask_spans(ask, reading)

    limitations: list[str] = [*result.limitations]
    tier = (
        None
        if conflict
        else _tier(result.score, short_edit=short_edit, same_direction=same_direction)
    )
    if short_edit:
        limitations.append("A short edit cannot pass the copied or reworded tier on words alone.")
    if conflict:
        limitations.append("The ask and the amendment pull in opposite directions.")
    if eligibility != "ask_first":
        limitations.append("The ask is not dated before the amendment, so it cannot be an origin.")
    if amendment.old_text is None:
        limitations.append("The original wording is unknown, so the whole proposed text was used.")
    quotes_valid = (
        span_matches(ask.span, ask_source_text)
        and bool(amendment_spans)
        and bool(ask_spans)
        and all(span_matches(span, ask_source_text) for span in ask_spans)
    )
    if not quotes_valid:
        limitations.append("A quotation could not be located exactly in its source.")

    status: LinkStatus
    if conflict:
        status = "contradicted"
    elif tier is None:
        status = "insufficient_evidence"
    elif (
        tier in publishable
        and eligibility == "ask_first"
        and amendment.old_text is not None
        and quotes_valid
    ):
        status = "published"
    else:
        status = "unconfirmed"
    return LinkAssessment(
        link_id=f"link:{id_part(ask.ask_id)}:{id_part(amendment.amendment_id)}",
        procedure_id=amendment.procedure_id,
        candidate_id=candidate_id,
        amendment_id=amendment.amendment_id,
        ask_id=ask.ask_id,
        status=status,
        tier=tier,
        support_score=0.0 if conflict else result.score,
        signals={
            "lexical_overlap": result.score,
            "polarity_conflict": float(conflict),
            "same_direction": float(same_direction),
            "short_edit": float(short_edit),
        },
        amendment_spans=amendment_spans,
        ask_spans=ask_spans if quotes_valid else (),
        time_eligibility=eligibility,
        method=METHOD,
        method_revision=METHOD_REVISION,
        limitations=tuple(limitations),
    )
