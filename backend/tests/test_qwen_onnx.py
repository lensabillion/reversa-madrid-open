"""The Qwen ONNX wrapper: padding, positions, cache inputs and pooling, with a fake session."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import cast

import pytest

from influence.services.qwen_onnx import MAX_TOKENS, QwenEmbedder, QwenError

PAD = 9


@dataclass
class FakeEncoding:
    ids: Sequence[int]


class FakeTokenizer:
    def __init__(self, ids: dict[str, list[int]]) -> None:
        self._ids = ids

    def encode_batch(self, inputs: list[str]) -> list[FakeEncoding]:
        return [FakeEncoding(self._ids[text]) for text in inputs]


@dataclass
class FakeInput:
    name: str
    shape: Sequence[object] = ()


class FakeArrays:
    def ints(self, rows: list[list[int]]) -> object:
        return rows

    def empty_cache(self, batch: int, heads: int, head_dim: int) -> object:
        return ("cache", batch, heads, head_dim)


@dataclass
class FakeSession:
    inputs: list[FakeInput]
    feeds: list[dict[str, object]] = field(default_factory=list)

    def get_inputs(self) -> list[FakeInput]:
        return self.inputs

    def run(self, output_names: list[str], input_feed: dict[str, object]) -> list[object]:
        assert output_names == ["last_hidden_state"]
        self.feeds.append(input_feed)
        rows = cast("list[list[int]]", input_feed["input_ids"])
        # The hidden state at position p of row r is [r, p], so which position is read shows.
        return [[[[float(r), float(p)] for p in range(len(line))] for r, line in enumerate(rows)]]


GRAPH_INPUTS = [
    FakeInput("input_ids"),
    FakeInput("attention_mask"),
    FakeInput("position_ids"),
    FakeInput("past_key_values.0.key", ["batch_size", 8, "past", 128]),
    FakeInput("past_key_values.0.value", ["batch_size", 8, "past", 128]),
]


def build(
    ids: dict[str, list[int]], inputs: list[FakeInput] | None = None
) -> tuple[QwenEmbedder, FakeSession]:
    session = FakeSession(GRAPH_INPUTS if inputs is None else inputs)
    return QwenEmbedder(session, FakeTokenizer(ids), FakeArrays(), PAD), session


def test_a_batch_is_padded_on_the_right_with_positions_that_count_real_tokens() -> None:
    model, session = build({"long": [1, 2, 3], "short": [4]})
    model(["long", "short"])
    (feed,) = session.feeds
    assert feed["input_ids"] == [[1, 2, 3], [4, PAD, PAD]]
    assert feed["attention_mask"] == [[1, 1, 1], [1, 0, 0]]
    assert feed["position_ids"] == [[0, 1, 2], [0, 0, 0]]


def test_each_cache_input_gets_an_empty_cache_of_its_own_head_shape() -> None:
    model, session = build({"a": [1], "b": [2]})
    model(["a", "b"])
    (feed,) = session.feeds
    assert feed["past_key_values.0.key"] == ("cache", 2, 8, 128)
    assert feed["past_key_values.0.value"] == ("cache", 2, 8, 128)
    cache_names = {item.name for item in GRAPH_INPUTS[3:]}
    assert set(feed) == {"input_ids", "attention_mask", "position_ids", *cache_names}


def test_the_vector_is_the_hidden_state_at_the_last_real_token_of_each_text() -> None:
    model, _ = build({"long": [1, 2, 3], "short": [4]})
    # The fake's state at position p of row r is [r, p]: the last real token is at p = 2 for
    # the three-token text and p = 0 for the one-token text, not at the padded end.
    assert model(["long", "short"]) == [[0.0, 2.0], [1.0, 0.0]]


def test_no_texts_means_no_vectors_and_no_model_call() -> None:
    model, session = build({})
    assert model([]) == []
    assert session.feeds == []


def test_a_long_text_is_cut_but_keeps_its_end_of_text_token() -> None:
    model, session = build({"long": [*range(1, MAX_TOKENS + 100), 7], "short": [1, 7]})
    assert model.truncated == 0
    model(["long", "short"])
    assert model.truncated == 1
    model(["long"])
    assert model.truncated == 2
    sent = cast("list[list[int]]", session.feeds[0]["input_ids"])
    assert len(sent[0]) == MAX_TOKENS
    assert sent[0][-1] == 7
    assert sent[0][:3] == [1, 2, 3]


def test_a_cache_input_without_a_fixed_shape_is_an_error() -> None:
    model, _ = build({"a": [1]}, [FakeInput("past_key_values.0.key", ["batch", "heads", "p", 128])])
    with pytest.raises(QwenError, match="no fixed head shape"):
        model(["a"])
