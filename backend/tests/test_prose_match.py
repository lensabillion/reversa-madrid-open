"""Prose matching: only phrases count, rare words weigh more, a distant negation is no conflict."""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from influence.services.prose_match import (
    MIN_RUN_WORDS,
    match_prose,
    negation_conflict,
    rarity_weights,
    weight_of,
    words_of,
)


def _w(text: str) -> list[str]:
    return [word.text for word in words_of(text)]


def test_words_are_folded_alphanumeric_tokens_with_exact_offsets() -> None:
    text = "High-risk AI: Article 5(1), 30%."
    words = words_of(text)
    assert [word.text for word in words] == ["high", "risk", "ai", "article", "5", "1", "30%"]
    assert all(text[word.start : word.end].casefold() == word.text for word in words)


def test_rarity_gives_common_words_little_weight_and_unseen_words_the_most() -> None:
    table = rarity_weights(["shall keep logs", "shall keep records", "shall publish a summary"])
    assert table["shall"] < table["logs"] < table["summary"] + 1e-9
    assert table["shall"] == pytest.approx(math.log(4 / 3.5))
    assert weight_of("zebra", table) == max(table.values())
    assert weight_of("shall", table) == table["shall"]
    assert weight_of("anything", None) == 1.0
    assert weight_of("anything", {}) == 1.0


def test_a_verbatim_copy_is_fully_covered_by_one_run() -> None:
    amendment = _w("for at least six months after the system is placed on the market")
    passage = _w("We ask that logs be kept for at least six months after the system is placed")
    match = match_prose(amendment, passage)
    assert match.longest == 10
    assert match.coverage == pytest.approx(10 / 13)
    assert len(match.runs) == 1


def test_scattered_common_words_are_not_a_match() -> None:
    amendment = _w("providers shall keep the logs for six months")
    passage = _w("the providers know that logs are not kept for months and we shall see")
    match = match_prose(amendment, passage)
    assert (match.coverage, match.longest, match.runs) == (0.0, 0, ())


def test_runs_are_taken_longest_first_and_each_amendment_word_once() -> None:
    amendment = _w("alpha beta gamma delta epsilon zeta")
    passage = _w("alpha beta gamma delta and then epsilon zeta alpha beta gamma")
    match = match_prose(amendment, passage)
    assert [run.length for run in match.runs] == [4]
    assert match.coverage == pytest.approx(4 / 6)


def test_rare_words_weigh_more_than_boilerplate() -> None:
    texts = ["high risk ai systems"] * 9 + ["high risk ai systems with extra rare phrase here"]
    rarity = rarity_weights(texts)
    boilerplate = match_prose(
        _w("high risk ai systems rare phrase here"), _w("high risk ai systems"), rarity
    )
    unweighted = match_prose(
        _w("high risk ai systems rare phrase here"), _w("high risk ai systems")
    )
    assert boilerplate.coverage < unweighted.coverage
    assert boilerplate.coverage < 0.2


def test_a_negated_sentence_on_one_side_only_is_a_conflict() -> None:
    amendment = "Providers shall keep logs for six months."
    negated = "We think providers shall not keep logs for six months."
    assert negation_conflict(amendment, 14, negated, 28)
    assert negation_conflict(negated, 28, amendment, 14)
    assert not negation_conflict(negated, 28, negated, 28)
    assert not negation_conflict(amendment, 14, amendment, 14)


def test_a_negation_in_another_sentence_of_the_passage_is_no_conflict() -> None:
    passage = "This is not a problem. Providers shall keep logs for six months. It is fine."
    amendment = "Providers shall keep logs for six months."
    assert not negation_conflict(amendment, 14, passage, passage.index("keep"))


def test_sentences_end_at_punctuation_or_a_line_feed() -> None:
    text = "First no thing.\N{LINE FEED}Second one; third one! Fourth"
    assert negation_conflict(text, text.index("no"), "plain words", 0)
    assert not negation_conflict(text, text.index("Second"), "plain words", 0)
    assert not negation_conflict(text, text.index("Fourth"), "plain words", 0)


def test_nothing_to_match_scores_zero() -> None:
    assert match_prose([], _w("some passage text here")).coverage == 0.0
    assert match_prose(_w("some changed words here"), []).coverage == 0.0
    assert match_prose([], []).longest == 0


def test_a_zero_weight_amendment_has_no_coverage() -> None:
    assert (
        match_prose(_w("a b c d"), _w("a b c d"), {"a": 0.0, "b": 0.0, "c": 0.0, "d": 0.0}).coverage
        == 0.0
    )


WORDS = st.sampled_from(["shall", "may", "not", "logs", "keep", "six", "months", "the", "of"])


@given(
    amendment=st.lists(WORDS, max_size=14),
    passage=st.lists(WORDS, max_size=20),
    rarity=st.none() | st.dictionaries(WORDS, st.floats(0.01, 10), max_size=9),
)
def test_runs_are_real_disjoint_phrases_and_coverage_is_a_fraction(
    amendment: list[str], passage: list[str], rarity: dict[str, float] | None
) -> None:
    match = match_prose(amendment, passage, rarity)
    assert 0.0 <= match.coverage <= 1.0
    used: set[int] = set()
    for run in match.runs:
        assert run.length >= MIN_RUN_WORDS
        mine = range(run.amendment_first, run.amendment_first + run.length)
        assert not used & set(mine)
        used |= set(mine)
        assert (
            amendment[run.amendment_first : run.amendment_first + run.length]
            == passage[run.passage_first : run.passage_first + run.length]
        )
