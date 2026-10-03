"""Quoted law is not evidence of an organization's contribution."""

from influence.services.masking import MaskedPassage, QuotedLaw


def _mask(passage: str, *law: str) -> MaskedPassage:
    return QuotedLaw(law).mask(passage)


def test_every_long_quote_masked_without_moving_original_offsets() -> None:
    law = "Member States shall ensure that every covered person receives information promptly"
    quote = "MEMBER states shall ensure, that every covered person receives information promptly"
    passage = f"We recommend more time. {quote}; also {quote}. Our addition stays."
    result = _mask(passage, law)
    assert len(result.text) == len(passage)
    assert len(result.spans) == 2
    assert result.text.startswith("We recommend more time. ")
    assert result.text.endswith(". Our addition stays.")
    for start, end in result.spans:
        assert passage[start:end] == quote
        assert result.text[start:end] == " " * (end - start)
    assert "covered" not in result.text


def test_short_edits_and_unrelated_campaign_text_are_not_masked() -> None:
    assert _mask("shall not", "shall").text == "shall not"
    assert (
        _mask("one two three four five six seven", "one two three four five six seven").spans == ()
    )
    assert _mask("", "anything").spans == ()
    assert _mask("Our shared request", "").text == "Our shared request"
    assert _mask("Our shared request").text == "Our shared request"
    assert (
        _mask("A separate campaign used by many different groups and authors", "no quotation").spans
        == ()
    )


def test_eight_words_and_unicode_offsets() -> None:
    quote = "Établissements publics shall ensure every person receives information"
    passage = "🗺️ " + quote + "; beyond this quotation"
    result = _mask(passage, quote)
    assert result.spans == ((3, 3 + len(quote)),)
    assert result.text[3 + len(quote) :] == "; beyond this quotation"


def test_a_quotation_is_indexed_inside_one_provision_never_across_two() -> None:
    """Provisions are indexed apart: the end of one and the start of the next are no phrase."""
    first = "Providers shall register the system before use"
    second = "and authorities may inspect every record they keep"
    across = "the system before use and authorities may inspect"
    assert _mask(across, first + " " + second).spans != ()
    assert _mask(across, first, second).spans == ()
    assert _mask(second, first, second).spans == ((0, len(second)),)
