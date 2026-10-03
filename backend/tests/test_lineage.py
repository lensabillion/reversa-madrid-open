"""Verbatim adoption: new wording of the final act, the amendments that carry it, and credit."""

from datetime import date

from atlas_fixture import build_fixture
from hypothesis import given
from hypothesis import strategies as st

from influence.schemas.atlas import Actor, Amendment, ArticleVersion, span_matches
from influence.schemas.lineage import MIN_ADOPTED_RUN_WORDS
from influence.services import lineage
from influence.services.lineage import COMMITTEE_TEXT, Rarity, adopt, adopt_records
from influence.services.pipeline import Collected

PROCEDURE = "2099/0001(COD)"


def sentence(prefix: str, count: int = 20, first: int = 0) -> str:
    """`count` distinct invented words, so a run of them cannot occur by chance."""
    return " ".join(f"{prefix}{number}" for number in range(first, first + count))


def article(name: str, text: str, stage: str = "final_act") -> ArticleVersion:
    return ArticleVersion(
        article_id=f"art:{stage}:{name.replace(' ', '-')}",
        procedure_id=PROCEDURE,
        document_id=f"doc:cellar:{stage}",
        stage=stage,  # pyright: ignore[reportArgumentType]
        provision=name,
        kind="article",
        text=text,
    )


def amendment(
    number: int,
    new: str,
    old: str | None = "",
    authors: tuple[str, ...] = ("actor:mep:1",),
    stage: str = "committee",
) -> Amendment:
    return Amendment(
        amendment_id=f"am:2099-0001-COD:IMCO:{number}",
        procedure_id=PROCEDURE,
        document_id="doc:parltrack:x",
        stage=stage,  # pyright: ignore[reportArgumentType]
        committee="IMCO",
        author_ids=authors,
        author_names=tuple(f"MEP {author}" for author in authors),
        tabled_on=date(2099, 3, 1),
        old_text=old,
        new_text=new,
    )


def mep(number: int, group: str | None) -> Actor:
    return Actor(
        actor_id=f"actor:mep:{number}",
        kind="mep",
        name=f"Member {number}",
        mep_id=number,
        political_group=group,
        resolution="mep_id",
    )


NEW = sentence("novel")
PROPOSAL = article("Article 1", "The providers shall keep logs. " + sentence("old"), "proposal")
FINAL = article("Article 1", "The providers shall keep logs. " + NEW)


def test_wording_new_in_the_final_act_is_adopted_with_exact_quotations() -> None:
    result = adopt_records(
        [amendment(1, "Providers shall keep logs. " + NEW, old="Providers shall keep logs.")],
        [PROPOSAL, FINAL],
        [],
    )
    (phrase,) = result.phrases
    assert phrase.text == NEW
    assert phrase.words == 20
    assert phrase.phrase_id.startswith("phrase:")
    assert all(span_matches(span, FINAL.text) for span in phrase.final_spans)
    (adoption,) = result.adoptions
    assert (adoption.adopted_words, adoption.longest_run) == (20, 20)
    assert adoption.inserted_words >= 20
    assert (result.amendments, result.amendments_adopting) == (1, 1)
    counts = result.counts(documents_read=4, documents_with_origin=1)
    assert (counts.adopted_phrases, counts.documents_read, counts.documents_with_origin) == (
        1,
        4,
        1,
    )


def test_wording_that_was_already_in_the_proposal_is_not_adopted() -> None:
    old_wording = sentence("old")
    result = adopt_records(
        [amendment(1, "Providers shall keep logs. " + old_wording)],
        [PROPOSAL, article("Article 1", "Providers shall keep logs. " + old_wording)],
        [],
    )
    assert result.phrases == ()
    assert result.adoptions == ()


def test_a_shared_run_shorter_than_the_minimum_is_not_adopted() -> None:
    short = sentence("brief", MIN_ADOPTED_RUN_WORDS - 2)
    result = adopt_records([amendment(1, short)], [article("A", short)], [])
    assert result.phrases == ()


def test_wording_the_amendment_did_not_insert_is_not_adopted() -> None:
    """The amendment's own original already held the run, so it inserted nothing new."""
    both = "Providers shall keep logs. " + NEW
    result = adopt_records([amendment(1, both, old=both)], [PROPOSAL, FINAL], [])
    assert result.adoptions == ()


def test_replaced_and_deleted_words_are_diffed_and_only_insertions_count() -> None:
    old = "Providers shall keep logs. " + sentence("gone", 8) + " tail words stay"
    new = "Providers shall keep logs. " + NEW + " tail words stay"
    result = adopt_records([amendment(1, new, old=old)], [PROPOSAL, FINAL], [])
    (adoption,) = result.adoptions
    assert adoption.inserted_words == 20
    deleted = adopt_records(
        [amendment(2, "Providers shall keep logs.", old=old)], [PROPOSAL, FINAL], []
    )
    assert deleted.adoptions == ()


def test_an_unknown_original_treats_the_whole_text_as_inserted_and_says_so() -> None:
    result = adopt_records([amendment(1, NEW, old=None)], [PROPOSAL, FINAL], [])
    assert len(result.adoptions) == 1
    assert any("no original wording" in note for note in result.limitations)


def test_an_amendment_too_long_for_an_exact_diff_is_handled_and_says_so() -> None:
    filler = " ".join(["filler"] * (lineage.MAX_DIFF_WORDS + 5))
    old = "keep " + filler
    new = NEW + " keep " + filler + " " + sentence("tailword", 3)
    result = adopt_records([amendment(1, new, old=old)], [PROPOSAL, FINAL], [])
    (adoption,) = result.adoptions
    assert adoption.adopted_words == 20
    assert any("too long for an exact diff" in note for note in result.limitations)
    only_known = adopt_records([amendment(2, filler, old=old + " extra")], [PROPOSAL, FINAL], [])
    assert only_known.adoptions == ()


def test_runs_that_switch_place_in_the_final_act_do_not_double_count_words() -> None:
    words = sentence("move").split()
    first, second = " ".join(words[:14]), " ".join(words[6:])
    final = [article("A", first), article("B", second)]
    result = adopt_records([amendment(1, " ".join(words))], [PROPOSAL, *final], [])
    (adoption,) = result.adoptions
    assert len(result.phrases) == 2
    assert adoption.adopted_words == 20
    assert adoption.inserted_words == 20
    assert adoption.longest_run == 14


def test_the_same_wording_in_two_amendments_is_one_phrase_and_the_credit_is_shared() -> None:
    actors = [mep(1, "PPE"), mep(2, "PPE"), mep(3, "S&D")]
    amendments = [
        amendment(1, NEW, authors=("actor:mep:1", "actor:mep:2")),
        amendment(2, NEW, authors=("actor:mep:3",), stage="plenary"),
    ]
    result = adopt_records(amendments, [PROPOSAL, FINAL], actors)
    assert len(result.phrases) == 1
    assert len(result.adoptions) == 2
    assert {adoption.stage for adoption in result.adoptions} == {"committee", "plenary"}
    by_name = {(credit.holder_kind, credit.name): credit for credit in result.credits}
    assert by_name[("mep", "Member 1")].phrases == 1 / 3
    assert by_name[("mep", "Member 3")].phrases == 1 / 3
    # Two co-signers of one group add up; the group never exceeds one phrase.
    assert by_name[("group", "PPE")].phrases == 2 / 3
    assert by_name[("group", "S&D")].phrases == 1 / 3
    assert by_name[("group", "PPE")].amendments == 1
    scores = [credit.phrases for credit in result.credits]
    assert scores == sorted(scores, reverse=True)


def test_an_amendment_without_authors_is_credited_to_the_committee_text() -> None:
    result = adopt_records([amendment(1, NEW, authors=())], [PROPOSAL, FINAL], [])
    (credit,) = result.credits
    assert (credit.holder_id, credit.holder_kind, credit.phrases) == (
        COMMITTEE_TEXT,
        "committee_text",
        1.0,
    )
    assert credit.amendments == 1


def test_an_author_missing_from_the_actors_has_an_unknown_group_and_keeps_the_id_as_name() -> None:
    result = adopt_records([amendment(1, NEW, authors=("actor:mep:9",))], [PROPOSAL, FINAL], [])
    names = {(credit.holder_kind, credit.name) for credit in result.credits}
    assert names == {("mep", "actor:mep:9"), ("group", "unknown")}
    ungrouped = adopt_records(
        [amendment(1, NEW, authors=("actor:mep:4",))], [PROPOSAL, FINAL], [mep(4, None)]
    )
    assert ("group", "unknown") in {(c.holder_kind, c.name) for c in ungrouped.credits}


def test_a_phrase_found_in_several_final_places_quotes_at_most_three() -> None:
    final = [article(f"Copy {number}", NEW) for number in range(5)]
    # Enough other provisions that five copies stay under the law's rarity share.
    others = [article(f"Other {n}", sentence("other", 3, 3 * n)) for n in range(120)]
    result = adopt_records([amendment(1, NEW)], [PROPOSAL, *final, *others], [])
    (phrase,) = result.phrases
    assert len(phrase.final_spans) == lineage.MAX_SPANS_PER_PHRASE


def test_a_law_without_a_final_act_adopts_nothing() -> None:
    result = adopt_records([amendment(1, NEW)], [PROPOSAL], [])
    assert result.phrases == ()
    assert result.credits == ()
    assert result.limitations == ()
    assert result.amendments_adopting == 0


def test_adopt_reads_a_collected_law() -> None:
    fixture = build_fixture()
    collected = Collected(
        manifest=fixture.manifests[0],
        law=fixture.laws[0],
        documents=(),
        document_texts=(),
        passages=(),
        actors=fixture.actors,
        amendments=(amendment(1, NEW),),
        articles=(PROPOSAL, FINAL),
    )
    assert len(adopt(collected).phrases) == 1


WORDS = st.sampled_from([f"w{number}" for number in range(6)])
TEXTS = st.lists(WORDS, min_size=0, max_size=40).map(" ".join)


@given(
    proposal=TEXTS,
    final=st.lists(TEXTS, min_size=1, max_size=3),
    inserted=st.lists(TEXTS, min_size=1, max_size=4),
    authors=st.lists(st.sampled_from(["1", "2", "3", ""]), min_size=1, max_size=4),
)
def test_every_quotation_is_exact_and_each_phrase_is_worth_exactly_one(
    proposal: str, final: list[str], inserted: list[str], authors: list[str]
) -> None:
    articles = [article("P", proposal, "proposal")] if proposal else []
    articles += [article(f"F{number}", text) for number, text in enumerate(final) if text]
    amendments = [
        amendment(
            number,
            text,
            authors=(f"actor:mep:{authors[number % len(authors)]}",)
            if authors[number % len(authors)]
            else (),
        )
        for number, text in enumerate(inserted)
        if text
    ]
    result = adopt_records(amendments, articles, [mep(1, "PPE"), mep(2, "PPE"), mep(3, None)])
    texts = {item.article_id: item.text for item in articles}
    for phrase in result.phrases:
        assert phrase.words >= MIN_ADOPTED_RUN_WORDS
        assert all(span_matches(span, texts[span.record_id]) for span in phrase.final_spans)
    known = {phrase.phrase_id for phrase in result.phrases}
    assert all(set(adoption.phrase_ids) <= known for adoption in result.adoptions)
    assert result.amendments_adopting == len(result.adoptions) <= result.amendments
    individual = sum(c.phrases for c in result.credits if c.holder_kind != "group")
    grouped = sum(c.phrases for c in result.credits if c.holder_kind == "group")
    assert abs(individual - len(result.phrases)) < 1e-9
    assert grouped <= len(result.phrases) + 1e-9


# --- Rarity: a run made of the law's own common words is not shared wording ---------------


def test_a_word_is_common_in_enough_provisions_and_never_in_only_one() -> None:
    small = Rarity.of(["shall b", "shall c", "shall d"])
    assert small.common == frozenset({"shall"})
    assert small.significant(["shall", "b", "c", "d"])
    assert not small.significant(["shall", "b", "c"])
    assert not small.significant(["b", "b", "b", "c"])
    # In 100 provisions the 5% share is 5: a word in 4 of them is still rare.
    large = Rarity.of([*(["rare common"] * 4), *(["common"] * 96)])
    assert large.common == frozenset({"common"})
    assert Rarity.of([]).common == frozenset()


def test_new_wording_made_of_the_laws_common_words_is_not_adopted_and_is_counted() -> None:
    formula = "the provider shall in accordance with this regulation and the"
    scrambled = " ".join(reversed(formula.split()))
    others = [article(f"Recital {n}", scrambled, "proposal") for n in range(3)]
    result = adopt_records([amendment(1, formula)], [*others, article("A", formula)], [])
    assert result.phrases == ()
    assert result.limitations == (
        f"1 run(s) of {MIN_ADOPTED_RUN_WORDS} or more words were not counted: they hold fewer "
        f"than {lineage.MIN_RARE_WORDS} of the law's rare words.",
    )
