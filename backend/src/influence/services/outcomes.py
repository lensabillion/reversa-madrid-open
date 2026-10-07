"""Part 5, trace outcomes: did the requested wording reach Parliament's text and the final law?

Provisions are aligned by their text, never by article number, because final acts renumber.
The test is the owner's rule of 3 October: an ask is adopted when its requested wording
survives in the aligned provision, labelled automatically. A missing text is unknown, not
a loss, and so is a text where no provision lines up, because failing to find the place is
not proof that the wording did not survive. An amendment's changed words are looked for
with their unchanged neighbours, so a common word such as "shall" elsewhere in the provision
neither counts as the requested wording nor as the old wording left in place.

Tokenised provisions are memoised by their text, so one law's provisions are tokenised once
however many asks are traced; each ask then costs one set intersection per provision of a
stage plus a linear scan of the aligned provision.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache

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
# The least overlap for a provision an amendment deleted to count as still in the text.
STILL_PRESENT_THRESHOLD = 0.8
# Parltrack writes a whole-provision deletion as one of these new texts. The same set as
# `direction.DELETION_MARKERS`, repeated because `direction` imports the pipeline.
DELETION_MARKERS = frozenset({"", "deleted", "(deleted)"})
# Distinct texts kept tokenised: more than the provisions of one law at every stage.
_CACHE_SIZE = 16_384

_ARTICLE_STAGE: dict[OutcomeStage, ArticleStage] = {
    "parliament_position": "parliament_position",
    "final_act": "final_act",
}
_MISSING_TEXT = {
    "parliament_position": "Parliament's position text was not obtained for this procedure.",
    "final_act": "No final act text: the procedure is still open or the act was not obtained.",
}
_NO_REQUEST = "No requested wording extracted to look for in this text."
_UNCONFIRMED = "The link is unconfirmed, so whether the ask was heard is not assessed."
_DELETION_LIKELY = (
    "Deletion likely achieved: no provision in this text lines up with the one the ask "
    "wanted deleted. An absence cannot be quoted, so it is not counted as a win."
)
_DELETION_UNCLEAR = (
    "A provision like the one the ask wanted deleted is here but was rewritten, so whether "
    "the deletion was achieved cannot be told."
)

type Words = tuple[tuple[str, int, int], ...]


@dataclass(frozen=True, slots=True)
class _Request:
    """What the ask wants in the law: words to appear, words to disappear.

    `deletes_provision` marks an amendment that deletes its whole provision. It is judged by
    whether a provision like `probe` is still in the text, not by looking for words.
    """

    inserts: tuple[str, ...]
    deletes: tuple[str, ...]
    whole: str | None
    allow_partial: bool
    probe: str
    deletes_provision: bool = False
    statement: bool = False


@lru_cache(maxsize=_CACHE_SIZE)
def _words(text: str) -> Words:
    return tuple(
        (token.group().casefold(), token.start(), token.end())
        for token in TOKEN_PATTERN.finditer(text)
        if any(char.isalnum() for char in token.group())
    )


@lru_cache(maxsize=_CACHE_SIZE)
def _word_set(text: str) -> frozenset[str]:
    return frozenset(word for word, _, _ in _words(text))


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


def _overlap(one: frozenset[str], other: frozenset[str]) -> float:
    """Dice overlap of two word sets: 2 * shared / (size of both)."""
    return 2 * len(one & other) / (len(one) + len(other)) if one and other else 0.0


def _best(versions: Sequence[ArticleVersion], probe: str) -> tuple[ArticleVersion | None, float]:
    """The provision whose words overlap `probe` most, and that overlap; ties keep the first."""
    probe_words = _word_set(probe)
    best: ArticleVersion | None = None
    best_score = 0.0
    for version in versions:
        score = _overlap(probe_words, _word_set(version.text))
        if best is None or score > best_score:
            best, best_score = version, score
    return best, best_score


def _align(versions: Sequence[ArticleVersion], probe: str) -> ArticleVersion | None:
    best, score = _best(versions, probe)
    return best if score >= ALIGNMENT_THRESHOLD else None


def _anchored(text: str, start: int, end: int) -> str:
    """`text[start:end]` widened to the nearest word on each side: its place in the text.

    A bare one-word fragment such as "shall" matches anywhere in a provision; with its
    unchanged neighbours it matches only where the amendment put it. A fragment with no
    word of its own comes back as it is, so it never matches.
    """
    if not _words(text[start:end]):
        return text[start:end]
    words = _words(text)
    left = max((first for _, first, last in words if last <= start), default=start)
    right = min((last for _, first, last in words if first >= end), default=end)
    return text[left:right]


def _request(ask: Ask, amendment: Amendment | None) -> _Request | None:
    """What to look for, or None when the ask names no wording to look for."""
    if amendment is not None:
        old = amendment.old_text or ""
        if amendment.new_text.strip().casefold() in DELETION_MARKERS:
            if not old.strip():
                return None
            return _Request((), (), None, False, old, deletes_provision=True)
        new = amendment.new_text
        spans = changed_spans(TextChange(old=old, new=new))
        return _Request(
            inserts=tuple(
                _anchored(new, span.start, span.end) for span in spans if span.operation == "insert"
            ),
            deletes=tuple(
                _anchored(old, span.start, span.end) for span in spans if span.operation == "delete"
            ),
            whole=new,
            allow_partial=True,
            probe=old or new,
        )
    changes = read_changes(ask.span.text)
    if not changes:
        return None
    if changes[0].kind == "statement":
        text = changes[0].new
        return _Request((text,), (), text, False, text, statement=True)
    return _Request(
        inserts=tuple(change.new for change in changes if change.new),
        deletes=tuple(change.old for change in changes if change.old),
        whole=None,
        allow_partial=len(changes) > 1,
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
    # Removed wording is looked for in its place, so a word it shares with the rest of the
    # provision does not count; a deletion's new text is often a prefix of its old one, so
    # the whole new text alone is no proof.
    still_present = [text for text in request.deletes if _find(words, text)]
    whole = _find(words, request.whole) if request.whole is not None else None
    if whole is not None and not still_present:
        kind: OutcomeKind = "deletion" if request.deletes and not request.inserts else "wording"
        return "full", kind, (_span(version, *whole),), None
    if request.deletes and not request.inserts:
        if still_present:
            return "not_observed", None, (), "The words the ask wanted removed are still there."
        everything = (_span(version, 0, len(version.text)),)
        if request.whole is None:
            return "full", "deletion", everything, None
        reason = "The words the ask wanted removed are gone, but the wording around them changed."
        return "partial", "deletion", everything, reason
    found = [place for text in request.inserts if (place := _find(words, text))]
    if request.whole is None and len(found) == len(request.inserts) and not still_present:
        return "full", "wording", (_span(version, *found[0]),), None
    if found and request.allow_partial:
        reason = "The requested words survive but the wording around them differs."
        if still_present:
            reason = "The requested words survive but words the ask wanted removed remain."
        return "partial", "wording", (_span(version, *found[0]),), reason
    return "not_observed", None, (), "The requested wording is not in the aligned provision."


def _heard(ask: Ask, amendment: Amendment, link: LinkAssessment | None) -> Outcome:
    """Heard when the link is published; an unconfirmed link is unknown, not a loss."""
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
        result="full" if published else "unknown",
        kind=kind if published else None,
        spans=link.amendment_spans if published and link else (),
        reason=None if published else _UNCONFIRMED,
        method=METHOD,
    )


type _Make = Callable[..., Outcome]


def _status_quo(
    ask: Ask,
    versions: Sequence[ArticleVersion],
    here: Sequence[ArticleVersion],
    outcome: _Make,
) -> Outcome:
    """An ask to keep a provision wins when it comes through word for word.

    This is a defence of the status quo, kept apart from winning a change (kind
    "status_quo"): the proposal's provision is found by the ask's own words, then the same
    provision is found at this stage by the proposal's words, and the two are compared.
    """
    before = _align([item for item in versions if item.stage == "proposal"], ask.span.text)
    if before is None:
        return outcome("unknown", reason="No proposal provision lines up with the ask to compare.")
    version = _align(here, before.text)
    if version is None:
        return outcome(
            "unknown", reason="No provision in this text lines up with the one the ask wants kept."
        )
    if [word for word, _, _ in _words(version.text)] == [
        word for word, _, _ in _words(before.text)
    ]:
        return outcome(
            "full",
            article_id=version.article_id,
            kind="status_quo",
            spans=(_span(version, 0, len(version.text)),),
        )
    return outcome(
        "not_observed",
        article_id=version.article_id,
        reason="The provision was changed from the proposal.",
    )


def _provision_deleted(
    request: _Request, here: Sequence[ArticleVersion], outcome: _Make
) -> Outcome:
    """A deleted provision is still there only when a provision matches it closely.

    The success of a deletion is an absence, which has no span to quote, so it stays
    unknown with a reason that says the deletion was likely achieved.
    """
    version, score = _best(here, request.probe)
    if version is None or score < ALIGNMENT_THRESHOLD:
        return outcome("unknown", reason=_DELETION_LIKELY)
    if score < STILL_PRESENT_THRESHOLD:
        return outcome("unknown", article_id=version.article_id, reason=_DELETION_UNCLEAR)
    return outcome(
        "not_observed",
        article_id=version.article_id,
        reason="The provision the ask wanted deleted is still in this text.",
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
    if ask.direction == "keep":
        return _status_quo(ask, versions, here, outcome)
    request = _request(ask, amendment)
    if request is None:
        return outcome("unknown", reason=_NO_REQUEST)
    if request.deletes_provision:
        return _provision_deleted(request, here, outcome)
    version = _align(here, request.probe)
    if version is None:
        return outcome(
            "unknown", reason="No provision in this text lines up with the one the ask is about."
        )
    result, kind, spans, reason = _judge(request, version)
    if request.statement and result != "full":
        # A statement quotes no change. It wins when it survives word for word, but a 40-120
        # word passage almost never does, so anything less says nothing about adoption.
        return outcome("unknown", article_id=version.article_id, reason=_NO_REQUEST)
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
    amendment's win. An ask to keep the text as it is (direction "keep") is never an
    amendment's origin and is judged by whether its provision survived unchanged.
    `versions` holds the provisions of every stage.
    """
    if (
        link is None
        or link.status in ("contradicted", "insufficient_evidence")
        or link.time_eligibility != "ask_first"
        or ask.direction == "keep"
    ):
        amendment = None
    if amendment is None:
        return (_stage_outcome(ask, None, None, versions, "final_act"),)
    return (
        _heard(ask, amendment, link),
        _stage_outcome(ask, amendment, link, versions, "parliament_position"),
        _stage_outcome(ask, amendment, link, versions, "final_act"),
    )
