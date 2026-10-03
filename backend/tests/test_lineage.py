"""Verbatim adoption: new wording of the final act, the amendments that carry it, and credit."""

from datetime import date
from itertools import pairwise

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
    # "providers shall keep logs" stood in the proposal, but followed by other words: the
    # windows that join it to the new wording are new, so the stretch of the law starts there.
    assert phrase.text == "providers shall keep logs " + NEW
    assert phrase.words == 24
    assert phrase.phrase_id.startswith("phrase:")
    (span,) = phrase.final_spans
    assert span_matches(span, FINAL.text)
    (adoption,) = result.adoptions
    assert (adoption.adopted_words, adoption.longest_run, adoption.inserted_words) == (24, 24, 20)
    assert adoption.new_words == 24
    assert (result.amendments, result.amendments_adopting) == (1, 1)
    counts = result.counts(documents_read=4, documents_with_origin=1)
    assert (counts.adopted_phrases, counts.documents_read, counts.documents_with_origin) == (
        1,
        4,
        1,
    )
    # "The" also stands in a new window of the final act, but no amendment carried it.
    assert (counts.changed_units, counts.linked_units) == (25, 24)
    assert result.counts().documents_read is None


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


def test_overlapping_runs_are_one_stretch_of_the_law_never_two_phrases() -> None:
    """Regression: a sub-run of a longer run used to be a second phrase, credited again."""
    long_new = sentence("novel", 30)
    final = article("Article 1", "The providers shall keep logs. " + long_new)
    whole = amendment(1, long_new, authors=("actor:mep:1",))
    part = amendment(2, sentence("novel", 15), authors=("actor:mep:2",))
    result = adopt_records([whole, part], [PROPOSAL, final], [mep(1, "PPE"), mep(2, "S&D")])
    (phrase,) = result.phrases
    assert phrase.words == 30
    assert phrase.holders == ("actor:mep:1", "actor:mep:2")
    assert phrase.joint
    by_id = {credit.holder_id: credit for credit in result.credits}
    # Each holder has the one stretch in full, flagged joint; nobody has it twice.
    assert {key: (c.phrases, c.joint_phrases) for key, c in by_id.items()} == {
        "actor:mep:1": (1, 1),
        "actor:mep:2": (1, 1),
        "PPE": (1, 1),
        "S&D": (1, 1),
    }
    assert {a.amendment_id: a.phrase_ids for a in result.adoptions} == {
        whole.amendment_id: (phrase.phrase_id,),
        part.amendment_id: (phrase.phrase_id,),
    }


def test_the_same_wording_in_two_amendments_is_credited_whole_to_every_holder() -> None:
    actors = [mep(1, "PPE"), mep(2, "PPE"), mep(3, "S&D")]
    amendments = [
        amendment(1, NEW, authors=("actor:mep:1", "actor:mep:2")),
        amendment(2, NEW, authors=("actor:mep:3",), stage="plenary"),
        amendment(3, sentence("lost"), authors=("actor:mep:3",)),
    ]
    result = adopt_records(amendments, [PROPOSAL, FINAL], actors)
    assert len(result.phrases) == 1
    assert len(result.adoptions) == 2
    assert {adoption.stage for adoption in result.adoptions} == {"committee", "plenary"}
    assert {a.amendment_id: a.author_groups for a in result.adoptions} == {
        "am:2099-0001-COD:IMCO:1": ("PPE", "PPE"),
        "am:2099-0001-COD:IMCO:2": ("S&D",),
    }
    by_name = {(credit.holder_kind, credit.name): credit for credit in result.credits}
    # No fractional credit: every holder has the whole phrase, and it is joint.
    for key in [("mep", "Member 1"), ("mep", "Member 3"), ("group", "PPE"), ("group", "S&D")]:
        assert (by_name[key].phrases, by_name[key].joint_phrases) == (1, 1)
    # "N of M": Member 3 tabled two amendments, one reached the law.
    assert (by_name[("mep", "Member 3")].amendments, by_name[("mep", "Member 3")].rate) == (1, 0.5)
    assert (by_name[("group", "PPE")].amendments, by_name[("group", "PPE")].amendments_tabled) == (
        1,
        1,
    )
    # Members first, ranked by rate per amendment tabled, then groups.
    assert [c.name for c in result.credits] == ["Member 1", "Member 2", "Member 3", "PPE", "S&D"]


def test_an_amendment_without_any_author_is_credited_to_the_committee_text() -> None:
    result = adopt_records([amendment(1, NEW, authors=())], [PROPOSAL, FINAL], [])
    (credit,) = result.credits
    assert (credit.holder_id, credit.holder_kind, credit.phrases) == (
        COMMITTEE_TEXT,
        "committee_text",
        1,
    )
    assert (credit.amendments, credit.amendments_tabled) == (1, 1)
    assert result.phrases_without_group == 1


def test_an_authorless_duplicate_names_its_tabler_and_never_splits_the_credit() -> None:
    """Regression: an authorless plenary duplicate was credited to "Committee text"."""
    committee = amendment(3, NEW, authors=("actor:mep:1",))
    named = amendment(4, NEW, authors=(), stage="plenary").model_copy(
        update={"author_names": ("on behalf of the Verts/ALE Group",)}
    )
    result = adopt_records([committee, named], [PROPOSAL, FINAL], [mep(1, "EPP")])
    by_id = {credit.holder_id: credit for credit in result.credits}
    assert set(by_id) == {"actor:mep:1", "EPP", "Verts/ALE"}
    assert by_id["Verts/ALE"].holder_kind == "group"
    assert all(credit.phrases == 1 for credit in result.credits)
    unresolved = named.model_copy(update={"author_names": ("A. Nonymous",)})
    by_name = {c.holder_id: c for c in adopt_records([unresolved], [PROPOSAL, FINAL], []).credits}
    assert by_name["name:A. Nonymous"].holder_kind == "unresolved"
    # Committee text is credited only when no carrier of the phrase names an author.
    anonymous = named.model_copy(update={"author_names": ()})
    merged = adopt_records([committee, anonymous], [PROPOSAL, FINAL], [mep(1, "EPP")])
    assert {credit.holder_id for credit in merged.credits} == {"actor:mep:1", "EPP"}


def test_a_committee_amendment_and_its_plenary_retabling_count_once_per_tabler() -> None:
    committee = amendment(1, NEW, authors=("actor:mep:1",))
    plenary = amendment(2, NEW, authors=("actor:mep:1",), stage="plenary")
    result = adopt_records([committee, plenary], [PROPOSAL, FINAL], [mep(1, "PPE")])
    (member, group) = result.credits
    assert (member.phrases, member.joint_phrases) == (1, 0)
    assert (member.amendments, member.amendments_tabled) == (1, 1)
    assert (group.amendments, group.amendments_tabled) == (1, 1)


def test_an_author_with_no_known_group_credits_no_group_and_is_counted_apart() -> None:
    result = adopt_records([amendment(1, NEW, authors=("actor:mep:9",))], [PROPOSAL, FINAL], [])
    names = {(credit.holder_kind, credit.name) for credit in result.credits}
    assert names == {("mep", "actor:mep:9")}
    assert result.phrases_without_group == 1
    assert result.counts().phrases_without_group == 1
    assert any("no holder with a known political group" in n for n in result.limitations)
    ungrouped = adopt_records(
        [amendment(1, NEW, authors=("actor:mep:4",))], [PROPOSAL, FINAL], [mep(4, None)]
    )
    assert {c.holder_kind for c in ungrouped.credits} == {"mep"}
    assert ungrouped.adoptions[0].author_groups == (None,)


def test_wording_in_several_final_places_is_one_phrase_per_place() -> None:
    final = [article(f"Copy {number}", NEW) for number in range(5)]
    # Enough other provisions that five copies stay under the law's rarity share.
    others = [article(f"Other {n}", sentence("other", 3, 3 * n)) for n in range(120)]
    result = adopt_records([amendment(1, NEW)], [PROPOSAL, *final, *others], [])
    assert len(result.phrases) == 5
    assert {phrase.final_spans[0].record_id for phrase in result.phrases} == {
        f"art:final_act:Copy-{number}" for number in range(5)
    }
    assert all(len(phrase.final_spans) == 1 for phrase in result.phrases)


def test_a_rewritten_sentence_is_adopted_whole_not_cut_at_the_words_it_kept() -> None:
    """Regression: a 43-word rewritten sentence used to be credited 17 words."""
    old = (
        "Providers shall ensure that the system is safe and that the risks of the system are "
        "assessed."
    )
    new = (
        "Providers shall ensure that the system is subject to an independent conformity "
        "assessment of the fundamental rights impact and that the results of the assessment are "
        "published by the national supervisory authority in a register that the public can "
        "consult free of charge."
    )
    proposal, final = article("Article 9", old, "proposal"), article("Article 9", new)
    result = adopt_records([amendment(1, new, old=old)], [proposal, final], [])
    (phrase,) = result.phrases
    assert phrase.words == len(new.split()) == 43
    (adoption,) = result.adoptions
    assert adoption.adopted_words == 43
    assert adoption.inserted_words < 43


def test_a_law_without_a_final_act_or_a_proposal_is_unknown_not_empty() -> None:
    no_final = adopt_records([amendment(1, NEW)], [PROPOSAL], [])
    assert (no_final.status, no_final.phrases, no_final.credits) == ("unknown", (), ())
    assert no_final.reason is not None
    assert "final act" in no_final.reason
    counts = no_final.counts()
    assert (counts.amendments, counts.amendments_adopting) == (1, None)
    assert counts.adopted_phrases is None
    assert (counts.changed_units, counts.linked_units) == (None, None)
    # Regression: without the proposal, the proposal's own wording re-tabled counted as adopted.
    old = sentence("old")
    no_proposal = adopt_records([amendment(5, old, old=None)], [article("Article 1", old)], [])
    assert no_proposal.status == "unknown"
    assert no_proposal.reason is not None
    assert "proposal" in no_proposal.reason
    assert no_proposal.amendments_adopting is None


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
def test_every_quotation_is_exact_and_no_stretch_of_the_law_is_credited_twice(
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
    if not proposal or not any(final):
        assert result.status == "unknown"
        assert result.counts().adopted_phrases is None
        return
    texts = {item.article_id: item.text for item in articles}
    stretches: dict[str, list[tuple[int, int]]] = {}
    for phrase in result.phrases:
        assert phrase.words >= MIN_ADOPTED_RUN_WORDS
        (span,) = phrase.final_spans
        assert span_matches(span, texts[span.record_id])
        stretches.setdefault(span.record_id, []).append((span.start, span.end))
    for spans in stretches.values():
        ordered = sorted(spans)
        assert all(left[1] < right[0] for left, right in pairwise(ordered))
    known = {phrase.phrase_id for phrase in result.phrases}
    assert all(set(adoption.phrase_ids) <= known for adoption in result.adoptions)
    assert result.amendments_adopting == len(result.adoptions) <= result.amendments
    for credit in result.credits:
        assert isinstance(credit.phrases, int)
        assert credit.phrases <= len(result.phrases)
        assert credit.amendments <= credit.amendments_tabled
    counts = result.counts()
    assert counts.linked_units is not None
    assert counts.changed_units is not None
    assert counts.linked_units <= counts.changed_units


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
