"""Candidate retrieval contracts: exact offsets, delta-only queries, bounded repetition."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from influence.schemas.scoring import TOKEN_PATTERN
from influence.services.retrieval import MAX_PASSAGE_TOKENS, PassageIndex, split_passages

DOCUMENT = (
    "The market is large. Providers shall keep logs for ten years. "
    "Small firms need relief from audit duties.\n\n"
    "Another topic entirely: pizza recipes and gardening."
)


def _index() -> PassageIndex:
    return PassageIndex(split_passages("doc-a", DOCUMENT))


@given(st.text(max_size=3_000))
def test_passages_are_exact_ordered_and_bounded(text: str) -> None:
    passages = split_passages("d", text)
    previous_end = 0
    for passage in passages:
        assert passage.text == text[passage.start : passage.end]
        assert passage.start >= previous_end
        assert len(TOKEN_PATTERN.findall(passage.text)) <= MAX_PASSAGE_TOKENS
        previous_end = passage.end
    covered = sum(len(TOKEN_PATTERN.findall(p.text)) for p in passages)
    assert covered == len(TOKEN_PATTERN.findall(text))


def test_long_sentence_is_cut_not_truncated() -> None:
    text = " ".join(["word"] * (MAX_PASSAGE_TOKENS * 2 + 5))
    passages = split_passages("d", text)
    assert [len(p.text.split()) for p in passages] == [MAX_PASSAGE_TOKENS, MAX_PASSAGE_TOKENS, 5]


def test_blank_text_has_no_passages() -> None:
    assert split_passages("d", " \n\n ") == ()
    assert PassageIndex(()).search("a", None, "anything").candidates == ()


def test_delta_query_finds_the_requested_change() -> None:
    shortlist = _index().search(
        "a1", "Providers shall keep logs.", "Providers shall keep logs for ten years."
    )
    assert shortlist.query_kind == "delta"
    assert shortlist.query_terms == ("for", "ten", "years")
    top = shortlist.candidates[0]
    assert top.rank == 1
    assert "ten years" in top.passage.text
    assert set(top.matched_terms) <= set(shortlist.query_terms)


def test_wording_shared_with_the_original_is_not_searched() -> None:
    shortlist = _index().search("a1", "Small firms need relief.", "Small firms need relief.")
    assert shortlist.query_terms == ()
    assert shortlist.candidates == ()


def test_unknown_original_searches_whole_text_and_says_so() -> None:
    shortlist = _index().search("a1", None, "pizza recipes")
    assert shortlist.query_kind == "whole_text"
    assert "pizza" in shortlist.candidates[0].passage.text
    assert "original wording is unknown" in shortlist.limitations[1]


def test_known_empty_original_is_a_pure_insertion() -> None:
    shortlist = _index().search("a1", "", "ten years")
    assert shortlist.query_kind == "delta"
    assert shortlist.query_terms == ("ten", "years")


@pytest.mark.parametrize(("old", "new"), [("", ""), (None, "  ")])
def test_empty_amendment_text_is_rejected(old: str | None, new: str) -> None:
    with pytest.raises(ValueError, match="non-whitespace"):
        _index().search("a1", old, new)


def test_repetition_credit_is_bounded() -> None:
    """Thirty repeats of one word lose to one occurrence of two distinct query words."""
    passages = split_passages("a", "audit " * 30 + ".") + split_passages(
        "b", "A single audit duty applies to rare cats."
    )
    shortlist = PassageIndex(passages).search("x", "", "audit cats")
    assert shortlist.candidates[0].passage.document_id == "b"


def test_k_limits_and_ranks_are_dense() -> None:
    filler = " ".join(["filler"] * 100)
    text = "\n\n".join(f"{filler} audit {n}." for n in range(6))
    shortlist = PassageIndex(split_passages("d", text)).search("x", "", "audit", k=3)
    assert [c.rank for c in shortlist.candidates] == [1, 2, 3]
    scores = [c.score for c in shortlist.candidates]
    assert scores == sorted(scores, reverse=True)


def test_context_stays_inside_one_document() -> None:
    filler = " ".join(["filler"] * 100)
    text = "\n\n".join(f"{filler} {word}." for word in ("first", "second", "third"))
    passages = split_passages("a", text) + split_passages("b", "Only audit.")
    assert len(passages) == 4
    index = PassageIndex(passages)
    only = index.search("x", "", "audit").candidates[0]
    assert (only.context_start, only.context_end) == (passages[3].start, passages[3].end)
    middle = index.search("x", "", "second").candidates[0]
    assert (middle.context_start, middle.context_end) == (passages[0].start, passages[2].end)
    first = index.search("x", "", "first").candidates[0]
    assert (first.context_start, first.context_end) == (passages[0].start, passages[1].end)
    third = index.search("x", "", "third").candidates[0]
    assert (third.context_start, third.context_end) == (passages[1].start, passages[2].end)
