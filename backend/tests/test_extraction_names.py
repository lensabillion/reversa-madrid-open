"""Name normalisation: what varies between spellings of one body is stripped, order kept."""

import pytest

from influence.extraction.names import normalise, token_set_ratio, tokenise


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Example Tech GmbH", "example tech"),
        ("The European Association of Example, e.V.", "association example"),
        ("EXAMPLE-TECH  (Brussels)", "example tech brussels"),
        ("The", ""),
    ],
)
def test_normalisation_strips_legal_suffixes_punctuation_and_filler(
    raw: str, expected: str
) -> None:
    assert normalise(raw) == expected


def test_tokenise_keeps_order_so_the_normalised_key_is_stable() -> None:
    assert tokenise("Example Tech Ltd") == ("example", "tech")


def test_token_set_ratio_ignores_word_order_and_is_zero_when_nothing_remains() -> None:
    assert token_set_ratio("Alpha Beta Systems", "Systems Beta Alpha") == 1.0
    assert token_set_ratio("The European", "Alpha") == 0.0
