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
    )


def credit(phrases: float) -> Credit:
    return Credit(
        holder_id="actor:mep:1",
        holder_kind="mep",
        name="A. Example",
        phrases=phrases,
        distinct_phrases=1,
        amendments=1,
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
        "credits": (credit(1.0), credit(0.5)),
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


def test_an_adoption_cannot_adopt_more_than_it_inserted() -> None:
    base = adoption().model_dump()
    with pytest.raises(ValidationError, match="adopted more words"):
        AmendmentAdoption.model_validate(base | {"inserted_words": MIN_ADOPTED_RUN_WORDS - 1})
    with pytest.raises(ValidationError, match="longest run"):
        AmendmentAdoption.model_validate(
            base
            | {"longest_run": MIN_ADOPTED_RUN_WORDS + 5, "adopted_words": MIN_ADOPTED_RUN_WORDS + 4}
        )
    assert AmendmentAdoption.model_validate(base | {"kind": "semantic"}).kind == "semantic"


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


def test_credits_are_listed_from_most_to_least() -> None:
    with pytest.raises(ValidationError, match="most to least"):
        view(credits=(credit(0.5), credit(1.0)))
    semantic = credit(0.2).model_copy(update={"basis": "semantic"})
    assert view(credits=(credit(1.0), credit(0.5), semantic)).credits[-1].basis == "semantic"
    assert view(credits=()).credits == ()


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
    with pytest.raises(ValidationError, match="cannot exceed"):
        LineageCounts.model_validate(fields | {"linked_units": 11})
