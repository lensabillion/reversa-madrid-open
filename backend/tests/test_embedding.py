"""The meaning signal without a model: a deterministic fake embedder stands in for Qwen."""

import hashlib
import math
from collections.abc import Sequence
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from influence.schemas.retrieval import SourcePassage
from influence.services.embedding import (
    QUERY_INSTRUCTION,
    DenseIndex,
    EmbeddingCache,
    EmbeddingError,
    cosine,
    delta_text,
    embed_texts,
    unit,
    with_instruction,
)

DIMENSIONS = 64


class BagOfWords:
    """Counts hashed words: texts sharing words point the same way, like a crude embedding."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * DIMENSIONS
            for word in text.casefold().split():
                digest = hashlib.sha256(word.encode()).digest()
                vector[digest[0] % DIMENSIONS] += 1.0
            vectors.append(vector)
        return vectors


def passage(text: str, document: str = "doc") -> SourcePassage:
    return SourcePassage(document_id=document, start=0, end=len(text), text=text)


def test_unit_scales_to_length_one_and_refuses_a_vector_without_direction() -> None:
    vector = unit([3.0, 4.0])
    assert vector == pytest.approx((0.6, 0.8))
    for bad in ([0.0, 0.0], [math.nan, 1.0], [math.inf, 1.0]):
        with pytest.raises(EmbeddingError, match="zero or non-finite"):
            unit(bad)


def test_cosine_of_unit_vectors_is_their_dot_product_and_stays_in_range() -> None:
    assert cosine((1.0, 0.0), (1.0, 0.0)) == 1.0
    assert cosine((1.0, 0.0), (0.0, 1.0)) == 0.0
    assert cosine((1.0, 0.0), (-1.0, 0.0)) == -1.0
    # Rounding can push a dot product of unit vectors a hair past 1; it is clamped.
    assert cosine((0.6000000000000001, 0.8000000000000002), (0.6, 0.8)) <= 1.0


@given(st.lists(st.floats(-1e3, 1e3), min_size=1, max_size=12).filter(lambda v: any(v)))
def test_a_unit_vector_has_length_one_and_cosine_with_itself_one(values: list[float]) -> None:
    vector = unit(values)
    assert math.sqrt(sum(x * x for x in vector)) == pytest.approx(1.0)
    assert cosine(vector, vector) == pytest.approx(1.0)


def test_the_query_is_phrased_as_the_retrieval_task() -> None:
    text = with_instruction("keep logs")
    assert text == f"Instruct: {QUERY_INSTRUCTION}\nQuery:keep logs"
    assert with_instruction("x", "do it") == "Instruct: do it\nQuery:x"


def test_delta_text_is_the_inserted_words_else_the_deleted_ones() -> None:
    assert delta_text(
        "Providers shall keep logs.", "Providers shall keep logs for six months."
    ) == ("for six months")
    assert delta_text("Remove the audit duty.", "Remove duty.") == "the audit"
    assert delta_text(None, "Whole new text.") == "Whole new text."
    with pytest.raises(ValueError, match="800 tokens"):
        delta_text("word " * 900, "other")


def test_the_cache_returns_exactly_what_was_stored_and_survives_reopening(tmp_path: Path) -> None:
    path = tmp_path / "vectors.sqlite3"
    cache = EmbeddingCache(path)
    stored = {"a": (0.1, -0.2, 1 / 3), "b": (1.0, 0.0, 0.0)}
    cache.store(stored)
    assert cache.load(["a", "b", "absent"]) == stored
    assert EmbeddingCache(path).load(["a"]) == {"a": stored["a"]}
    cache.store({"a": (9.0, 9.0, 9.0)})
    assert cache.load(["a"]) == {"a": (9.0, 9.0, 9.0)}


def test_each_distinct_text_is_embedded_once_in_batches_of_similar_length() -> None:
    embed = BagOfWords()
    texts = ["long long long long", "a", "bb", "a", "long long long long", "cc dd", "e"]
    vectors = embed_texts(texts, embed, model_id="m", batch_size=2)
    assert len(vectors) == len(texts)
    assert vectors[1] == vectors[3]
    assert vectors[0] == vectors[4]
    sent = [text for batch in embed.calls for text in batch]
    assert sorted(sent) == sorted(set(texts))
    assert all(len(batch) <= 2 for batch in embed.calls)
    assert sent == sorted(sent, key=len)
    assert all(math.sqrt(sum(x * x for x in v)) == pytest.approx(1.0) for v in vectors)


def test_a_cached_text_is_not_embedded_again_and_the_model_id_keys_the_cache(
    tmp_path: Path,
) -> None:
    cache = EmbeddingCache(tmp_path / "v.sqlite3")
    embed = BagOfWords()
    first = embed_texts(["alpha beta", "gamma"], embed, model_id="m1", cache=cache)
    assert embed_texts(["gamma", "alpha beta"], embed, model_id="m1", cache=cache) == [
        first[1],
        first[0],
    ]
    assert len(embed.calls) == 1
    embed_texts(["gamma"], embed, model_id="m2", cache=cache)
    assert len(embed.calls) == 2


def test_an_embedder_that_returns_the_wrong_number_of_vectors_is_an_error() -> None:
    with pytest.raises(EmbeddingError, match="Asked for 2 vectors, got 1"):
        embed_texts(["a", "b"], lambda texts: [[1.0, 0.0]], model_id="m")
    with pytest.raises(ValueError, match="batch_size"):
        embed_texts(["a"], BagOfWords(), model_id="m", batch_size=0)


def _index(embed: BagOfWords | None = None) -> DenseIndex:
    passages = [
        passage("providers shall keep technical logs for six months", "d1"),
        passage("the label must show the energy grade", "d2"),
        passage("small firms need a transition period", "d3"),
    ]
    return DenseIndex(passages, embed or BagOfWords(), model_id="m")


def test_search_ranks_passages_by_cosine_best_first_and_limits_k() -> None:
    index = _index()
    assert len(index) == 3
    hits = index.search("keep technical logs six months", k=2, instruction=None)
    assert [hit.passage.document_id for hit in hits] == ["d1", hits[1].passage.document_id]
    assert [hit.rank for hit in hits] == [1, 2]
    assert hits[0].score > hits[1].score
    assert len(index.search("keep technical logs", k=10, instruction=None)) == 3


def test_equal_scores_keep_passage_order() -> None:
    index = DenseIndex(
        [passage("same words", "first"), passage("same words", "second")],
        BagOfWords(),
        model_id="m",
    )
    hits = index.search("same words", k=2, instruction=None)
    assert [hit.passage.document_id for hit in hits] == ["first", "second"]
    assert hits[0].score == pytest.approx(hits[1].score)


def test_a_query_gets_the_instruction_unless_told_not_to() -> None:
    embed = BagOfWords()
    index = _index(embed)
    index.search("energy grade")
    assert embed.calls[-1] == [with_instruction("energy grade")]
    index.search("energy grade", instruction=None)
    assert embed.calls[-1] == ["energy grade"]


def test_a_query_without_text_is_refused() -> None:
    with pytest.raises(ValueError, match="no text"):
        _index().search("   ")
