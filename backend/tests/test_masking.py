"""Quoted law is not evidence of an organization's contribution."""

from influence.services.masking import mask_quoted_law


def test_every_long_quote_masked_without_moving_original_offsets() -> None:
    law = "Member States shall ensure that every covered person receives information promptly"
    quote = "MEMBER states shall ensure, that every covered person receives information promptly"
    passage = f"We recommend more time. {quote}; also {quote}. Our addition stays."
    result = mask_quoted_law(passage, law)
    assert len(result.text) == len(passage)
    assert len(result.spans) == 2
    assert result.text.startswith("We recommend more time. ")
    assert result.text.endswith(". Our addition stays.")
    for start, end in result.spans:
        assert passage[start:end] == quote
        assert result.text[start:end] == " " * (end - start)
    assert "covered" not in result.text


def test_short_edits_and_unrelated_campaign_text_are_not_masked() -> None:
    assert mask_quoted_law("shall not", "shall").text == "shall not"
    assert (
        mask_quoted_law(
            "one two three four five six seven", "one two three four five six seven"
        ).spans
        == ()
    )
    assert mask_quoted_law("", "anything").spans == ()
    assert mask_quoted_law("Our shared request", "").text == "Our shared request"
    assert (
        mask_quoted_law(
            "A separate campaign used by many different groups and authors", "no quotation"
        ).spans
        == ()
    )


def test_eight_words_and_unicode_offsets() -> None:
    quote = "Établissements publics shall ensure every person receives information"
    passage = "🗺️ " + quote + "; beyond this quotation"
    result = mask_quoted_law(passage, quote)
    assert result.spans == ((3, 3 + len(quote)),)
    assert result.text[3 + len(quote) :] == "; beyond this quotation"
