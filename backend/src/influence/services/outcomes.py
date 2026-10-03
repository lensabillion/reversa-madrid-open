"""Part 5, trace outcomes: did the requested wording reach Parliament's text and the final law?

Provisions are aligned by their text, never by article number, because final acts renumber.
The test is the owner's rule of 3 October: an ask is adopted when its requested wording
survives in the aligned provision, labelled automatically. A missing text is unknown, not
a loss, and so is a text where no provision lines up, because failing to find the place is
not proof that the wording did not survive. Linear in the text length, plus one pass over
the provisions of a stage per ask.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from influence.schemas.atlas import (
    Amendment,
    ArticleStage,
    ArticleVersion,
    Ask,
    LinkAssessment,
    Outcome,
    OutcomeKind,
    OutcomeResult,
    OutcomeStage,
    SourceSpan,
    id_part,
)
from influence.schemas.scoring import TOKEN_PATTERN, TextChange
from influence.services.passage_change import read_changes
from influence.services.scoring import changed_spans

METHOD = "text-survival"
# A placeholder: the least token overlap for a provision to count as the same provision.
ALIGNMENT_THRESHOLD = 0.3

_ARTICLE_STAGE: dict[OutcomeStage, ArticleStage] = {
    "parliament_position": "parliament_position",
    "final_act": "final_act",
}
_MISSING_TEXT = {
    "parliament_position": "Parliament's position text was not obtained for this procedure.",
    "final_act": "No final act text: the procedure is still open or the act was not obtained.",
}

type Words = tuple[tuple[str, int, int], ...]


@dataclass(frozen=True, slots=True)
class _Request:
    """What the ask wants in the law: words to appear, words to disappear."""

    inserts: tuple[str, ...]
    deletes: tuple[str, ...]
    whole: str | None
    allow_partial: bool
    probe: str


def _words(text: str) -> Words:
    return tuple(
        (token.group().casefold(), token.start(), token.end())
        for token in TOKEN_PATTERN.finditer(text)
        if any(char.isalnum() for char in token.group())
    )


def _find(haystack: Words, needle: str) -> tuple[int, int] | None:
    """The first place `needle`'s words appear in a row in `haystack`, as text offsets."""
    wanted = [word for word, _, _ in _words(needle)]
    if not wanted:
        return None
    have = [word for word, _, _ in haystack]
    for index in range(len(have) - len(wanted) + 1):
        if have[index : index + len(wanted)] == wanted:
            return haystack[index][1], haystack[index + len(wanted) - 1][2]
    return None


def _overlap(left: Words, right: Words) -> float:
    """Dice overlap of two word sets: 2 * shared / (size of both)."""
    one, other = {word for word, _, _ in left}, {word for word, _, _ in right}
    return 2 * len(one & other) / (len(one) + len(other)) if one and other else 0.0


def _align(versions: Sequence[ArticleVersion], probe: str) -> ArticleVersion | None:
    probe_words = _words(probe)
    scored = [(_overlap(probe_words, _words(version.text)), version) for version in versions]
    best = max(scored, key=lambda item: item[0], default=None)
    return best[1] if best and best[0] >= ALIGNMENT_THRESHOLD else None


def _request(ask: Ask, amendment: Amendment | None) -> _Request:
    if amendment is not None:
        spans = changed_spans(TextChange(old=amendment.old_text or "", new=amendment.new_text))
        return _Request(
            inserts=tuple(span.text for span in spans if span.operation == "insert"),
            deletes=tuple(span.text for span in spans if span.operation == "delete"),
            whole=amendment.new_text if amendment.new_text.strip() else None,
            allow_partial=True,
            probe=amendment.old_text or amendment.new_text,
        )
    (change, *_) = read_changes(ask.span.text) or (None,)
    if change is None or change.kind == "statement":
        text = ask.span.text.strip()
        return _Request(inserts=(text,), deletes=(), whole=text, allow_partial=False, probe=text)
    return _Request(
        inserts=(change.new,) if change.new else (),
        deletes=(change.old,) if change.old else (),
        whole=None,
        allow_partial=False,
        probe=ask.span.text,
    )


def _span(version: ArticleVersion, start: int, end: int) -> SourceSpan:
    return SourceSpan(
        record_id=version.article_id,
        field="text",
        start=start,
        end=end,
        text=version.text[start:end],
    )


def _judge(
    request: _Request, version: ArticleVersion
) -> tuple[OutcomeResult, OutcomeKind | None, tuple[SourceSpan, ...], str | None]:
    """Decide full, partial or not observed for one aligned provision."""
    words = _words(version.text)
    still_present = [text for text in request.deletes if _find(words, text)]
    if not request.inserts:
        if still_present:
            return "not_observed", None, (), "The words the ask wanted removed are still there."
        return "full", "deletion", (_span(version, 0, len(version.text)),), None
    found = [place for text in request.inserts if (place := _find(words, text))]
    whole = _find(words, request.whole) if request.whole else None
    everything = request.whole is None and len(found) == len(request.inserts)
    if (whole or everything) and not still_present:
        place = whole or found[0]
        return "full", "wording", (_span(version, *place),), None
    if found and request.allow_partial:
        reason = "The requested words survive but the wording around them differs."
        if still_present:
            reason = "The requested words survive but words the ask wanted removed remain."
        return "partial", "wording", (_span(version, *found[0]),), reason
    return "not_observed", None, (), "The requested wording is not in the aligned provision."


def _heard(ask: Ask, amendment: Amendment, link: LinkAssessment | None) -> Outcome:
    published = link is not None and link.status == "published"
    kind: OutcomeKind | None = None
    if link is not None and link.tier in ("copied", "reworded"):
        kind = "wording" if link.tier == "copied" else "reworded"
    return Outcome(
        outcome_id=f"outcome:{id_part(ask.ask_id)}:heard",
        procedure_id=ask.procedure_id,
        ask_id=ask.ask_id,
        link_id=link.link_id if published and link else None,
        amendment_id=amendment.amendment_id,
        relation="via_amendment",
        stage="heard",
        result="full" if published else "not_observed",
        kind=kind if published else None,
        spans=link.amendment_spans if published and link else (),
        reason=None if published else "No published link joins this ask to an amendment.",
        method=METHOD,
    )


def _stage_outcome(
    ask: Ask,
    amendment: Amendment | None,
    link: LinkAssessment | None,
    versions: Sequence[ArticleVersion],
    stage: OutcomeStage,
) -> Outcome:
    link_id = link.link_id if link is not None and link.status == "published" else None

    def outcome(
        result: OutcomeResult,
        *,
        article_id: str | None = None,
        kind: OutcomeKind | None = None,
        spans: tuple[SourceSpan, ...] = (),
        reason: str | None = None,
    ) -> Outcome:
        return Outcome(
            outcome_id=f"outcome:{id_part(ask.ask_id)}:{stage}",
            procedure_id=ask.procedure_id,
            ask_id=ask.ask_id,
            link_id=link_id,
            amendment_id=amendment.amendment_id if amendment else None,
            relation="via_amendment" if amendment else "direct_to_final",
            stage=stage,
            result=result,
            kind=kind,
            article_id=article_id,
            spans=spans,
            reason=reason,
            method=METHOD,
        )

    here = [version for version in versions if version.stage == _ARTICLE_STAGE[stage]]
    if not here:
        return outcome("unknown", reason=_MISSING_TEXT[stage])
    request = _request(ask, amendment)
    version = _align(here, request.probe)
    if version is None:
        return outcome(
            "unknown", reason="No provision in this text lines up with the one the ask is about."
        )
    result, kind, spans, reason = _judge(request, version)
    return outcome(result, article_id=version.article_id, kind=kind, spans=spans, reason=reason)


def trace_outcomes(
    ask: Ask,
    amendment: Amendment | None,
    link: LinkAssessment | None,
    versions: Sequence[ArticleVersion],
) -> tuple[Outcome, ...]:
    """Outcomes of one ask at each stage it can be observed.

    With an amendment: heard, Parliament's position and the final act, each separate. Without
    one, only the final act, as a direct ask-to-final relation. An amendment counts only when
    the link to it is published or unconfirmed and the ask came first: otherwise the ask is
    not that amendment's origin, so it is traced on its own wording instead of inheriting the
    amendment's win. `versions` holds the provisions of every stage.
    """
    if (
        link is None
        or link.status in ("contradicted", "insufficient_evidence")
        or link.time_eligibility != "ask_first"
    ):
        amendment = None
    if amendment is None:
        return (_stage_outcome(ask, None, None, versions, "final_act"),)
    return (
        _heard(ask, amendment, link),
        _stage_outcome(ask, amendment, link, versions, "parliament_position"),
        _stage_outcome(ask, amendment, link, versions, "final_act"),
    )


def outcome_result(outcomes: Sequence[Outcome], stage: OutcomeStage) -> OutcomeResult | None:
    """The result recorded for `stage`, or None when that stage was not assessed."""
    return next((item.result for item in outcomes if item.stage == stage), None)
