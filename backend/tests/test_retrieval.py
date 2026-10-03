"""Candidate retrieval contracts: exact offsets, delta-only queries, bounded repetition."""

from collections import Counter, defaultdict
from heapq import nlargest
from math import log

import pytest
from hypothesis import given
from hypothesis import strategies as st

from influence.schemas.retrieval import SourcePassage
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


def _walk_postings(
    passages: tuple[SourcePassage, ...], terms: tuple[str, ...], k: int
) -> list[tuple[int, float, tuple[str, ...]]]:
    """The per-posting BM25 walk the vectorized index replaced, kept as its oracle."""
    k1, b = 1.2, 0.75
    lengths: list[int] = []
    postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for index, passage in enumerate(passages):
        counts = Counter(
            token.casefold()
            for token in TOKEN_PATTERN.findall(passage.text)
            if any(c.isalnum() for c in token)
        )
        lengths.append(sum(counts.values()))
        for term, count in counts.items():
            postings[term].append((index, count))
    average = sum(lengths) / len(passages) if passages else 0.0
    scores: dict[int, float] = defaultdict(float)
    matched: dict[int, list[str]] = defaultdict(list)
    for term in terms:
        found = postings.get(term, ())
        idf = log(1 + (len(passages) - len(found) + 0.5) / (len(found) + 0.5))
        for index, count in found:
            norm = 1 - b + b * lengths[index] / average
            scores[index] += idf * count * (k1 + 1) / (count + k1 * norm)
            matched[index].append(term)
    best = nlargest(k, scores.items(), key=lambda item: (item[1], -item[0]))
    return [(index, score, tuple(matched[index])) for index, score in best]


_VOCABULARY = st.sampled_from(["audit", "the", "of", "logs", "ten", "years", "rare", "cats"])


@given(
    st.lists(st.lists(_VOCABULARY, max_size=12).map(" ".join), max_size=12),
    st.lists(_VOCABULARY, min_size=1, max_size=6).map(" ".join),
    st.integers(min_value=0, max_value=8),
)
def test_search_matches_the_per_posting_walk_exactly(texts: list[str], query: str, k: int) -> None:
    """Same passages, ranks, bit-identical scores and matched terms, ties included.

    A small vocabulary makes shared terms and equal scores common, so the tie-break and the
    top-k cut are exercised; k = 0 and k above the match count are drawn too.
    """
    passages = tuple(
        SourcePassage(document_id=f"d{n % 3}", start=0, end=len(text), text=text)
        for n, text in enumerate(texts)
    )
    shortlist = PassageIndex(passages).search("x", None, query, k=k)
    expected = _walk_postings(passages, shortlist.query_terms, k)
    assert [(c.passage, c.score, c.matched_terms) for c in shortlist.candidates] == [
        (passages[index], score, terms) for index, score, terms in expected
    ]
    assert [c.rank for c in shortlist.candidates] == list(range(1, len(expected) + 1))
