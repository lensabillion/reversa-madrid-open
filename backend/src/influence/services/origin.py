"""Lineage, origin: which submitted documents say the wording that reached the final law.

Given the adopted phrases (runs of at least `MIN_ADOPTED_RUN_WORDS` words that stand in the
final act, are absent from the Commission's proposal, and were inserted by an amendment),
this finds the submissions (Have Your Say comments and their PDF attachments) that contain
the same run, quotes it exactly, and compares the document's date with the date the
amendments carrying it were tabled.

`find_tabled_origins` does the same for wording that amendments inserted whether or not it was
adopted, so a document can be tied to an amendment that never reached the final act: origin
and adoption are two independent facts (`TabledPhrase`).

A shared run is evidence of shared wording, not of authorship: the same text can come from a
common draft, a coalition or a quotation of another act. So the result states what it can
check (an exact span, the dates, whether the run is a citation, which amendments carry it)
and nothing more. Only consultation documents (`CONSULTATION_KINDS`) are searched, so the
law's own texts never match themselves. A document counts as an origin only when it is dated
before every carrying amendment, so an undated document, or one undated carrier, leaves the
order unknown (`eligibility` "unknown_date").

Complexity: the index holds one entry per 8-word window of every accepted carrier run.
Each document is scanned once, and a window is built only where its first word starts an
indexed window. The cost is linear in document words plus matched windows.
`find_tabled_origins` indexes
every amendment's inserted words instead of the adopted phrases, about one entry per inserted
word (the AI Act's 5,660 amendments insert well under a million), so it scans the same way;
a window that many amendments share costs one lookup per carrier.
"""

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from influence.schemas.atlas import (
    Actor,
    Amendment,
    DocumentText,
    Passage,
    SourceDocument,
    SourceSpan,
    TimeEligibility,
)
from influence.schemas.lineage import (
    MIN_ADOPTED_RUN_WORDS,
    NGRAM_WORDS,
    AdoptedPhrase,
    AdoptionEvidence,
    AmendmentAdoption,
    OriginMatch,
    OriginSupport,
    TabledPhrase,
)
from influence.services.lineage import Rarity, evidence_id_of, inserted_words, phrase_id_of
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
# The documents an organisation or a citizen submitted: Have Your Say feedback and its
# attachments. The law's own texts are never searched for origins.
CONSULTATION_KINDS = frozenset({"hys_feedback", "hys_attachment"})


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
    rarity: Rarity,
    insertions: Sequence[tuple[int, ...]] | None = None,
) -> dict[int, tuple[int, int, int]]:
    """Longest qualifying (document first, end, carrier first) for each indexed run.

    Qualification precedes selection: an earlier or longer overlap without the carrier's
    insertion cannot suppress an actual supported overlap. Window hits are linear in the
    indexed and document words plus matched windows, as in the module's cost description.
    """
    hits: defaultdict[tuple[int, int], list[int]] = defaultdict(list)
    for start in range(len(folded) - NGRAM_WORDS + 1):
        if folded[start] not in first_words:
            continue
        for phrase_index, phrase_start in index.get(tuple(folded[start : start + NGRAM_WORDS]), ()):
            hits[phrase_index, start - phrase_start].append(start)
    best: dict[int, tuple[int, int, int]] = {}
    for (phrase_index, shift), starts in hits.items():
        first = previous = starts[0]
        for start in (*starts[1:], None):
            if start is not None and start == previous + 1:
                previous = start
                continue
            end = previous + NGRAM_WORDS
            if end - first >= MIN_ADOPTED_RUN_WORDS and rarity.significant(folded[first:end]):
                carrier_first = first - shift
                if insertions is None or any(
                    carrier_first <= offset < carrier_first + end - first
                    for offset in insertions[phrase_index]
                ):
                    current = best.get(phrase_index)
                    rank = (-(end - first), first, carrier_first)
                    if current is None or rank < (
                        -(current[1] - current[0]),
                        current[0],
                        current[2],
                    ):
                        best[phrase_index] = (first, end, carrier_first)
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
    rarity: Rarity,
    amendments: Mapping[str, Amendment] | None = None,
    submitters: Mapping[str, Actor] | None = None,
) -> tuple[OriginMatch, ...]:
    """Exact submission/carrier/final associations, with supported carrier dates.

    For each document and accepted carrier occurrence, choose the longest qualifying run
    of at least `MIN_ADOPTED_RUN_WORDS` words with three rare words and an insertion.
    Group only identical phrase/document/submission occurrences, retaining each support.
    Documents that are not consultation documents are skipped.
    `precedes` is True when the document is dated before the earliest amendment carrying the
    phrase, False when not, and None when the document or any carrying amendment is undated;
    `eligibility` records the corresponding date status. `is_citation` marks a run that is a
    reference to another act. An adopted phrase holds no window of the proposal by
    construction, so there is no second test against the proposal here. `amendments`
    supplies a tabling date for an adoption that has none. `submitters` (see
    `submitters_from`) names the organisation behind a document; without it a comment is
    named by its title and an attachment is left unnamed. Output is ordered longest first,
    then by document, phrase and submission offsets, so it is reproducible.
    """
    verbatim = [phrase for phrase in phrases if phrase.kind == "verbatim"]
    carriers = _carriers(verbatim, adoptions)
    listed = {phrase.phrase_id for phrase in verbatim}
    accepted: list[tuple[AmendmentAdoption, AdoptionEvidence]] = []
    for phrase_id in sorted(listed):
        for adoption in carriers[phrase_id]:
            evidence = [item for item in adoption.evidence if item.phrase_id == phrase_id]
            if not evidence:
                raise OriginError(
                    f"{adoption.amendment_id} lacks exact carrier evidence for {phrase_id}"
                )
            for item in evidence:
                if item.amendment_span.record_id != adoption.amendment_id:
                    raise OriginError("Carrier evidence quotes a different amendment")
                source = None if amendments is None else amendments.get(adoption.amendment_id)
                if (
                    source is not None
                    and source.new_text[item.amendment_span.start : item.amendment_span.end]
                    != item.amendment_span.text
                ):
                    raise OriginError(
                        "Carrier evidence does not quote the amendment's exact source"
                    )
                accepted.append((adoption, item))
    accepted.sort(key=lambda pair: pair[1].evidence_id)
    index: defaultdict[tuple[str, ...], list[tuple[int, int]]] = defaultdict(list)
    for target, (_, evidence) in enumerate(accepted):
        for start, window in _windows(
            [word.text for word in words_of(evidence.amendment_span.text)]
        ):
            index[window].append((target, start))
    insertions = [evidence.inserted_word_offsets for _, evidence in accepted]
    first_words = frozenset(window[0] for window in index)

    found: list[OriginMatch] = []
    for document, text in _consultation(documents):
        words = words_of(text.text)
        folded = [word.text for word in words]
        submitter = (submitters or {}).get(document.document_id)
        grouped: defaultdict[tuple[str, SourceSpan], dict[str, OriginSupport]] = defaultdict(dict)
        supporting: dict[str, AmendmentAdoption] = {}
        for target, (first, end, carrier_first) in _runs(
            folded, index, first_words, rarity, insertions
        ).items():
            adoption, evidence = accepted[target]
            submission_span = _span(document, text.text, words, first, end)
            amendment_span = _project(
                evidence.amendment_span, carrier_first, carrier_first + end - first
            )
            final_span = _project(evidence.final_span, carrier_first, carrier_first + end - first)
            support_id = evidence_id_of(
                "origin-support",
                evidence.evidence_id,
                (submission_span, amendment_span, final_span),
            )
            support = OriginSupport(
                support_id=support_id,
                adoption_evidence_id=evidence.evidence_id,
                amendment_id=adoption.amendment_id,
                submission_span=submission_span,
                amendment_span=amendment_span,
                final_span=final_span,
            )
            grouped[evidence.phrase_id, submission_span][support_id] = support
            supporting[adoption.amendment_id] = adoption
        for (phrase_id, span), supports in grouped.items():
            ids = tuple(sorted({support.amendment_id for support in supports.values()}))
            earliest, precedes = _order(
                [_tabled(supporting[amendment_id], amendments) for amendment_id in ids],
                document.published_at,
            )
            run_words = [word.text for word in words_of(span.text)]
            found.append(
                OriginMatch(
                    phrase_id=phrase_id,
                    document_id=document.document_id,
                    actor_id=None if submitter is None else submitter.actor_id,
                    organisation=_organisation(document, submitter),
                    published_at=document.published_at,
                    span=span,
                    words=len(run_words),
                    amendment_ids=ids,
                    earliest_amendment_on=earliest,
                    precedes=precedes,
                    eligibility=_eligibility(precedes),
                    is_citation=is_citation(run_words),
                    supports=tuple(supports[key] for key in sorted(supports)),
                )
            )
    return tuple(
        sorted(
            found,
            key=lambda match: (
                -match.words,
                match.document_id,
                match.phrase_id,
                match.span.start,
                match.span.end,
            ),
        )
    )


def _project(span: SourceSpan, first: int, end: int) -> SourceSpan:
    """Project a matched word interval inside its accepted occurrence, without text search."""
    words = words_of(span.text)
    start, stop = words[first].start, words[end - 1].end
    return SourceSpan(
        record_id=span.record_id,
        field=span.field,
        start=span.start + start,
        end=span.start + stop,
        text=span.text[start:stop],
        page=span.page,
    )


def _consultation(
    documents: Iterable[tuple[SourceDocument, DocumentText]],
) -> Iterable[tuple[SourceDocument, DocumentText]]:
    """The consultation documents, each checked against its text; the law's own are skipped."""
    for document, text in documents:
        _checked(document, text)
        if document.source_kind in CONSULTATION_KINDS:
            yield document, text


def _order(
    tabled: Sequence[date | None], published: datetime | None
) -> tuple[date | None, bool | None]:
    """The earliest tabling date, and whether the document came before it.

    Both are None when any carrier is undated: the undated one may have come first, so the
    order cannot be settled. `precedes` is also None for an undated document.
    """
    if not tabled or any(day is None for day in tabled):
        return None, None
    earliest = min(day for day in tabled if day is not None)
    return earliest, None if published is None else published.date() < earliest


def _eligibility(precedes: bool | None) -> TimeEligibility:
    if precedes is None:
        return "unknown_date"
    return "ask_first" if precedes else "amendment_first"


def _proposal_windows(proposal_texts: Iterable[str]) -> set[tuple[str, ...]]:
    windows: set[tuple[str, ...]] = set()
    for proposal_text in proposal_texts:
        windows |= {window for _, window in _windows([w.text for w in words_of(proposal_text)])}
    return windows


def _checked(document: SourceDocument, text: DocumentText) -> None:
    if document.document_id != text.document_id:
        raise OriginError(f"Text of {text.document_id} does not belong to {document.document_id}")


@dataclass(frozen=True, slots=True)
class TabledOrigins:
    """Inserted wording that documents also say, and those documents, adopted or not."""

    phrases: tuple[TabledPhrase, ...]
    origins: tuple[OriginMatch, ...]


def find_tabled_origins(
    amendments: Sequence[Amendment],
    documents: Sequence[tuple[SourceDocument, DocumentText]],
    *,
    rarity: Rarity,
    adopted: Sequence[AdoptedPhrase] = (),
    submitters: Mapping[str, Actor] | None = None,
    proposal_texts: Iterable[str] = (),
) -> TabledOrigins:
    """Every document that says what an amendment inserted, whether or not it was adopted.

    The 8-word windows of each amendment's new text that hold a word it inserted
    (`lineage.inserted_words`) are indexed, leaving out windows of the Commission's proposal,
    which are not the amendment's request; windows slide over the whole new text, so an
    insertion is not cut at the words it kept. Only consultation documents are searched.
    For each (amendment, document) pair the longest shared run of at least
    `MIN_ADOPTED_RUN_WORDS` words that `rarity` finds significant is kept. A run that lies
    wholly inside adopted wording is left to `find_origins`, so a phrase is adopted or
    tabled, never both. Runs with the same
    folded words are one `TabledPhrase` carried by every amendment that yielded it; each
    `OriginMatch` names the amendments that share the run with that document, and is dated
    against them as in `find_origins`.
    """
    proposal = _proposal_windows(proposal_texts)
    adopted_windows = {
        window
        for phrase in adopted
        if phrase.kind == "verbatim"
        for _, window in _windows(phrase.text.split())
    }
    owners: list[Amendment] = []
    index: defaultdict[tuple[str, ...], list[tuple[int, int]]] = defaultdict(list)
    for amendment in amendments:
        new, inserted, _ = inserted_words(amendment)
        target = len(owners)
        owners.append(amendment)
        for start, window in _windows(new):
            if window not in proposal and any(inserted[start : start + NGRAM_WORDS]):
                index[window].append((target, start))
    first_words = frozenset(window[0] for window in index)
    by_id = {amendment.amendment_id: amendment for amendment in amendments}

    texts: dict[str, tuple[str, ...]] = {}
    carriers: defaultdict[str, set[str]] = defaultdict(set)
    found: list[OriginMatch] = []
    for document, text in _consultation(documents):
        words = words_of(text.text)
        folded = [word.text for word in words]
        submitter = (submitters or {}).get(document.document_id)
        shared: dict[str, tuple[set[str], int, int]] = {}
        for target, (first, end, _) in _runs(folded, index, first_words, rarity).items():
            run = tuple(folded[first:end])
            if all(window in adopted_windows for _, window in _windows(run)):
                continue
            phrase_id = phrase_id_of(run)
            texts[phrase_id] = run
            carriers[phrase_id].add(owners[target].amendment_id)
            ids, _, _ = shared.setdefault(phrase_id, (set(), first, end))
            ids.add(owners[target].amendment_id)
        for phrase_id, (ids, first, end) in shared.items():
            published = document.published_at
            earliest, precedes = _order([by_id[a].tabled_on for a in ids], published)
            found.append(
                OriginMatch(
                    phrase_id=phrase_id,
                    document_id=document.document_id,
                    actor_id=None if submitter is None else submitter.actor_id,
                    organisation=_organisation(document, submitter),
                    published_at=published,
                    span=_span(document, text.text, words, first, end),
                    words=end - first,
                    amendment_ids=tuple(sorted(ids)),
                    earliest_amendment_on=earliest,
                    precedes=precedes,
                    eligibility=_eligibility(precedes),
                    is_citation=is_citation(texts[phrase_id]),
                )
            )
    phrases = tuple(
        TabledPhrase(
            phrase_id=phrase_id,
            text=" ".join(run),
            words=len(run),
            amendment_ids=tuple(sorted(carriers[phrase_id])),
        )
        for phrase_id, run in sorted(texts.items())
    )
    origins = tuple(sorted(found, key=lambda m: (-m.words, m.document_id, m.phrase_id)))
    return TabledOrigins(phrases, origins)


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
