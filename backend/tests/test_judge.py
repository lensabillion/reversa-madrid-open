"""The meaning judge without a model: a fake scorer stands in for the reranker."""

import math
from collections.abc import Sequence
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from influence.services.embedding import EmbeddingCache
from influence.services.judge import (
    INSTRUCTION,
    MAX_FIELD_CHARS,
    PREFIX,
    SUFFIX,
    JudgeError,
    amendment_query,
    best_sentence,
    change_query,
    clipped_fields,
    judge_pairs,
    judge_prompt,
    probability,
)


class MagicJudge:
    """Says yes (+5) when the document part of the prompt holds the word "magic", else no (-5)."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, prompts: Sequence[str]) -> list[float]:
        self.calls.append(list(prompts))
        documents = [prompt.split("<Document>:")[1].casefold() for prompt in prompts]
        return [5.0 if "magic" in document else -5.0 for document in documents]


def test_the_amendment_is_shown_as_old_to_new_or_as_new_alone() -> None:
    assert amendment_query("keep logs", "keep logs for a year") == (
        "Amendment: keep logs -> keep logs for a year"
    )
    assert amendment_query(None, "keep logs") == (
        "Amendment, new wording (original unknown): keep logs"
    )
    assert amendment_query("", "added") == "Amendment:  -> added"


def test_a_long_field_is_cut_so_the_question_stays_whole() -> None:
    query = amendment_query("x" * 5_000, "y")
    assert len(query) < MAX_FIELD_CHARS + 60
    assert "x" * MAX_FIELD_CHARS + " ..." in query
    assert judge_prompt("o", "n", "d" * 9_000).endswith(" ..." + SUFFIX)


def test_the_change_query_names_only_the_words_added_and_removed() -> None:
    assert change_query("keep logs", "keep logs for a year") == "Amendment adds: for a year"
    assert change_query("keep the old logs", "keep logs") == "Amendment removes: the old"
    assert change_query("a shall b", "a may b") == "Amendment adds: may; removes: shall"
    assert change_query("same text", "same text") == "Amendment makes no change"
    assert change_query(None, "new text") == amendment_query(None, "new text")
    # Text past the edit scorer's bounds falls back to the old -> new form.
    assert change_query("word " * 900, "other") == amendment_query("word " * 900, "other")


def test_the_prompt_can_show_the_change_instead_of_the_whole_amendment() -> None:
    whole = judge_prompt("a b c", "a b d", "doc")
    changes = judge_prompt("a b c", "a b d", "doc", changes_only=True)
    assert "<Query>: Amendment: a b c -> a b d\n" in whole
    assert "<Query>: Amendment adds: d; removes: c\n" in changes
    pairs = [("a b c", "a b d", "magic")]
    assert judge_pairs(pairs, MagicJudge(), model_id="m", changes_only=True)[0] > 0.9


def test_the_evidence_can_be_chosen_with_the_change_prompt() -> None:
    evidence = best_sentence("a", "a b", PASSAGE, MagicJudge(), model_id="m", changes_only=True)
    assert evidence.text == "The lobbyist wants the magic change here."


def test_the_prompt_is_the_models_trained_format() -> None:
    prompt = judge_prompt("a", "b", "the passage")
    assert prompt.startswith(PREFIX)
    assert prompt.endswith(SUFFIX)
    assert (
        f"<Instruct>: {INSTRUCTION}\n<Query>: Amendment: a -> b\n<Document>: the passage" in prompt
    )
    assert "answer can only be" in prompt


def test_probability_is_the_logistic_of_the_log_odds_and_never_overflows() -> None:
    assert probability(0.0) == 0.5
    assert probability(math.log(3)) == pytest.approx(0.75)
    assert probability(1e6) == pytest.approx(1.0)
    assert probability(-1e6) == pytest.approx(0.0, abs=1e-12)
    assert probability(2.0) + probability(-2.0) == pytest.approx(1.0)


@given(st.floats(-1e3, 1e3), st.floats(-1e3, 1e3))
def test_probability_is_in_range_and_increases_with_the_log_odds(low: float, high: float) -> None:
    low, high = sorted((low, high))
    assert 0.0 <= probability(low) <= probability(high) <= 1.0


def test_every_cut_field_is_counted_for_both_prompt_forms() -> None:
    long = "x" * (MAX_FIELD_CHARS + 1)
    fits = "y" * MAX_FIELD_CHARS
    assert clipped_fields(None, fits, fits) == 0
    assert clipped_fields(None, long, "passage") == 1
    assert clipped_fields(long, long, long) == 3
    # The change form shows only the added and removed words, so a long unchanged
    # paragraph is not cut there, but a long added run is.
    paragraph = "word " * 400
    assert clipped_fields(paragraph, paragraph + "new", "p") == 2
    assert clipped_fields(paragraph, paragraph + "new", "p", changes_only=True) == 0
    assert clipped_fields("a", "a " + long, "p", changes_only=True) == 1
    # Where the change form falls back to old -> new, so does the count.
    assert clipped_fields(None, long, "p", changes_only=True) == 1
    too_many = "w " * 900
    assert clipped_fields(too_many, too_many + "z", "p", changes_only=True) == 2


def test_pairs_come_back_in_order_each_distinct_prompt_scored_once_in_batches() -> None:
    judge = MagicJudge()
    pairs = [
        (None, "n", "plain text"),
        (None, "n", "magic text"),
        (None, "n", "plain text"),
        ("o", "n", "more magic"),
    ]
    chances = judge_pairs(pairs, judge, model_id="m", batch_size=2)
    assert [round(c, 3) for c in chances] == [0.007, 0.993, 0.007, 0.993]
    sent = [prompt for batch in judge.calls for prompt in batch]
    assert len(sent) == 3
    assert all(len(batch) <= 2 for batch in judge.calls)


def test_a_cached_pair_is_not_scored_again_and_the_model_id_keys_the_cache(tmp_path: Path) -> None:
    cache = EmbeddingCache(tmp_path / "judgements.sqlite3")
    judge = MagicJudge()
    first = judge_pairs([(None, "n", "magic")], judge, model_id="m1", cache=cache)
    assert judge_pairs([(None, "n", "magic")], judge, model_id="m1", cache=cache) == first
    assert len(judge.calls) == 1
    judge_pairs([(None, "n", "magic")], judge, model_id="m2", cache=cache)
    assert len(judge.calls) == 2


def test_a_scorer_that_returns_the_wrong_count_or_a_non_finite_score_is_an_error() -> None:
    with pytest.raises(JudgeError, match="Asked for 2 scores, got 1"):
        judge_pairs(
            [(None, "n", "a"), (None, "n", "b")],
            lambda prompts: [0.0],
            model_id="m",
            batch_size=2,
        )
    with pytest.raises(JudgeError, match="non-finite"):
        judge_pairs([(None, "n", "a")], lambda prompts: [math.nan], model_id="m")
    with pytest.raises(ValueError, match="batch_size"):
        judge_pairs([(None, "n", "a")], MagicJudge(), model_id="m", batch_size=0)


PASSAGE = "Intro words come first. The lobbyist wants the magic change here. Closing words follow."


def test_the_evidence_is_the_best_sentence_with_its_exact_offsets() -> None:
    evidence = best_sentence(None, "n", PASSAGE, MagicJudge(), model_id="m")
    assert evidence.text == "The lobbyist wants the magic change here."
    assert PASSAGE[evidence.start : evidence.end] == evidence.text
    assert evidence.probability == pytest.approx(0.993, abs=1e-3)


def test_with_no_better_sentence_the_first_wins_and_offsets_survive_unicode() -> None:
    text = "\N{LATIN CAPITAL LETTER U WITH DIAERESIS}ber first. Second one. Third one."
    evidence = best_sentence(None, "n", text, MagicJudge(), model_id="m")
    assert (evidence.start, evidence.text) == (
        0,
        "\N{LATIN CAPITAL LETTER U WITH DIAERESIS}ber first.",
    )
    assert text[evidence.start : evidence.end] == evidence.text


def test_a_passage_without_a_sentence_has_no_evidence() -> None:
    with pytest.raises(ValueError, match="no sentence"):
        best_sentence(None, "n", "  \n ", MagicJudge(), model_id="m")


SENTENCES = st.lists(
    st.sampled_from(["Magic is here.", "Nothing here.", "Another plain line.", "Magic again."]),
    min_size=1,
    max_size=6,
)


@given(SENTENCES, st.text(alphabet=" \n", max_size=2))
def test_the_evidence_is_always_a_substring_of_the_passage(sentences: list[str], gap: str) -> None:
    passage = (" " + gap).join(sentences)
    evidence = best_sentence(None, "n", passage, MagicJudge(), model_id="m")
    assert passage[evidence.start : evidence.end] == evidence.text
    assert evidence.text.strip() == evidence.text
    assert ("Magic" in passage) == ("Magic" in evidence.text)
