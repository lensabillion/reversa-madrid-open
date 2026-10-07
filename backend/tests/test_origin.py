"""Origins: exact quotations, honest dates, citations flagged, coalition wording visible."""

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from functools import partial

import pytest
from hypothesis import given
from hypothesis import strategies as st

from influence.schemas.atlas import (
    Actor,
    Amendment,
    DocumentText,
    Passage,
    SourceDocument,
    SourceSpan,
    span_matches,
)
from influence.schemas.lineage import (
    MIN_ADOPTED_RUN_WORDS,
    AdoptedPhrase,
    AdoptionEvidence,
    AmendmentAdoption,
    OriginMatch,
)
from influence.services import origin
from influence.services.lineage import Rarity, evidence_id_of
from influence.services.origin import (
    OriginError,
    is_citation,
    submitters_from,
)
from influence.services.prose_match import words_of

# No word is common, so these tests see the run-length rules alone; rarity has its own tests.
EVERY_WORD_RARE = Rarity(frozenset())


def find_origins(
    phrases: Sequence[AdoptedPhrase],
    adoptions: Sequence[AmendmentAdoption],
    documents: Sequence[tuple[SourceDocument, DocumentText]],
    *,
    amendments: Mapping[str, Amendment] | None = None,
    submitters: Mapping[str, Actor] | None = None,
    rarity: Rarity = EVERY_WORD_RARE,
) -> tuple[OriginMatch, ...]:
    """Single-carrier synthetic worlds explicitly accept each supplied whole phrase.

    These existing tests isolate dates, citation detection and document matching. The
    carrier regressions use real adoption instead of this intentionally simpler world.
    """
    by_id = {item.phrase_id: item for item in phrases if item.kind == "verbatim"}
    accepted: list[AmendmentAdoption] = []
    for item in adoptions:
        evidence: list[AdoptionEvidence] = []
        for phrase_id in item.phrase_ids:
            phrase = by_id.get(phrase_id)
            if phrase is None or item.kind != "verbatim":
                continue
            amendment_span = SourceSpan(
                record_id=item.amendment_id,
                field="new_text",
                start=0,
                end=len(phrase.text),
                text=phrase.text,
            )
            final_span = SourceSpan(
                record_id=FINAL.record_id,
                start=0,
                end=len(phrase.text),
                text=phrase.text,
            )
            offsets = tuple(range(phrase.words))
            evidence.append(
                AdoptionEvidence(
                    evidence_id=evidence_id_of(
                        "adoption-evidence", phrase_id, (amendment_span, final_span), offsets
                    ),
                    phrase_id=phrase_id,
                    amendment_span=amendment_span,
                    final_span=final_span,
                    inserted_word_offsets=offsets,
                )
            )
        accepted.append(item.model_copy(update={"evidence": tuple(evidence)}))
    return origin.find_origins(
        phrases,
        accepted,
        documents,
        rarity=rarity,
        amendments=amendments,
        submitters=submitters,
    )


find_tabled_origins = partial(origin.find_tabled_origins, rarity=EVERY_WORD_RARE)

SHA = "0" * 64
RETRIEVED = datetime(2026, 10, 3, tzinfo=UTC)
FINAL = SourceSpan(record_id="art:32099R0001:article-6-1", start=0, end=4, text="Word")
REQUEST = (
    "providers of high risk systems shall keep technical logs for at least six months after "
    "the system is placed on the market and make them available to the authority"
)
PHRASE_ID = "phrase:0123456789abcdef"


def phrase(text: str = REQUEST, phrase_id: str = PHRASE_ID) -> AdoptedPhrase:
    return AdoptedPhrase(
        phrase_id=phrase_id, text=text, words=len(text.split()), final_spans=(FINAL,)
    )


def adoption(
    amendment_id: str = "am:2099-0001-COD:IMCO:1",
    tabled_on: date | None = date(2099, 3, 1),
    phrase_id: str = PHRASE_ID,
    authors: tuple[str, ...] = (),
    groups: tuple[str | None, ...] = (),
) -> AmendmentAdoption:
    return AmendmentAdoption(
        amendment_id=amendment_id,
        stage="committee",
        author_ids=authors,
        author_groups=groups,
        tabled_on=tabled_on,
        phrase_ids=(phrase_id,),
        adopted_words=14,
        inserted_words=40,
        new_words=40,
        longest_run=14,
    )


def document(
    key: str = "1",
    text: str = "",
    published: datetime | None = datetime(2099, 2, 1, tzinfo=UTC),
    kind: str = "hys_attachment",
    title: str | None = "position-paper.pdf",
) -> tuple[SourceDocument, DocumentText]:
    document_id = f"doc:{kind}:{key}"
    source = SourceDocument.model_validate(
        {
            "document_id": document_id,
            "procedure_id": "2099/0001(COD)",
            "source_kind": kind,
            "url": "https://example.test/x",
            "title": title,
            "published_at": published,
            "retrieved_at": RETRIEVED,
            "sha256": SHA,
            "extraction_status": "extracted",
        }
    )
    return source, DocumentText(document_id=document_id, text=text)


def test_a_document_that_repeats_an_adopted_phrase_is_quoted_exactly_and_dated() -> None:
    text = f"Our position. We ask that {REQUEST.upper()}. Thank you."
    (match,) = find_origins([phrase()], [adoption()], [document(text=text)])
    assert match.phrase_id == PHRASE_ID
    assert match.words == len(REQUEST.split())
    assert span_matches(match.span, text)
    assert match.span.text == REQUEST.upper()
    assert match.amendment_ids == ("am:2099-0001-COD:IMCO:1",)
    assert (match.earliest_amendment_on, match.precedes) == (date(2099, 3, 1), True)
    assert not match.is_citation


def test_a_shorter_shared_run_still_counts_when_it_is_long_enough() -> None:
    words = REQUEST.split()
    text = "Intro " + " ".join(words[2:16]) + " and then something else entirely"
    (match,) = find_origins([phrase()], [adoption()], [document(text=text)])
    assert match.words == 14


def test_a_run_shorter_than_the_adopted_minimum_is_not_an_origin() -> None:
    text = " ".join(REQUEST.split()[: MIN_ADOPTED_RUN_WORDS - 1]) + " but nothing more"
    assert find_origins([phrase()], [adoption()], [document(text=text)]) == ()


def test_dates_decide_precedes_and_unknown_dates_are_never_an_origin() -> None:
    text = REQUEST
    later = document("2", text, published=datetime(2099, 4, 1, tzinfo=UTC))
    same_day = document("3", text, published=datetime(2099, 3, 1, 8, tzinfo=UTC))
    undated = document("4", text, published=None)
    results = {
        m.document_id: m.precedes
        for m in find_origins([phrase()], [adoption()], [later, same_day, undated])
    }
    assert results == {
        "doc:hys_attachment:2": False,
        "doc:hys_attachment:3": False,
        "doc:hys_attachment:4": None,
    }
    no_tabling = find_origins([phrase()], [adoption(tabled_on=None)], [document(text=text)])
    assert (no_tabling[0].earliest_amendment_on, no_tabling[0].precedes) == (None, None)


def test_the_earliest_of_several_amendments_is_the_date_to_beat() -> None:
    adoptions = [
        adoption("am:2099-0001-COD:IMCO:2", date(2099, 6, 1)),
        adoption("am:2099-0001-COD:IMCO:1", date(2099, 1, 15)),
    ]
    (match,) = find_origins([phrase()], adoptions, [document(text=REQUEST)])
    assert match.earliest_amendment_on == date(2099, 1, 15)
    assert match.precedes is False  # published 1 February, after the earliest amendment
    assert match.amendment_ids == ("am:2099-0001-COD:IMCO:1", "am:2099-0001-COD:IMCO:2")


def test_one_undated_carrier_leaves_the_order_unknown_instead_of_dropping_out() -> None:
    """Regression: the undated committee amendment used to be dropped before taking the min."""
    committee_undated = adoption("am:2099-0001-COD:IMCO:1", tabled_on=None)
    plenary_late = adoption("am:2099-0001-COD:PLENARY:2", tabled_on=date(2099, 9, 1))
    text = "We ask that " + REQUEST + "."
    published = datetime(2099, 6, 1, tzinfo=UTC)
    (match,) = find_origins(
        [phrase()], [committee_undated, plenary_late], [document(text=text, published=published)]
    )
    assert (match.earliest_amendment_on, match.precedes, match.eligibility) == (
        None,
        None,
        "unknown_date",
    )
    assert not match.counts_as_origin
    (dated,) = find_origins([phrase()], [plenary_late], [document(text=text, published=published)])
    assert (dated.precedes, dated.eligibility, dated.counts_as_origin) == (True, "ask_first", True)


def test_a_missing_tabling_date_falls_back_to_the_amendment_record() -> None:
    record = Amendment(
        amendment_id="am:2099-0001-COD:IMCO:1",
        procedure_id="2099/0001(COD)",
        document_id="doc:parltrack:x",
        stage="committee",
        tabled_on=date(2099, 5, 5),
        old_text="old",
        new_text=REQUEST,
    )
    records = {record.amendment_id: record}
    missing = adoption(tabled_on=None)
    (match,) = find_origins([phrase()], [missing], [document(text=REQUEST)], amendments=records)
    assert match.earliest_amendment_on == date(2099, 5, 5)
    (unknown,) = find_origins([phrase()], [missing], [document(text=REQUEST)], amendments={})
    assert unknown.earliest_amendment_on is None


@pytest.mark.parametrize(
    "run",
    [
        "the european parliament and of the council of 20 may 2021 setting up a union regime",
        "regulation eu 2016 679 of the european parliament and of the council on protection",
        "directive 2013 36 eu of the european parliament and of the council of 26 june",
        "commission delegated regulation eu 2019 2 laying down",
        "official journal of the european union l 119 of 4 may 2016",
        "see regulation of the european parliament and of the council of 27 april 2016 on",
        "2009 and repealing council directives 90 385 eec and 93 42 eec oj l",
        "applies to the products listed in the official journal of the european union",
    ],
)
def test_a_run_that_starts_as_a_reference_to_another_act_is_a_citation(run: str) -> None:
    assert is_citation(run.split())


def test_a_request_that_merely_mentions_a_regulation_later_is_not_a_citation() -> None:
    assert not is_citation([*REQUEST.split(), "regulation", "eu", "2016", "679"])


def test_a_citation_run_and_a_proposal_window_are_flagged() -> None:
    cited = (
        "the european parliament and of the council of 20 may 2021 setting up a union regime "
        "for the control of exports brokering technical assistance transit and transfer"
    )
    (citation,) = find_origins([phrase(cited)], [adoption()], [document(text=cited)])
    assert citation.is_citation
    assert not citation.counts_as_origin
    (request,) = find_origins([phrase()], [adoption()], [document(text=REQUEST)])
    assert not request.is_citation
    assert request.counts_as_origin


def test_only_consultation_documents_are_searched_so_the_law_never_matches_itself() -> None:
    final_act = document("1", REQUEST, kind="cellar", title="Regulation")
    feedback = document("2", REQUEST, kind="hys_feedback", title="Acme")
    found = find_origins([phrase()], [adoption()], [final_act, feedback])
    assert [match.document_id for match in found] == ["doc:hys_feedback:2"]
    tabled = find_tabled_origins([amendment()], [final_act])
    assert (tabled.phrases, tabled.origins) == ((), ())


def test_the_organisation_comes_from_the_submitter_a_comment_title_or_nothing() -> None:
    actor = Actor(
        actor_id="actor:tr:123456789012-34",
        kind="organisation",
        name="Example Association",
        resolution="register_id",
        register_id="123456789012-34",
    )
    citizen = Actor(
        actor_id="actor:citizens:all", kind="citizens", name="Citizens", resolution="unresolved"
    )
    passage = Passage(
        passage_id="passage:a:1",
        procedure_id="2099/0001(COD)",
        document_id="doc:hys_attachment:1",
        actor_id=actor.actor_id,
        span=SourceSpan(record_id="doc:hys_attachment:1", start=0, end=4, text="Text"),
        submitted_at=None,
    )
    unknown = passage.model_copy(
        update={
            "passage_id": "passage:b:1",
            "document_id": "doc:hys_attachment:2",
            "actor_id": "actor:name:ghost",
        }
    )
    submitters = submitters_from([passage, passage, unknown], [actor])
    assert set(submitters) == {"doc:hys_attachment:1"}
    named = find_origins([phrase()], [adoption()], [document("1", REQUEST)], submitters=submitters)
    assert (named[0].actor_id, named[0].organisation) == (actor.actor_id, "Example Association")
    citizens = find_origins(
        [phrase()],
        [adoption()],
        [document("1", REQUEST)],
        submitters={"doc:hys_attachment:1": citizen},
    )
    assert (citizens[0].actor_id, citizens[0].organisation) == (citizen.actor_id, None)
    comment = document("9", REQUEST, kind="hys_feedback", title="Acme Lobby")
    attachment = document("8", REQUEST, kind="hys_attachment", title="paper.pdf")
    by_title = {
        m.document_id: m.organisation
        for m in find_origins([phrase()], [adoption()], [comment, attachment])
    }
    assert by_title == {"doc:hys_feedback:9": "Acme Lobby", "doc:hys_attachment:8": None}


def test_contradictory_inputs_are_refused() -> None:
    with pytest.raises(OriginError, match="carried by no amendment"):
        find_origins([phrase()], [], [document(text=REQUEST)])
    source, _ = document("1", REQUEST)
    other = DocumentText(document_id="doc:hys_attachment:2", text=REQUEST)
    with pytest.raises(OriginError, match="does not belong"):
        find_origins([phrase()], [adoption()], [(source, other)])


def test_semantic_phrases_and_adoptions_are_left_to_the_semantic_piece() -> None:
    semantic = AdoptedPhrase(
        phrase_id="phrase:aaaaaaaaaaaaaaaa",
        kind="semantic",
        text="providers keep logs",
        words=3,
        final_spans=(FINAL,),
        similarity=0.9,
    )
    other = adoption("am:2099-0001-COD:IMCO:7", phrase_id=semantic.phrase_id).model_copy(
        update={"kind": "semantic"}
    )
    assert find_origins([semantic], [other], [document(text="providers keep logs")]) == ()


def test_a_repeated_quotation_is_reported_once_with_its_longest_run() -> None:
    words = REQUEST.split()
    text = " ".join(words[:13]) + " blah blah " + REQUEST
    (match,) = find_origins([phrase()], [adoption()], [document(text=text)])
    assert match.words == len(words)
    assert match.span.text == REQUEST


@pytest.mark.parametrize(("changed", "kept"), [(20, 20), (12, 27)])
def test_a_quotation_broken_by_one_changed_word_keeps_its_longest_unbroken_run(
    changed: int, kept: int
) -> None:
    words = [f"term{i}" for i in range(40)]
    quoted = [*words[:changed], "different", *words[changed + 1 :]]
    (match,) = find_origins(
        [phrase(" ".join(words))], [adoption()], [document(text=" ".join(quoted))]
    )
    assert match.words == kept


def test_output_is_ordered_longest_first_and_is_reproducible() -> None:
    short = phrase(" ".join(f"term{i}" for i in range(12)), "phrase:aaaaaaaaaaaaaaaa")
    short_adoption = adoption("am:2099-0001-COD:IMCO:2", phrase_id=short.phrase_id)
    text = REQUEST + " ordinary words in between " + short.text
    docs = [document("1", text)]
    first = find_origins([short, phrase()], [adoption(), short_adoption], docs)
    again = find_origins([phrase(), short], [short_adoption, adoption()], docs)
    assert [m.words for m in first] == [len(REQUEST.split()), 12]
    assert first == again


WORD = st.sampled_from(["alpha", "beta", "gamma", "delta", "Epsilon", "zeta", "eta", "x1", "x2"])


@given(
    body=st.lists(WORD, min_size=12, max_size=24),
    before=st.lists(WORD, max_size=10),
    after=st.lists(WORD, max_size=10),
    separator=st.sampled_from([" ", ", ", " - ", "\n"]),
)
def test_every_origin_span_is_an_exact_substring_of_its_document(
    body: list[str], before: list[str], after: list[str], separator: str
) -> None:
    folded = " ".join(word.casefold() for word in body)
    text = separator.join([*before, *body, *after])
    for match in find_origins([phrase(folded)], [adoption()], [document(text=text)]):
        assert span_matches(match.span, text)
        assert match.words >= 12
        run = " ".join(word.text for word in words_of(match.span.text))
        assert f" {run} " in f" {folded} "


# --- Tabled wording: documents tied to amendments whether or not they were adopted ---------


def amendment(
    number: int = 1,
    new_text: str = REQUEST,
    old_text: str | None = None,
    tabled_on: date | None = date(2099, 3, 1),
) -> Amendment:
    return Amendment(
        amendment_id=f"am:2099-0001-COD:IMCO:{number}",
        procedure_id="2099/0001(COD)",
        document_id="doc:parltrack:x",
        stage="committee",
        tabled_on=tabled_on,
        old_text=old_text,
        new_text=new_text,
    )


def test_a_document_is_tied_to_an_amendment_that_was_never_adopted() -> None:
    text = f"Our position. We ask that {REQUEST.upper()}. Thank you."
    found = find_tabled_origins(
        [amendment(old_text="Providers shall keep logs.")], [document(text=text)]
    )
    (tabled,) = found.phrases
    (match,) = found.origins
    # The amendment kept "providers", "shall keep" and "logs" from its original but rewrote
    # the sentence around them: the run is the whole rewritten sentence, not cut at the kept
    # words, because every window of it holds an inserted word.
    assert tabled.text == REQUEST
    assert tabled.amendment_ids == ("am:2099-0001-COD:IMCO:1",)
    assert match.phrase_id == tabled.phrase_id
    assert match.span.text == REQUEST.upper()
    assert span_matches(match.span, text)
    assert (match.earliest_amendment_on, match.precedes, match.is_citation) == (
        date(2099, 3, 1),
        True,
        False,
    )


def test_amendments_inserting_the_same_wording_share_one_phrase_and_the_earliest_date() -> None:
    amendments = [
        amendment(2, tabled_on=date(2099, 6, 1)),
        amendment(1, tabled_on=date(2099, 1, 15)),
    ]
    undated = document("2", REQUEST, published=None)
    found = find_tabled_origins(amendments, [document(text=REQUEST), undated])
    (tabled,) = found.phrases
    ids = ("am:2099-0001-COD:IMCO:1", "am:2099-0001-COD:IMCO:2")
    assert tabled.amendment_ids == ids
    dated, unknown = sorted(found.origins, key=lambda m: m.document_id)
    assert (dated.amendment_ids, dated.earliest_amendment_on) == (ids, date(2099, 1, 15))
    assert (dated.precedes, dated.eligibility) == (False, "amendment_first")
    assert (unknown.precedes, unknown.eligibility) == (None, "unknown_date")
    # One undated carrier may have come first, so the order is unknown, not decided by the
    # dated ones (the chronology hole the reviewer found).
    with_undated = find_tabled_origins(
        [*amendments, amendment(3, tabled_on=None)], [document(text=REQUEST)]
    )
    (match,) = with_undated.origins
    assert (match.earliest_amendment_on, match.precedes, match.eligibility) == (
        None,
        None,
        "unknown_date",
    )
    only_undated = find_tabled_origins([amendment(tabled_on=None)], [document(text=REQUEST)])
    assert (only_undated.origins[0].earliest_amendment_on, only_undated.origins[0].precedes) == (
        None,
        None,
    )


def test_adopted_wording_is_left_to_find_origins_and_only_the_rest_is_tabled() -> None:
    extra = " and publish a yearly summary of incidents in plain language for every citizen"
    wholly = find_tabled_origins([amendment()], [document(text=REQUEST)], adopted=[phrase()])
    assert (wholly.phrases, wholly.origins) == ((), ())
    longer = REQUEST + extra
    partly = find_tabled_origins(
        [amendment(new_text=longer)], [document(text=longer)], adopted=[phrase()]
    )
    assert [p.text for p in partly.phrases] == [longer]
    semantic = phrase().model_copy(update={"kind": "semantic", "similarity": 0.9})
    assert find_tabled_origins([amendment()], [document(text=REQUEST)], adopted=[semantic]).phrases


def test_the_proposals_own_wording_and_short_runs_are_not_a_request() -> None:
    proposal = find_tabled_origins(
        [amendment()], [document(text=REQUEST)], proposal_texts=[REQUEST]
    )
    assert (proposal.phrases, proposal.origins) == ((), ())
    short = " ".join(REQUEST.split()[: MIN_ADOPTED_RUN_WORDS - 1]) + " but nothing more"
    assert find_tabled_origins([amendment()], [document(text=short)]).origins == ()


def test_a_tabled_citation_is_flagged_and_the_submitter_is_named() -> None:
    citation = "regulation eu 2016 679 of the european parliament and of the council on protection"
    acme = Actor(actor_id="actor:tr:1", kind="organisation", name="Acme", resolution="unresolved")
    source, text = document(text=citation)
    found = find_tabled_origins(
        [amendment(new_text=citation)],
        [(source, text)],
        submitters={source.document_id: acme},
    )
    (match,) = found.origins
    assert (match.is_citation, match.organisation, match.actor_id) == (True, "Acme", "actor:tr:1")


def test_tabled_search_refuses_a_text_of_another_document() -> None:
    source, _ = document("1", REQUEST)
    other = DocumentText(document_id="doc:hys_attachment:2", text=REQUEST)
    with pytest.raises(OriginError, match="does not belong"):
        find_tabled_origins([amendment()], [(source, other)])


@given(
    body=st.lists(WORD, min_size=12, max_size=24),
    before=st.lists(WORD, max_size=10),
    after=st.lists(WORD, max_size=10),
    separator=st.sampled_from([" ", ", ", " - ", "\n"]),
)
def test_every_tabled_origin_quotes_its_document_and_names_carriers_of_its_phrase(
    body: list[str], before: list[str], after: list[str], separator: str
) -> None:
    text = separator.join([*before, *body, *after])
    found = find_tabled_origins([amendment(new_text=" ".join(body))], [document(text=text)])
    carriers = {p.phrase_id: set(p.amendment_ids) for p in found.phrases}
    for match in found.origins:
        assert span_matches(match.span, text)
        assert match.words >= 12
        assert set(match.amendment_ids) <= carriers[match.phrase_id]


def test_a_run_of_the_laws_common_words_is_no_origin_adopted_or_tabled() -> None:
    common = Rarity(frozenset(REQUEST.split()))
    docs = [document(text=REQUEST)]
    assert find_origins([phrase()], [adoption()], docs, rarity=common) == ()
    tabled = origin.find_tabled_origins([amendment()], docs, rarity=common)
    assert (tabled.phrases, tabled.origins) == ((), ())
