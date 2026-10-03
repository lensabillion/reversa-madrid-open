"""Link assessment: statuses follow the signals, and a published link is always defensible."""

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from influence.schemas.atlas import (
    Amendment,
    Ask,
    Direction,
    LinkAssessment,
    LinkTier,
    SourceSpan,
    span_matches,
)
from influence.schemas.scoring import MAX_TOKENS, TOKEN_PATTERN, ChangeSpan
from influence.services.assessment import (
    amendment_direction,
    ask_limit_reason,
    assess_link,
    cue_mismatch,
)

FIXTURES = Path(__file__).parent / "fixtures" / "atlas"
SOURCE = "Intro. Providers shall keep logs for at least six months after launch. Outro."
QUOTE = "for at least six months after launch."


@pytest.mark.parametrize("instruction", ["statement", "replace", "delete", "mixed"])
def test_punctuation_heavy_ask_is_insufficient_without_truncating(instruction: str) -> None:
    dotted = "Contents " + "." * 810 + " providers retain logs"
    assert len(dotted.split()) < 120
    assert len(TOKEN_PATTERN.findall(dotted)) > MAX_TOKENS
    text = {
        "statement": dotted,
        "replace": f'replace "{dotted}" with "logs"',
        "delete": f'delete "{dotted}"',
        "mixed": f'add "logs"; delete "{dotted}"',
    }[instruction]
    source = "Préface. " + text + " End."
    ask = _ask(text, start=len("Préface. "))
    before = ask.model_dump_json()
    result = assess_link(_amendment(), ask, source, candidate_id="cand:oversized")
    assert result.status == "insufficient_evidence"
    assert result.candidate_id == "cand:oversized"
    assert result.support_score == 0
    assert result.ask_spans == result.amendment_spans == ()
    assert "800 tokens" in result.limitations[0]
    assert ask.model_dump_json() == before
    assert source[ask.span.start : ask.span.end] == ask.span.text


def test_blank_ask_has_an_explicit_reason() -> None:
    ask = _ask("  ", start=0)
    assert (
        ask_limit_reason(ask)
        == "The ask has no non-whitespace statement or quoted instruction to assess."
    )
    assert assess_link(_amendment(), ask, "  ").status == "insufficient_evidence"


def test_valid_quoted_instruction_uses_its_parsed_bounds() -> None:
    text = "Discussion " + "." * 810 + ' add "logs"'
    ask = _ask(text, start=0)
    assert ask_limit_reason(ask) is None


def _assess(*args: Any, **kwargs: Any) -> LinkAssessment:
    """The assessor with prose publishing on, so these tests can check the whole ladder."""
    return assess_link(*args, publish_prose=True, **kwargs)


def _rows(name: str) -> list[dict[str, object]]:
    lines = (FIXTURES / name).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def _amendment(
    old: str | None = "Providers shall keep logs.",
    new: str = "Providers shall keep logs for at least six months after launch.",
    tabled_on: date | None = date(2099, 3, 1),
) -> Amendment:
    return Amendment(
        amendment_id="am:2099-0001-COD:IMCO:1",
        procedure_id="2099/0001(COD)",
        document_id="doc:parltrack:x",
        stage="committee",
        tabled_on=tabled_on,
        old_text=old,
        new_text=new,
    )


def _ask(
    quote: str = QUOTE,
    direction: Direction = "stricter",
    submitted_at: datetime | None = datetime(2099, 2, 1, tzinfo=UTC),
    start: int | None = None,
) -> Ask:
    begin = SOURCE.index(quote) if start is None else start
    return Ask(
        ask_id="ask:x",
        procedure_id="2099/0001(COD)",
        actor_id="actor:name:hys_feedback.x",
        document_id="doc:hys_feedback:1",
        span=SourceSpan(
            record_id="doc:hys_feedback:1", start=begin, end=begin + len(quote), text=quote
        ),
        direction=direction,
        submitted_at=submitted_at,
        extraction_method="test",
    )


def test_fixture_verdicts_match_the_committed_contract_examples() -> None:
    amendments = {
        row["amendment_id"]: Amendment.model_validate(row) for row in _rows("amendments.jsonl")
    }
    asks = {row["ask_id"]: Ask.model_validate(row) for row in _rows("asks.jsonl")}
    texts = {str(row["document_id"]): str(row["text"]) for row in _rows("document_texts.jsonl")}
    # One fixture example differs on purpose: its ask repeats ten words of the amendment
    # verbatim, which is a copy, where the fixture labelled it reworded.
    differ = {"link:b-am3-labels": ("published", "copied")}
    checked = 0
    for row in _rows("links.jsonl"):
        expected = LinkAssessment.model_validate(row)
        ask = asks[expected.ask_id]
        got = _assess(amendments[expected.amendment_id], ask, texts[ask.document_id])
        assert got.time_eligibility == expected.time_eligibility
        if expected.link_id in differ:
            assert (got.status, got.tier) == differ[expected.link_id]
        else:
            assert (got.status, got.tier) == (expected.status, expected.tier)
        checked += 1
    assert checked == 6


def test_a_supported_copy_is_published_with_exact_quotations() -> None:
    got = _assess(_amendment(), _ask(), SOURCE)
    assert (got.status, got.tier) == ("published", "copied")
    assert got.ask_spans
    assert got.amendment_spans
    assert all(span_matches(span, SOURCE) for span in got.ask_spans)
    assert got.signals["same_direction"] == 1.0


def test_negation_and_opposite_direction_contradict() -> None:
    source = "Providers should not keep logs for at least six months after launch."
    negated = _ask(source, start=0)
    assert _assess(_amendment(), negated, source).status == "contradicted"
    opposite = _assess(_amendment(), _ask(direction="weaker"), SOURCE)
    assert opposite.status == "contradicted"
    assert opposite.support_score == 0.0
    assert opposite.tier is None


@pytest.mark.parametrize(
    ("submitted_at", "tabled_on", "eligibility"),
    [
        (datetime(2099, 2, 1, tzinfo=UTC), date(2099, 3, 1), "ask_first"),
        (datetime(2099, 3, 1, tzinfo=UTC), date(2099, 3, 1), "amendment_first"),
        (datetime(2099, 4, 1, tzinfo=UTC), date(2099, 3, 1), "amendment_first"),
        (None, date(2099, 3, 1), "unknown_date"),
        (datetime(2099, 2, 1, tzinfo=UTC), None, "unknown_date"),
    ],
)
def test_only_an_ask_dated_strictly_before_the_amendment_can_be_an_origin(
    submitted_at: datetime | None, tabled_on: date | None, eligibility: str
) -> None:
    got = _assess(_amendment(tabled_on=tabled_on), _ask(submitted_at=submitted_at), SOURCE)
    assert got.time_eligibility == eligibility
    assert (got.status == "published") == (eligibility == "ask_first")
    if eligibility != "ask_first":
        assert got.status == "unconfirmed"
        assert any("origin" in note for note in got.limitations)


def test_unknown_original_wording_blocks_publication() -> None:
    got = _assess(_amendment(old=None), _ask(), SOURCE)
    assert got.status == "unconfirmed"
    assert any("original wording is unknown" in note for note in got.limitations)


def test_a_quotation_that_is_not_in_its_source_blocks_publication() -> None:
    got = _assess(_amendment(), _ask(), "A completely different document text here.")
    assert got.status == "unconfirmed"
    assert got.ask_spans == ()
    assert any("located exactly" in note for note in got.limitations)


def test_a_tier_the_caller_does_not_allow_stays_unconfirmed() -> None:
    only: frozenset[LinkTier] = frozenset({"reworded"})
    got = _assess(_amendment(), _ask(), SOURCE, publishable=only)
    assert (got.status, got.tier) == ("unconfirmed", "copied")


def test_a_one_word_edit_never_reaches_the_copied_tier() -> None:
    amendment = _amendment(
        old="The authority shall publish it.", new="The authority may publish it."
    )
    quote = "In Article 9, replace 'shall' with 'may': the authority may publish it."
    ask = _ask(quote=quote, direction="weaker", start=0)
    ask = ask.model_copy(
        update={
            "span": SourceSpan(record_id="doc:hys_feedback:1", start=0, end=len(quote), text=quote)
        }
    )
    got = _assess(amendment, ask, quote)
    assert (got.status, got.tier) == ("unconfirmed", "same_direction")
    assert got.signals["short_edit"] == 1.0


def test_unrelated_text_is_insufficient_evidence() -> None:
    quote = "Pizza recipes need patience."
    got = _assess(_amendment(), _ask(quote=quote, start=0), quote)
    assert (got.status, got.tier) == ("insufficient_evidence", None)


def _span(operation: str, text: str) -> ChangeSpan:
    return ChangeSpan.model_validate(
        {"operation": operation, "start": 0, "end": len(text), "text": text}
    )


@pytest.mark.parametrize(
    ("spans", "expected"),
    [
        ([_span("insert", "shall keep")], "stricter"),
        ([_span("insert", "for at least six months")], "stricter"),
        ([_span("delete", "shall"), _span("insert", "may")], "weaker"),
        ([_span("delete", "may")], "stricter"),
        ([_span("insert", "the widget")], "unknown"),
        ([], "unknown"),
    ],
)
def test_direction_is_read_only_from_obligation_cues(
    spans: list[ChangeSpan], expected: str
) -> None:
    assert amendment_direction(spans) == expected


WORDS = st.sampled_from(["shall", "may", "not", "logs", "six", "months", "keep", "the", "."])
TEXTS = st.lists(WORDS, min_size=1, max_size=10).map(" ".join)


@given(old=TEXTS, new=TEXTS, quote=TEXTS)
def test_published_links_always_have_valid_spans_and_an_earlier_ask(
    old: str, new: str, quote: str
) -> None:
    source = f"Lead in. {quote} Trailing."
    got = _assess(_amendment(old=old, new=new), _ask(quote=quote, start=len(" Lead in.")), source)
    assert 0.0 <= got.support_score <= 1.0
    if got.status == "published":
        assert got.time_eligibility == "ask_first"
        assert all(span_matches(span, source) for span in got.ask_spans)
        assert all(span.text for span in got.amendment_spans)


def test_a_reworded_link_is_labelled_but_not_published_unless_the_caller_allows_it() -> None:
    quote = "for at least six months in total"
    source = "Intro. " + quote + " Outro."
    ask = _ask(quote, start=source.index(quote))
    default = _assess(_amendment(), ask, source)
    assert (default.status, default.tier) == ("unconfirmed", "reworded")
    allowed: frozenset[LinkTier] = frozenset({"copied", "reworded"})
    opted_in = _assess(_amendment(), ask, source, publishable=allowed)
    assert (opted_in.status, opted_in.tier) == ("published", "reworded")
    assert opted_in.support_score == default.support_score


PROSE_SOURCE = (
    "We have many concerns about this proposal and its costs. Providers should not be "
    "treated as users, and the rules are unclear. Still, providers shall keep technical logs "
    "for at least six months after the system is placed on the market, as a minimum."
)


def _prose_ask(source: str = PROSE_SOURCE) -> Ask:
    return _ask(source, direction="unknown", start=0)


def test_a_far_away_negation_in_prose_does_not_contradict_a_shared_phrase() -> None:
    """The first real AI Act run marked 99.8 percent of candidates contradicted this way."""
    amendment = _amendment(
        old="Providers shall keep technical logs.",
        new=(
            "Providers shall keep technical logs for at least six months after the system "
            "is placed on the market."
        ),
    )
    got = _assess(_amendment_to(amendment), _prose_ask(), PROSE_SOURCE)
    assert got.status == "published"
    assert got.signals["polarity_conflict"] == 0.0
    assert got.signals["longest_shared_run"] >= 8
    assert all(span_matches(span, PROSE_SOURCE) for span in got.ask_spans)


def _amendment_to(amendment: Amendment) -> Amendment:
    return amendment


def test_a_negation_right_before_the_shared_phrase_does_contradict() -> None:
    source = "Providers shall not keep technical logs for at least six months after launch."
    amendment = _amendment(
        old="Providers shall keep technical logs.",
        new="Providers shall keep technical logs for at least six months after launch.",
    )
    got = _assess(amendment, _ask(source, start=0), source)
    assert got.status == "contradicted"


def test_scattered_common_words_in_prose_are_insufficient_evidence() -> None:
    source = "The logs that providers keep are long and we shall see what months bring."
    got = _assess(_amendment(), _ask(source, start=0), source)
    assert (got.status, got.tier) == ("insufficient_evidence", None)
    assert got.signals["longest_shared_run"] == 0.0


def test_a_rarity_table_lowers_the_support_for_boilerplate() -> None:
    quote = "for at least six months in total"
    source = "Intro. " + quote + " Outro."
    ask = _ask(quote, start=source.index(quote))
    plain = _assess(_amendment(), ask, source)
    boilerplate = {
        "for": 0.01,
        "at": 0.01,
        "least": 0.01,
        "six": 5.0,
        "months": 5.0,
        "after": 5.0,
        "launch": 5.0,
    }
    weighted = _assess(_amendment(), ask, source, rarity=boilerplate)
    assert weighted.support_score != plain.support_score


def test_a_prose_match_is_never_published_by_default() -> None:
    """The first prose run on the AI Act published 7 links, all of them the law's own wording."""
    default = assess_link(_amendment(), _ask(), SOURCE)
    assert (default.status, default.tier) == ("unconfirmed", "copied")
    assert any("not published" in note for note in default.limitations)
    assert _assess(_amendment(), _ask(), SOURCE).status == "published"


def _instruction_ask(text: str) -> Ask:
    return _ask(text, start=0)


def test_a_quoted_instruction_that_repeats_the_inserted_words_is_a_published_copy() -> None:
    text = "Please insert 'for at least six months after launch' into Article 5."
    got = assess_link(_amendment(), _instruction_ask(text), text)
    assert (got.status, got.tier) == ("published", "copied")
    assert "longest_shared_run" not in got.signals
    assert [span.text for span in got.ask_spans] == [
        "insert 'for at least six months after launch'"
    ]
    assert got.amendment_spans


def test_a_quoted_instruction_with_extra_words_is_only_a_rewording() -> None:
    text = "Please insert 'for at least six whole calendar months' into Article 5."
    got = assess_link(_amendment(), _instruction_ask(text), text)
    assert (got.status, got.tier) == ("unconfirmed", "reworded")


# --- Review round 2 regressions (scratchpad review-r2/r1.py to r3.py) ----------------------

LOGS = "keep the logs for ten years after the system is placed on the market"


def _passage_ask(text: str) -> Ask:
    """An ask read from a passage: no declared direction, as `asks_from_passages` makes."""
    return _ask(text, direction="unknown", start=0)


@pytest.mark.parametrize("modal", ["shall", "must"])
def test_a_one_modal_difference_is_contradicted_not_copied(modal: str) -> None:
    amendment = _amendment(old="", new=f"Providers {modal} {LOGS}.")
    text = f"We ask the co-legislators to insert 'Providers may {LOGS}'."
    got = assess_link(amendment, _passage_ask(text), text)
    assert (got.status, got.tier, got.support_score) == ("contradicted", None, 0.0)
    assert any(f"(may, {modal})" in note for note in got.limitations)


def test_a_one_number_difference_cannot_be_a_copy() -> None:
    amendment = _amendment(
        old="",
        new="The notification shall be made at least 30 days before the system is placed "
        "on the market.",
    )
    text = (
        "Add 'The notification shall be made at least 90 days before the system is placed "
        "on the market'."
    )
    got = assess_link(amendment, _passage_ask(text), text)
    assert (got.status, got.tier) == ("unconfirmed", "reworded")
    assert any("(30, 90)" in note for note in got.limitations)


def test_a_different_article_number_in_a_replacement_cannot_be_a_copy() -> None:
    amendment = _amendment(
        old="Article 5(2) applies to all providers placing systems on the market.",
        new="Article 5(1) applies to all providers placing systems on the market within the Union.",
    )
    text = (
        "replace 'Article 5(2) applies to all providers placing systems on the market.' with "
        "'Article 5(3) applies to all providers placing systems on the market within the Union.'"
    )
    got = assess_link(amendment, _passage_ask(text), text)
    assert got.status != "published"
    assert got.tier == "reworded"


@pytest.mark.parametrize(
    ("old", "new", "text", "sentence"),
    [
        (
            "",
            f"Providers shall {LOGS}.",
            f"Intro. We strongly oppose any proposal to insert 'Providers shall {LOGS}'. Thanks.",
            f"We strongly oppose any proposal to insert 'Providers shall {LOGS}'.",
        ),
        (
            f"Providers shall {LOGS}.",
            "",
            f"Please do not delete 'Providers shall {LOGS}'.",
            f"Please do not delete 'Providers shall {LOGS}'.",
        ),
    ],
)
def test_an_instruction_the_ask_opposes_is_never_published(
    old: str, new: str, text: str, sentence: str
) -> None:
    got = assess_link(_amendment(old=old, new=new), _passage_ask(text), text)
    assert (got.status, got.tier) == ("unconfirmed", "copied")
    assert [span.text for span in got.ask_spans] == [sentence]
    assert all(span_matches(span, text) for span in got.ask_spans)
    assert any("opposition cue" in note for note in got.limitations)


def test_an_opposed_instruction_with_no_tier_is_insufficient_evidence() -> None:
    text = "We reject any plan to insert 'unrelated wording entirely here'."
    got = assess_link(_amendment(), _passage_ask(text), text)
    assert got.status == "insufficient_evidence"
    assert any("opposition cue" in note for note in got.limitations)


@pytest.mark.parametrize(
    ("new", "inserted"),
    [
        (f"Providers shall {LOGS}.", f"Providers shall not {LOGS}"),
        (
            "This Regulation shall apply to systems used for military purposes.",
            "This Regulation shall not apply to systems used for military purposes",
        ),
        (
            "This Regulation shall apply to systems used for military purposes.",
            "This Regulation shall apply only to systems not used for military purposes",
        ),
    ],
)
def test_the_same_wording_with_its_sense_reversed_is_contradicted(new: str, inserted: str) -> None:
    text = f"Insert '{inserted}'."
    got = assess_link(_amendment(old="", new=new), _passage_ask(text), text)
    assert (got.status, got.tier, got.support_score) == ("contradicted", None, 0.0)
    assert got.amendment_spans
    assert got.signals["polarity_conflict"] == 1.0


def test_a_negation_with_unrelated_wording_stays_insufficient_evidence() -> None:
    text = "Insert 'nothing here is not alike at all'."
    got = assess_link(_amendment(old="", new=f"Providers shall {LOGS}."), _passage_ask(text), text)
    assert got.status == "insufficient_evidence"
    assert got.signals["polarity_conflict"] == 0.0


def test_an_apostrophe_inside_the_quote_leaves_the_ask_unpublished_prose() -> None:
    text = "Insert 'the provider's obligation shall not apply' to SMEs."
    amendment = _amendment(old="", new="the provider's obligation shall not apply")
    got = assess_link(amendment, _passage_ask(text), text)
    assert got.status != "published"
    assert "longest_shared_run" in got.signals


def test_matching_cues_still_publish_a_copy() -> None:
    amendment = _amendment(old="", new=f"Providers shall {LOGS} within 30 days.")
    text = f"Insert 'Providers shall {LOGS} within 30 days'."
    got = assess_link(amendment, _passage_ask(text), text)
    assert (got.status, got.tier) == ("published", "copied")


@pytest.mark.parametrize(
    ("amendment", "ask", "expected"),
    [
        ((("insert", "shall keep 30"),), (("insert", "may keep 30"),), ("may", "shall")),
        ((("insert", "keep 30"),), (("insert", "keep 90"),), ("30", "90")),
        ((("insert", "keep"), ("delete", "may")), (("insert", "keep"),), ()),
        ((("delete", "not"),), (("delete", "never"),), ("never", "not")),
        ((("insert", "keep logs"),), (("insert", "keep logs"),), ()),
    ],
)
def test_cue_mismatch_compares_operations_both_sides_perform(
    amendment: tuple[tuple[str, str], ...],
    ask: tuple[tuple[str, str], ...],
    expected: tuple[str, ...],
) -> None:
    mine = [_span(operation, text) for operation, text in amendment]
    theirs = [_span(operation, text) for operation, text in ask]
    assert cue_mismatch(mine, theirs) == expected
    assert cue_mismatch(theirs, mine) == expected
