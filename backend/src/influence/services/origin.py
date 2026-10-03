"""Lineage, origin: which submitted documents say the wording that reached the final law.

Given the adopted phrases (runs of at least `MIN_ADOPTED_RUN_WORDS` words that stand in the
final act, are absent from the Commission's proposal, and were inserted by an amendment),
this finds the submissions (Have Your Say comments and their PDF attachments) that contain
the same run, quotes it exactly, and compares the document's date with the date the
amendments carrying it were tabled.

A shared run is evidence of shared wording, not of authorship: the same text can come from a
common draft, a coalition or a quotation of another act. So the result states what it can
check (an exact span, the dates, whether the run is a citation, which amendments carry it)
and nothing more. An undated document is never reported as coming before an amendment.

Complexity: the index holds one entry per 8-word window of every phrase; each document is
scanned once, and a window is built only where its first word starts some indexed window, so
the cost is linear in the documents' words plus the matched windows. The 259 AI Act
attachments (about 2 million words) scan in a few seconds.
"""

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date

from influence.schemas.atlas import (
    Actor,
    Amendment,
    DocumentText,
    Passage,
    SourceDocument,
    SourceSpan,
)
from influence.schemas.lineage import (
    MIN_ADOPTED_RUN_WORDS,
    NGRAM_WORDS,
    AdoptedPhrase,
    AmendmentAdoption,
    OriginMatch,
)
from influence.services.prose_match import Word, words_of

# The first words of a run that quotes another act: "the European Parliament and of the
# Council of 20 May 2021 ...", "Regulation (EU) 2016/679 ...", "Directive 2013/36/EU ...".
# Punctuation is gone after folding, so "(EU)" is the word "eu".
_CITATION_START = re.compile(
    r"^(?:the )?(?:european parliament and of the council"
    r"|(?:commission |council )?(?:implementing |delegated )?(?:regulation|directive|decision)"
    r" (?:eu |ec |eec )?\d"
    r"|(?:regulation|directive|decision) (?:eu|ec|eec)\b"
    r"|official journal|oj l)"
)
_CITATION_ENACTED = "of the european parliament and of the council of"
# A run can start in the middle of a citation ("... and repealing Council Directives
# 90/385/EEC and 93/42/EEC (OJ L ..."), so these markers count anywhere in it.
_CITATION_ANYWHERE = re.compile(
    r"\b(?:oj l|official journal"
    r"|repealing (?:council |commission )?(?:directive|regulation|decision)s?)\b"
)
_CITATION_WINDOW_WORDS = 14
# A phrase carried by amendments of this many different political groups is coalition
# wording rather than one group's request.
COALITION_GROUPS = 3


class OriginError(ValueError):
    """The inputs contradict each other: a phrase no amendment carries, or a mismatched text."""


def _windows(words: Sequence[str]) -> Iterable[tuple[int, tuple[str, ...]]]:
    for start in range(len(words) - NGRAM_WORDS + 1):
        yield start, tuple(words[start : start + NGRAM_WORDS])


def is_citation(run_words: Sequence[str]) -> bool:
    """True when a run is a reference to another act rather than a request.

    It starts as one (checked on the first words only, so a request that merely mentions a
    regulation later is not discarded), or it holds a marker that only a citation has, such
    as "OJ L" or "repealing Council Directives".
    """
    head = " ".join(run_words[:_CITATION_WINDOW_WORDS])
    return (
        bool(_CITATION_START.match(head))
        or _CITATION_ENACTED in head
        or bool(_CITATION_ANYWHERE.search(" ".join(run_words)))
    )


def submitters_from(passages: Iterable[Passage], actors: Iterable[Actor]) -> dict[str, Actor]:
    """Document ID to the actor that submitted it, from the passages cut out of it.

    A passage names its actor; an actor missing from the table (an unresolved name) is left
    out, so that document keeps no organisation instead of a wrong one.
    """
    by_id = {actor.actor_id: actor for actor in actors}
    found: dict[str, Actor] = {}
    for passage in passages:
        actor = by_id.get(passage.actor_id)
        if actor is not None:
            found.setdefault(passage.document_id, actor)
    return found


def coalition_phrase_ids(
    adoptions: Iterable[AmendmentAdoption],
    group_of: Mapping[str, str],
    *,
    minimum: int = COALITION_GROUPS,
) -> frozenset[str]:
    """Phrases carried by amendments of at least `minimum` different political groups.

    An author with no known group counts for none, and committee text has no author, so it
    counts for no group either.
    """
    groups: defaultdict[str, set[str]] = defaultdict(set)
    for adoption in adoptions:
        if adoption.kind != "verbatim":
            continue
        known = {group_of[author] for author in adoption.author_ids if author in group_of}
        for phrase_id in adoption.phrase_ids:
            groups[phrase_id] |= known
    return frozenset(phrase_id for phrase_id, found in groups.items() if len(found) >= minimum)


def _carriers(
    phrases: Sequence[AdoptedPhrase], adoptions: Iterable[AmendmentAdoption]
) -> dict[str, list[AmendmentAdoption]]:
    carried: defaultdict[str, list[AmendmentAdoption]] = defaultdict(list)
    for adoption in adoptions:
        if adoption.kind == "verbatim":
            for phrase_id in adoption.phrase_ids:
                carried[phrase_id].append(adoption)
    for phrase in phrases:
        if phrase.phrase_id not in carried:
            raise OriginError(f"{phrase.phrase_id} is carried by no amendment")
    return carried


def _runs(
    folded: Sequence[str],
    index: Mapping[tuple[str, ...], Sequence[tuple[int, int]]],
    first_words: frozenset[str],
) -> dict[int, tuple[int, int]]:
    """For each phrase found in the document, its longest run as (first word, end word)."""
    hits: defaultdict[tuple[int, int], list[int]] = defaultdict(list)
    for start in range(len(folded) - NGRAM_WORDS + 1):
        if folded[start] not in first_words:
            continue
        for phrase_index, phrase_start in index.get(tuple(folded[start : start + NGRAM_WORDS]), ()):
            hits[phrase_index, start - phrase_start].append(start)
    best: dict[int, tuple[int, int]] = {}
    for (phrase_index, _), starts in hits.items():
        first = previous = starts[0]
        for start in (*starts[1:], None):
            if start is not None and start == previous + 1:
                previous = start
                continue
            end = previous + NGRAM_WORDS
            if end - first >= MIN_ADOPTED_RUN_WORDS:
                current = best.get(phrase_index)
                if current is None or end - first > current[1] - current[0]:
                    best[phrase_index] = (first, end)
            if start is not None:
                first = previous = start
    return best


def _span(
    document: SourceDocument, text: str, words: Sequence[Word], first: int, end: int
) -> SourceSpan:
    start, stop = words[first].start, words[end - 1].end
    return SourceSpan(record_id=document.document_id, start=start, end=stop, text=text[start:stop])


def find_origins(
    phrases: Sequence[AdoptedPhrase],
    adoptions: Sequence[AmendmentAdoption],
    documents: Sequence[tuple[SourceDocument, DocumentText]],
    *,
    amendments: Mapping[str, Amendment] | None = None,
    submitters: Mapping[str, Actor] | None = None,
    proposal_texts: Iterable[str] = (),
) -> tuple[OriginMatch, ...]:
    """Every document that says an adopted phrase, with an exact quotation and the dates.

    For each (phrase, document) pair the longest shared run of at least
    `MIN_ADOPTED_RUN_WORDS` words is reported once. `precedes` is True when the document is
    dated before the earliest amendment carrying the phrase, False when not, and None when
    either date is unknown. `is_citation` marks a run that starts as a reference to another
    act, or that holds a window of the Commission's proposal (`proposal_texts`).
    `amendments` supplies a tabling date for an adoption that has none. `submitters` (see
    `submitters_from`) names the organisation behind a document; without
    it a comment is named by its title and an attachment is left unnamed. Output is ordered
    longest first, then by document and phrase, so it is reproducible.
    """
    verbatim = [phrase for phrase in phrases if phrase.kind == "verbatim"]
    carriers = _carriers(verbatim, adoptions)
    index: defaultdict[tuple[str, ...], list[tuple[int, int]]] = defaultdict(list)
    for phrase_index, phrase in enumerate(verbatim):
        for start, window in _windows(phrase.text.split()):
            index[window].append((phrase_index, start))
    first_words = frozenset(window[0] for window in index)
    proposal: set[tuple[str, ...]] = set()
    for proposal_text in proposal_texts:
        proposal |= {window for _, window in _windows([w.text for w in words_of(proposal_text)])}

    found: list[OriginMatch] = []
    for document, text in documents:
        if document.document_id != text.document_id:
            raise OriginError(
                f"Text of {text.document_id} does not belong to {document.document_id}"
            )
        words = words_of(text.text)
        folded = [word.text for word in words]
        submitter = (submitters or {}).get(document.document_id)
        for phrase_index, (first, end) in _runs(folded, index, first_words).items():
            phrase = verbatim[phrase_index]
            carrying = carriers[phrase.phrase_id]
            dates = [d for d in (_tabled(a, amendments) for a in carrying) if d is not None]
            earliest = min(dates) if dates else None
            published = document.published_at
            run = folded[first:end]
            found.append(
                OriginMatch(
                    phrase_id=phrase.phrase_id,
                    document_id=document.document_id,
                    actor_id=None if submitter is None else submitter.actor_id,
                    organisation=_organisation(document, submitter),
                    published_at=published,
                    span=_span(document, text.text, words, first, end),
                    words=end - first,
                    amendment_ids=tuple(sorted({a.amendment_id for a in carrying})),
                    earliest_amendment_on=earliest,
                    precedes=None
                    if published is None or earliest is None
                    else published.date() < earliest,
                    is_citation=is_citation(run)
                    or any(window in proposal for _, window in _windows(run)),
                )
            )
    return tuple(sorted(found, key=lambda m: (-m.words, m.document_id, m.phrase_id)))


def _organisation(document: SourceDocument, submitter: Actor | None) -> str | None:
    """The organisation's name; a citizen is never named, and an attachment's title is a file."""
    if submitter is not None:
        return None if submitter.kind == "citizens" else submitter.name
    return document.title if document.source_kind == "hys_feedback" else None


def _tabled(adoption: AmendmentAdoption, amendments: Mapping[str, Amendment] | None) -> date | None:
    if adoption.tabled_on is not None or amendments is None:
        return adoption.tabled_on
    amendment = amendments.get(adoption.amendment_id)
    return None if amendment is None else amendment.tabled_on
