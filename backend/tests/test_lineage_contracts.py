"""The lineage contracts: self-consistent records, resolvable references, ordered credits."""

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from influence.schemas.atlas import SourceSpan
from influence.schemas.lineage import (
    MIN_ADOPTED_RUN_WORDS,
    AdoptedPhrase,
    AmendmentAdoption,
    Credit,
    LineageCounts,
    LineageView,
    OriginMatch,
    TabledPhrase,
)

WORDS = " ".join(f"word{i}" for i in range(MIN_ADOPTED_RUN_WORDS))
PHRASE_ID = "phrase:0123456789abcdef"
SPAN = SourceSpan(record_id="art:32099R0001:article-6-1", start=0, end=4, text="Word")


def phrase(phrase_id: str = PHRASE_ID, text: str = WORDS) -> AdoptedPhrase:
    return AdoptedPhrase(
        phrase_id=phrase_id, text=text, words=len(text.split()), final_spans=(SPAN,)
    )


def adoption(amendment_id: str = "am:2099-0001-COD:IMCO:1") -> AmendmentAdoption:
    return AmendmentAdoption(
        amendment_id=amendment_id,
        stage="committee",
        tabled_on=date(2099, 3, 1),
        phrase_ids=(PHRASE_ID,),
        adopted_words=MIN_ADOPTED_RUN_WORDS,
        inserted_words=40,
        new_words=40,
        longest_run=MIN_ADOPTED_RUN_WORDS,
    )


def origin(amendment_id: str = "am:2099-0001-COD:IMCO:1") -> OriginMatch:
    return OriginMatch(
        phrase_id=PHRASE_ID,
        document_id="doc:hys_attachment:1",
        span=SPAN,
        words=MIN_ADOPTED_RUN_WORDS,
        amendment_ids=(amendment_id,),
        earliest_amendment_on=date(2099, 3, 1),
        precedes=True,
        eligibility="ask_first",
    )


def credit(amendments: int, tabled: int = 4, holder: str = "actor:mep:1") -> Credit:
    return Credit(
        holder_id=holder,
        holder_kind="mep",
        name="A. Example",
        phrases=1,
        joint_phrases=0,
        amendments=amendments,
        amendments_tabled=tabled,
    )


def view(**changes: object) -> LineageView:
    data: dict[str, object] = {
        "procedure_id": "2099/0001(COD)",
        "slug": "2099-0001-COD",
        "title": "Widget Act",
        "run_id": "run-1",
        "generated_at": datetime(2099, 12, 1, tzinfo=UTC),
        "method": "adopted-phrases",
        "method_revision": "lineage-1.0",
        "counts": LineageCounts(
            amendments=10,
            amendments_adopting=1,
            adopted_phrases=1,
            documents_read=5,
            documents_with_origin=1,
        ),
        "adopted_phrases": (phrase(),),
        "adoptions": (adoption(),),
        "origins": (origin(),),
        "credits": (credit(2), credit(1, 2, "actor:mep:2"), credit(1)),
    }
    return LineageView.model_validate(data | changes)


def test_a_consistent_view_round_trips_through_json() -> None:
    original = view()
    assert LineageView.model_validate_json(original.model_dump_json()) == original
    assert original.schema_version == "lineage-1"


def test_a_phrase_counts_its_own_words_and_a_minimum_length() -> None:
    with pytest.raises(ValidationError, match="number of words"):
        AdoptedPhrase(
            phrase_id=PHRASE_ID, text=WORDS, words=MIN_ADOPTED_RUN_WORDS + 1, final_spans=(SPAN,)
        )
    with pytest.raises(ValidationError, match="MIN_ADOPTED_RUN_WORDS"):
        phrase(text="too short")
    with pytest.raises(ValidationError):
        phrase(phrase_id="phrase:nothex")


def test_a_semantic_phrase_may_be_short_but_carries_its_similarity() -> None:
    short = AdoptedPhrase(
        phrase_id="phrase:aaaaaaaaaaaaaaaa",
        kind="semantic",
        text="providers keep logs",
        words=3,
        final_spans=(SPAN,),
        similarity=0.83,
        judge_probability=0.9,
    )
    assert short.kind == "semantic"
    with pytest.raises(ValidationError, match="its similarity"):
        AdoptedPhrase(
            phrase_id="phrase:aaaaaaaaaaaaaaaa",
            kind="semantic",
            text="providers keep logs",
            words=3,
            final_spans=(SPAN,),
        )


def test_an_adoption_fits_inside_its_new_text_and_names_one_group_per_author() -> None:
    base = adoption().model_dump()
    with pytest.raises(ValidationError, match="more words than it holds"):
        AmendmentAdoption.model_validate(base | {"new_words": MIN_ADOPTED_RUN_WORDS - 1})
    with pytest.raises(ValidationError, match="more words than it holds"):
        AmendmentAdoption.model_validate(base | {"inserted_words": 41})
    with pytest.raises(ValidationError, match="longest run"):
        AmendmentAdoption.model_validate(
            base
            | {"longest_run": MIN_ADOPTED_RUN_WORDS + 5, "adopted_words": MIN_ADOPTED_RUN_WORDS + 4}
        )
    # A rewritten sentence adopts more of the amendment's words than it inserted.
    rewritten = AmendmentAdoption.model_validate(base | {"adopted_words": 40, "inserted_words": 9})
    assert rewritten.adopted_words > rewritten.inserted_words
    assert AmendmentAdoption.model_validate(base | {"kind": "semantic"}).kind == "semantic"
    authors = {"author_ids": ["actor:mep:1", "actor:mep:2"]}
    assert AmendmentAdoption.model_validate(
        base | authors | {"author_groups": ["PPE", None]}
    ).author_groups == ("PPE", None)
    with pytest.raises(ValidationError, match="one group per author"):
        AmendmentAdoption.model_validate(base | authors | {"author_groups": ["PPE"]})


def test_references_must_resolve() -> None:
    other = phrase("phrase:fedcba9876543210", WORDS.replace("word", "term"))
    with pytest.raises(ValidationError, match="Duplicate phrase"):
        view(adopted_phrases=(phrase(), phrase()))
    with pytest.raises(ValidationError, match="names a phrase"):
        view(adopted_phrases=(other,))
    with pytest.raises(ValidationError, match="names a phrase"):
        view(adoptions=(), origins=(origin(),), adopted_phrases=(other,))
    with pytest.raises(ValidationError, match="does not carry"):
        view(origins=(origin("am:2099-0001-COD:IMCO:9"),))


def test_credit_is_whole_and_counted_against_the_amendments_tabled() -> None:
    whole = credit(3, 4)
    assert (whole.phrases, whole.rate) == (1, 0.75)
    assert isinstance(whole.phrases, int)
    with pytest.raises(ValidationError):
        Credit.model_validate(whole.model_dump() | {"phrases": 0.5})
    with pytest.raises(ValidationError, match="more adopting amendments"):
        credit(5, 4)
    with pytest.raises(ValidationError, match="Joint phrases"):
        Credit.model_validate(whole.model_dump() | {"joint_phrases": 2})


def test_credits_are_ranked_by_kind_then_rate_per_amendment_tabled() -> None:
    with pytest.raises(ValidationError, match="credit_rank"):
        view(credits=(credit(1), credit(2)))
    group = Credit(
        holder_id="PPE",
        holder_kind="group",
        name="PPE",
        phrases=4,
        joint_phrases=0,
        amendments=4,
        amendments_tabled=4,
    )
    # A Member with a better rate ranks first; groups come after every Member.
    ranked = view(credits=(credit(2), credit(1), group))
    assert [c.holder_kind for c in ranked.credits] == ["mep", "mep", "group"]
    semantic = credit(4).model_copy(update={"basis": "semantic"})
    assert view(credits=(credit(1), semantic)).credits[-1].basis == "semantic"
    assert view(credits=()).credits == ()


def test_an_origins_eligibility_follows_its_dates_and_only_eligible_ones_count() -> None:
    assert origin().counts_as_origin
    assert not origin().model_copy(update={"is_citation": True}).counts_as_origin
    later = origin().model_dump() | {"precedes": False, "eligibility": "amendment_first"}
    assert not OriginMatch.model_validate(later).counts_as_origin
    undated = origin().model_dump() | {"precedes": None, "eligibility": "unknown_date"}
    assert not OriginMatch.model_validate(undated).counts_as_origin
    with pytest.raises(ValidationError, match="must follow"):
        OriginMatch.model_validate(origin().model_dump() | {"precedes": None})


def test_an_unknown_adoption_carries_its_reason_and_lists_nothing() -> None:
    unknown = {
        "status": "unknown",
        "reason": "The final act's text was not collected.",
        "counts": LineageCounts(amendments=10),
        "adopted_phrases": (),
        "adoptions": (),
        "origins": (),
        "credits": (),
    }
    assert view(**unknown).counts.adopted_phrases is None
    with pytest.raises(ValidationError, match="carries its reason"):
        view(**(unknown | {"reason": None}))
    with pytest.raises(ValidationError, match="carries its reason"):
        view(reason="no reason without unknown")
    with pytest.raises(ValidationError, match="lists no phrases"):
        view(status="unknown", reason="missing")


TABLED_ID = "phrase:aaaaaaaaaaaaaaaa"


def tabled(amendment_id: str = "am:2099-0001-COD:IMCO:9") -> TabledPhrase:
    text = WORDS.replace("word", "other")
    return TabledPhrase(
        phrase_id=TABLED_ID, text=text, words=len(text.split()), amendment_ids=(amendment_id,)
    )


def test_an_origin_can_tie_a_document_to_an_amendment_that_was_never_adopted() -> None:
    loser = "am:2099-0001-COD:IMCO:9"
    link = origin(loser).model_copy(update={"phrase_id": TABLED_ID})
    resolved = view(tabled_phrases=(tabled(loser),), origins=(origin(), link))
    assert resolved.origins[1].amendment_ids == (loser,)
    stray = origin().model_copy(update={"phrase_id": TABLED_ID})
    with pytest.raises(ValidationError, match="does not carry"):
        view(tabled_phrases=(tabled(),), origins=(stray,))
    with pytest.raises(ValidationError, match="adopted or only tabled"):
        view(tabled_phrases=(tabled().model_copy(update={"phrase_id": PHRASE_ID}),))
    with pytest.raises(ValidationError, match="Duplicate"):
        view(tabled_phrases=(tabled(), tabled()))
    with pytest.raises(ValidationError, match="number of words"):
        TabledPhrase(phrase_id=TABLED_ID, text="a b", words=5, amendment_ids=("am:x",))


def test_coverage_counts_cannot_link_more_than_changed() -> None:
    fields = {
        "amendments": 5,
        "amendments_adopting": 2,
        "adopted_phrases": 3,
        "documents_read": 4,
        "documents_with_origin": 1,
        "changed_units": 10,
        "linked_units": 7,
    }
    assert view(counts=LineageCounts.model_validate(fields)).counts.linked_units == 7
    with pytest.raises(ValidationError, match="Linked units cannot exceed"):
        LineageCounts.model_validate(fields | {"linked_units": 11})
    with pytest.raises(ValidationError, match="Documents with an origin cannot exceed"):
        LineageCounts.model_validate(fields | {"documents_with_origin": 5})


def test_a_count_not_computed_is_none_never_zero() -> None:
    counts = LineageCounts(amendments=5)
    assert (
        counts.amendments_adopting,
        counts.adopted_phrases,
        counts.phrases_without_group,
        counts.documents_read,
        counts.documents_with_origin,
        counts.changed_units,
        counts.linked_units,
    ) == (None, None, None, None, None, None, None)
    assert LineageCounts(amendments=5, linked_units=3).linked_units == 3
