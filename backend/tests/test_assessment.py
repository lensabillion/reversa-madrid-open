"""Link assessment: statuses follow the signals, and a published link is always defensible."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

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
from influence.services.assessment import amendment_direction, ask_limit_reason, assess_link

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
    # Two fixture examples differ on purpose. The fixture publishes both, but their overlap
    # (0.64 and 0.58) is under the calibrated copied threshold of 0.75, and the reworded tier
    # is labelled and not published because it missed its precision floor on LobbyPlag.
    differ = {
        "link:a-am1-makers": ("unconfirmed", "reworded"),
        "link:b-am3-labels": ("unconfirmed", "reworded"),
    }
    checked = 0
    for row in _rows("links.jsonl"):
        expected = LinkAssessment.model_validate(row)
        ask = asks[expected.ask_id]
        got = assess_link(amendments[expected.amendment_id], ask, texts[ask.document_id])
        assert got.time_eligibility == expected.time_eligibility
        if expected.link_id in differ:
            assert (got.status, got.tier) == differ[expected.link_id]
        else:
            assert (got.status, got.tier) == (expected.status, expected.tier)
        checked += 1
    assert checked == 6


def test_a_supported_copy_is_published_with_exact_quotations() -> None:
    got = assess_link(_amendment(), _ask(), SOURCE)
    assert (got.status, got.tier) == ("published", "copied")
    assert got.ask_spans
    assert got.amendment_spans
    assert all(span_matches(span, SOURCE) for span in got.ask_spans)
    assert got.signals["same_direction"] == 1.0


def test_negation_and_opposite_direction_contradict() -> None:
    source = "Providers should not keep logs for at least six months after launch."
    negated = _ask(source, start=0)
    assert assess_link(_amendment(), negated, source).status == "contradicted"
    opposite = assess_link(_amendment(), _ask(direction="weaker"), SOURCE)
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
    got = assess_link(_amendment(tabled_on=tabled_on), _ask(submitted_at=submitted_at), SOURCE)
    assert got.time_eligibility == eligibility
    assert (got.status == "published") == (eligibility == "ask_first")
    if eligibility != "ask_first":
        assert got.status == "unconfirmed"
        assert any("origin" in note for note in got.limitations)


def test_unknown_original_wording_blocks_publication() -> None:
    got = assess_link(_amendment(old=None), _ask(), SOURCE)
    assert got.status == "unconfirmed"
    assert any("original wording is unknown" in note for note in got.limitations)


def test_a_quotation_that_is_not_in_its_source_blocks_publication() -> None:
    got = assess_link(_amendment(), _ask(), "A completely different document text here.")
    assert got.status == "unconfirmed"
    assert got.ask_spans == ()
    assert any("located exactly" in note for note in got.limitations)


def test_a_tier_the_caller_does_not_allow_stays_unconfirmed() -> None:
    only: frozenset[LinkTier] = frozenset({"reworded"})
    got = assess_link(_amendment(), _ask(), SOURCE, publishable=only)
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
    got = assess_link(amendment, ask, quote)
    assert (got.status, got.tier) == ("unconfirmed", "same_direction")
    assert got.signals["short_edit"] == 1.0


def test_unrelated_text_is_insufficient_evidence() -> None:
    quote = "Pizza recipes need patience."
    got = assess_link(_amendment(), _ask(quote=quote, start=0), quote)
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
    got = assess_link(
        _amendment(old=old, new=new), _ask(quote=quote, start=len(" Lead in.")), source
    )
    assert 0.0 <= got.support_score <= 1.0
    if got.status == "published":
        assert got.time_eligibility == "ask_first"
        assert all(span_matches(span, source) for span in got.ask_spans)
        assert all(span.text for span in got.amendment_spans)


def test_a_reworded_link_is_labelled_but_not_published_unless_the_caller_allows_it() -> None:
    sentence = "Providers shall keep logs for at least six months after launch."
    ask = _ask(sentence)
    default = assess_link(_amendment(), ask, SOURCE)
    assert (default.status, default.tier) == ("unconfirmed", "reworded")
    allowed: frozenset[LinkTier] = frozenset({"copied", "reworded"})
    opted_in = assess_link(_amendment(), ask, SOURCE, publishable=allowed)
    assert (opted_in.status, opted_in.tier) == ("published", "reworded")
    assert opted_in.support_score == default.support_score
