"""Origins: exact quotations, honest dates, citations flagged, coalition wording visible."""

from datetime import UTC, date, datetime

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
from influence.schemas.lineage import AdoptedPhrase, AmendmentAdoption
from influence.services.origin import (
    OriginError,
    coalition_phrase_ids,
    find_origins,
    is_citation,
    submitters_from,
)
from influence.services.prose_match import words_of

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
) -> AmendmentAdoption:
    return AmendmentAdoption(
        amendment_id=amendment_id,
        stage="committee",
        author_ids=authors,
        tabled_on=tabled_on,
        phrase_ids=(phrase_id,),
        adopted_words=14,
        inserted_words=40,
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
    text = " ".join(REQUEST.split()[:10]) + " but nothing more"
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


def test_a_missing_tabling_date_falls_back_to_the_amendment_record() -> None:
    record = Amendment(
        amendment_id="am:2099-0001-COD:IMCO:1",
        procedure_id="2099/0001(COD)",
        document_id="doc:parltrack:x",
        stage="committee",
        tabled_on=date(2099, 5, 5),
        old_text="old",
        new_text="new",
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
    (citation,) = find_origins(
        [phrase(cited)], [adoption()], [document(text=cited)], proposal_texts=()
    )
    assert citation.is_citation
    (from_proposal,) = find_origins(
        [phrase()], [adoption()], [document(text=REQUEST)], proposal_texts=[f"Article 5 {REQUEST}"]
    )
    assert from_proposal.is_citation


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


def test_coalition_phrases_are_those_carried_by_three_or_more_groups() -> None:
    adoptions = [
        adoption("am:2099-0001-COD:IMCO:1", authors=("actor:mep:1", "actor:mep:2")),
        adoption("am:2099-0001-COD:IMCO:2", authors=("actor:mep:3",)),
        adoption("am:2099-0001-COD:IMCO:3", authors=("actor:mep:4", "actor:mep:99")),
        adoption(
            "am:2099-0001-COD:IMCO:4", phrase_id="phrase:fedcba9876543210", authors=("actor:mep:1",)
        ),
    ]
    groups = {"actor:mep:1": "PPE", "actor:mep:2": "PPE", "actor:mep:3": "S&D", "actor:mep:4": "RE"}
    assert coalition_phrase_ids(adoptions, groups) == {PHRASE_ID}
    assert coalition_phrase_ids(adoptions, groups, minimum=4) == frozenset()
    assert coalition_phrase_ids([], groups) == frozenset()


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
    assert coalition_phrase_ids([other], {}) == frozenset()


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
