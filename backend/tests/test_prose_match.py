"""Lineage word normalization retains exact Unicode source offsets."""

from influence.services.prose_match import words_of


def test_words_are_folded_alphanumeric_tokens_with_exact_offsets() -> None:
    text = "High-risk AI: Article 5(1), 30%."
    words = words_of(text)
    assert [word.text for word in words] == ["high", "risk", "ai", "article", "5", "1", "30%"]
    assert all(text[word.start : word.end].casefold() == word.text for word in words)
