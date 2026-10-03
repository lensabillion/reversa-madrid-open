"""Part 4, verify links: judge one candidate (an amendment and an ask) from explicit signals.

Every rule here is a readable lexical rule with a threshold that is a placeholder: no
calibration exists yet (the practice loop sets and freezes them, `rev-zzur`), so the output
carries a support score and the method, never a probability. A link is published only when
the ask was dated before the amendment, the original wording is known, the quoted spans
match their sources exactly, and the evidence tier is one the caller allows. Linear in the
text length; the scorer's token diff is O(n*m) at 800 tokens per side.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from pydantic import ValidationError

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
from influence.services.masking import QuotedLaw
from influence.services.passage_change import read_changes
from influence.services.prose_match import (
    ProseMatch,
    Word,
    match_prose,
    negation_conflict,
    words_of,
)
from influence.services.scoring import changed_spans, score_pair

METHOD = "lexical-rules"
METHOD_REVISION = "rules-4"
# Proposed by the LobbyPlag calibration (PR #40, evaluation/link-calibration.json): the least
# lexical score whose held-out precision, with a Wilson 95% lower bound, clears each tier's
# floor on practice data. Proposals, not frozen values: the practice loop owner freezes them
# before the blind audit. On that data the copied tier held (35 of 36 correct); the reworded
# tier did not reach its floor (36 of 50, 0.72 against 0.80), so it is labelled but not
# published until an audit shows otherwise. Weak negatives, one law, mostly verbatim copies.
COPIED_THRESHOLD = 0.75
REWORDED_THRESHOLD = 0.32
SHORT_EDIT_TOKENS = 3
# Prose passages (no quoted instruction) are judged on shared phrases, not edit overlap. These
# are placeholders: no prose labels exist yet, and the blind audit is what will set them. A
# copy is a long verbatim run covering most of the changed words; a rewording is most of the
# changed words in shorter runs.
PROSE_COPIED_RUN_WORDS = 6
PROSE_COPIED_COVERAGE = 0.8
PROSE_REWORDED_RUN_WORDS = 4
PROSE_REWORDED_COVERAGE = 0.5
# The shared phrases must also carry this much rarity in absolute terms (the sum of their
# words' inverse document frequencies), so a short insertion made only of the law's own
# vocabulary ("before being placed on the market") cannot score as a full copy.
PROSE_MIN_WEIGHT = 0.0
# Break words stop a shared run crossing a gap: between an amendment's separate insertions,
# and where a proposal quotation was masked out of a passage. They differ so that a break on
# one side can never match a break on the other.
_BREAK = "\x00"
_PASSAGE_BREAK = "\x01"
DEFAULT_PUBLISHABLE: frozenset[LinkTier] = frozenset({"copied"})

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


def requested_direction(text: str) -> Direction:
    """The direction an ask's quoted instructions request, read like an amendment's change.

    A quoted instruction ("replace 'may' with 'shall'") states its change, so its changed
    words go through `amendment_direction`, the rule the calibration applied to LobbyPlag's
    submissions (`practice/calibrate.py`, its direction features). Prose states no change:
    counting cues over an argued passage reads "should not be required" as stricter, so
    prose stays unknown until a reader is measured on labelled prose. An instruction past
    the scorer's bounds is unknown too; `ask_limit_reason` reports it and it is never
    assessed. Several instructions are read together, as an amendment's several spans are.
    """
    instructions = [change for change in read_changes(text) if change.kind != "statement"]
    try:
        changes = [TextChange(old=change.old or "", new=change.new) for change in instructions]
    except ValidationError:
        return "unknown"
    return amendment_direction(span for change in changes for span in changed_spans(change))


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


def ask_limit_reason(ask: Ask) -> str | None:
    """Check the exact parsed inputs the scorer will receive, without changing source text.

    A passage's whitespace-word count misses punctuation-heavy PDF tables of contents.
    Reuse TextChange's token/character bounds for every reading, including replacements
    and deletions. One unsupported reading makes the whole ask explicitly unassessed;
    choosing only its convenient bounded readings would silently discard part of the ask.
    """
    readings = read_changes(ask.span.text)
    if not readings:
        return "The ask has no non-whitespace statement or quoted instruction to assess."
    try:
        for change in readings:
            TextChange(old=change.old or "", new=change.new)
    except ValidationError as error:
        # Omit input text from the error: the source is retained under its original ID.
        reasons = "; ".join(
            item["msg"] for item in error.errors(include_input=False, include_context=False)
        )
        return f"The ask exceeds the scorer's input bounds: {reasons}"
    return None


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
    """The quoted instruction itself, located inside the ask's own quotation."""
    base = ask.span.start
    return (
        SourceSpan(
            record_id=ask.span.record_id,
            field=ask.span.field,
            start=base + reading.change.start,
            end=base + reading.change.end,
            text=reading.change.text,
        ),
    )


@dataclass(frozen=True, slots=True)
class _Prose:
    """What the amendment's changed words share with a prose passage, with exact quotations."""

    match: ProseMatch
    amendment_spans: tuple[SourceSpan, ...]
    ask_spans: tuple[SourceSpan, ...]
    negation: bool
    # Characters of proposal quotation masked out of the passage; None when not masked.
    masked_chars: int | None


def _amendment_words(amendment: Amendment, spans: Iterable[ChangeSpan]) -> list[Word]:
    """Inserted words, offsets in `new_text`; a break word between spans stops a run crossing."""
    flat: list[Word] = []
    for span in spans:
        if span.operation != "insert":
            continue
        if flat:
            flat.append(Word(_BREAK, flat[-1].end, flat[-1].end))
        flat.extend(
            Word(word.text, span.start + word.start, span.start + word.end)
            for word in words_of(span.text)
        )
    return flat


def _passage_words(text: str, quoted_law: QuotedLaw) -> tuple[list[Word], int]:
    """Words outside proposal quotations, offsets in `text`, a break word at each masked gap.

    Masking blanks the quotation in place, so the remaining words keep their offsets and
    every quotation is still read from the original text. Also returns the masked length.
    """
    masked = quoted_law.mask(text)
    gaps = iter(masked.spans)
    gap = next(gaps, None)
    flat: list[Word] = []
    for word in words_of(masked.text):
        while gap is not None and gap[1] <= word.start:
            if flat:
                flat.append(Word(_PASSAGE_BREAK, flat[-1].end, flat[-1].end))
            gap = next(gaps, None)
        flat.append(word)
    return flat, sum(end - start for start, end in masked.spans)


def _prose(
    amendment: Amendment,
    ask: Ask,
    change: PassageChange,
    spans: Iterable[ChangeSpan],
    rarity: Mapping[str, float] | None,
    quoted_law: QuotedLaw | None,
) -> _Prose:
    mine = _amendment_words(amendment, spans)
    if quoted_law is None:
        theirs, masked_chars = list(words_of(change.new)), None
    else:
        theirs, masked_chars = _passage_words(change.new, quoted_law)
    match = match_prose([w.text for w in mine], [w.text for w in theirs], rarity)
    shift = ask.span.start + change.start
    amendment_spans = tuple(
        SourceSpan(
            record_id=amendment.amendment_id,
            field="new_text",
            start=mine[run.amendment_first].start,
            end=mine[run.amendment_first + run.length - 1].end,
            text=amendment.new_text[
                mine[run.amendment_first].start : mine[run.amendment_first + run.length - 1].end
            ],
        )
        for run in match.runs
    )
    ask_spans = tuple(
        SourceSpan(
            record_id=ask.span.record_id,
            field=ask.span.field,
            start=shift + theirs[run.passage_first].start,
            end=shift + theirs[run.passage_first + run.length - 1].end,
            text=change.new[
                theirs[run.passage_first].start : theirs[run.passage_first + run.length - 1].end
            ],
        )
        for run in match.runs
    )
    negation = any(
        negation_conflict(
            amendment.new_text,
            mine[run.amendment_first].start,
            change.new,
            theirs[run.passage_first].start,
        )
        for run in match.runs
    )
    return _Prose(match, amendment_spans, ask_spans, negation, masked_chars)


def _prose_tier(
    match: ProseMatch, *, short_edit: bool, same_direction: bool, min_weight: float
) -> LinkTier | None:
    if not short_edit and match.shared_weight >= min_weight:
        if match.longest >= PROSE_COPIED_RUN_WORDS and match.coverage >= PROSE_COPIED_COVERAGE:
            return "copied"
        if match.longest >= PROSE_REWORDED_RUN_WORDS and match.coverage >= PROSE_REWORDED_COVERAGE:
            return "reworded"
    return "same_direction" if same_direction and match.runs else None


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
    rarity: Mapping[str, float] | None = None,
    publish_prose: bool = False,
    quoted_law: QuotedLaw | None = None,
) -> LinkAssessment:
    """Judge whether `ask` supports `amendment`, with signals, quotations and limitations.

    `ask_source_text` is the document the ask was quoted from, so the ask's quotation can be
    checked against it. Contradicted wins over everything; a link that is not publishable
    for another reason stays "unconfirmed" with the reason in `limitations`.

    A passage that gives a quoted instruction ("replace 'shall' with 'may'") is compared as an
    edit. Any other passage is prose and is compared as shared phrases (`prose_match`), with
    `rarity` (inverse document frequency over the law's passages, `rarity_weights`) so
    boilerplate counts for little; with no table every word weighs the same. With
    `quoted_law`, wording the passage quotes from the proposal (8 words or more) is masked
    out first: an amendment may reuse the proposal's own wording, and a passage quoting the
    proposal has not asked for it. Without it nothing is masked, and the caller says why.

    A shared-phrase match on prose is never published unless `publish_prose` is set: on the
    AI Act the 7 links it published were all the law's own boilerplate, and no threshold
    separates that from real copying without labels. It stays "unconfirmed" until the meaning
    judge or the blind audit says otherwise.
    """
    if reason := ask_limit_reason(ask):
        return LinkAssessment(
            link_id=f"link:{id_part(ask.ask_id)}:{id_part(amendment.amendment_id)}",
            procedure_id=amendment.procedure_id,
            candidate_id=candidate_id,
            amendment_id=amendment.amendment_id,
            ask_id=ask.ask_id,
            status="insufficient_evidence",
            support_score=0.0,
            time_eligibility=_time_eligibility(amendment, ask),
            method=METHOD,
            method_revision=METHOD_REVISION,
            limitations=(reason,),
        )
    amendment_change = TextChange(old=amendment.old_text or "", new=amendment.new_text)
    reading = _best_reading(ask, amendment_change)
    result = reading.result
    spans = (*result.amendment_changes,)
    direction = amendment_direction(spans)
    same_direction = ask.direction == direction and direction != "unknown"
    evidence = (
        _prose(amendment, ask, reading.change, spans, rarity, quoted_law)
        if reading.change.kind == "statement"
        else None
    )
    negation = result.negation_conflict if evidence is None else evidence.negation
    score = result.score if evidence is None else evidence.match.coverage
    opposed = _OPPOSITE.get(direction) == ask.direction
    short_edit = sum(len(span.text.split()) for span in spans) < SHORT_EDIT_TOKENS
    eligibility = _time_eligibility(amendment, ask)
    amendment_spans = (
        _amendment_spans(amendment, result) if evidence is None else evidence.amendment_spans
    )
    ask_spans = _ask_spans(ask, reading) if evidence is None else evidence.ask_spans

    limitations: list[str] = [*result.limitations]
    if evidence is None:
        clean_tier = _tier(score, short_edit=short_edit, same_direction=same_direction)
    else:
        clean_tier = _prose_tier(
            evidence.match,
            short_edit=short_edit,
            same_direction=same_direction,
            min_weight=PROSE_MIN_WEIGHT if rarity is not None else 0.0,
        )
    # A negation cue is only a hint: it contradicts a link when the wording otherwise matches
    # well enough to earn a tier. A weak match with a "not" nearby is just a weak match.
    conflict = opposed or (negation and clean_tier is not None)
    tier = None if conflict else clean_tier
    if short_edit:
        limitations.append("A short edit cannot pass the copied or reworded tier on words alone.")
    if conflict:
        limitations.append("The ask and the amendment pull in opposite directions.")
    if evidence is not None and ask.direction == "unknown":
        limitations.append(
            "The ask is prose with no recorded direction, so the same-direction and "
            "opposite-direction checks did not run."
        )
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
    if evidence is not None and not publish_prose:
        limitations.append(
            "A shared-phrase match on prose is not published: it cannot tell the law's own "
            "wording from copying, and no prose threshold is calibrated yet."
        )

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
        and (evidence is None or publish_prose)
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
        support_score=0.0 if conflict else score,
        signals={
            "lexical_overlap": score,
            "polarity_conflict": float(conflict),
            "same_direction": float(same_direction),
            "short_edit": float(short_edit),
            **(
                {}
                if evidence is None
                else {
                    "longest_shared_run": float(evidence.match.longest),
                    "shared_rarity": evidence.match.shared_weight,
                    **(
                        {}
                        if evidence.masked_chars is None
                        else {"quoted_law_masked_chars": float(evidence.masked_chars)}
                    ),
                }
            ),
        },
        amendment_spans=amendment_spans,
        ask_spans=ask_spans if quotes_valid else (),
        time_eligibility=eligibility,
        method=METHOD,
        method_revision=METHOD_REVISION,
        limitations=tuple(limitations),
    )
