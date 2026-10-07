"""Existing bounded passage extraction and BM25 shortlist for lineage's optional Jev path.

These helpers retain their input bounds, direction cues, ordering and candidate IDs from
before the ask-first analytical pipeline was retired. They do not publish or score links.
"""

from collections.abc import Iterable, Sequence

from pydantic import ValidationError

from influence.schemas.atlas import Amendment, Ask, Candidate, Direction, Passage, id_part
from influence.schemas.retrieval import SourcePassage
from influence.schemas.scoring import ChangeSpan, TextChange
from influence.services.passage_change import read_changes
from influence.services.retrieval import PassageIndex
from influence.services.scoring import changed_spans

ASK_METHOD = "passage-v0"
CANDIDATES_PER_AMENDMENT = 5
_STRICTER_WORDS = frozenset({"shall", "must", "required", "least", "minimum"})
_WEAKER_WORDS = frozenset({"may", "can", "optional"})


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
    words go through `amendment_direction`. Prose states no change:
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


def asks_from_passages(passages: Iterable[Passage]) -> tuple[Ask, ...]:
    """One ask per passage, quoting the passage whole: the stand-in for ask extraction.

    The direction is read from the passage's quoted instructions (`requested_direction`),
    and remains unknown for a prose passage.
    """
    return tuple(
        Ask(
            ask_id=f"ask:{id_part(passage.passage_id)}",
            procedure_id=passage.procedure_id,
            actor_id=passage.actor_id,
            document_id=passage.document_id,
            passage_id=passage.passage_id,
            span=passage.span,
            submitted_at=passage.submitted_at,
            language=passage.language,
            direction=requested_direction(passage.span.text),
            extraction_method=ASK_METHOD,
        )
        for passage in passages
    )


def find_candidates(
    amendments: Iterable[Amendment],
    asks: Sequence[Ask],
    unsearchable: list[str] | None = None,
    *,
    unsearchable_asks: dict[str, str] | None = None,
) -> tuple[Candidate, ...]:
    """The top BM25 asks for each amendment's changed words.

    An amendment the scorer's bounds refuse (over 800 tokens a side, as a long recital can
    be, or no text), or whose change leaves no word to search (case or punctuation only),
    has no candidates; its ID is appended to `unsearchable` so the view can say so, instead
    of one long amendment stopping a whole law.

    Unsupported asks are excluded before indexing so they cannot consume the shortlist.
    Their IDs/reasons are recorded in unsearchable_asks, never their truncated replacements.

    Building the index is linear in the asks' total length; each search costs the postings
    of the amendment's distinct changed words plus O(M log k) over M matching passages.
    """
    searchable: list[Ask] = []
    for ask in asks:
        if reason := ask_limit_reason(ask):
            if unsearchable_asks is not None:
                unsearchable_asks[ask.ask_id] = reason
        else:
            searchable.append(ask)
    index = PassageIndex(
        tuple(
            SourcePassage(
                document_id=ask.document_id,
                start=ask.span.start,
                end=ask.span.end,
                text=ask.span.text,
            )
            for ask in searchable
        )
    )
    by_slice = {(ask.document_id, ask.span.start, ask.span.end): ask for ask in searchable}
    found: list[Candidate] = []
    for amendment in amendments:
        try:
            shortlist = index.search(
                amendment.amendment_id,
                amendment.old_text,
                amendment.new_text,
                k=CANDIDATES_PER_AMENDMENT,
            )
        except ValueError:
            if unsearchable is not None:
                unsearchable.append(amendment.amendment_id)
            continue
        if not shortlist.query_terms:
            # A change of case or punctuation only leaves no word to search for.
            if unsearchable is not None:
                unsearchable.append(amendment.amendment_id)
            continue
        for candidate in shortlist.candidates:
            passage = candidate.passage
            ask = by_slice[(passage.document_id, passage.start, passage.end)]
            found.append(
                Candidate(
                    candidate_id=f"cand:{id_part(amendment.amendment_id)}:{id_part(ask.ask_id)}",
                    procedure_id=amendment.procedure_id,
                    amendment_id=amendment.amendment_id,
                    ask_id=ask.ask_id,
                    lexical_rank=candidate.rank,
                    retrieval_score=candidate.score,
                    method=shortlist.method,
                )
            )
    return tuple(found)
