"""The Qwen reranker wrapper: tokens, left padding, masks and the logit read-out, with fakes."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import cast

import pytest

from influence.services.qwen_onnx import QwenError
from influence.services.qwen_reranker import MAX_TOKENS, QwenReranker

PAD = 9


@dataclass
class FakeEncoding:
    ids: Sequence[int]


class FakeTokenizer:
    def __init__(self, ids: dict[str, list[int]]) -> None:
        self._ids = ids
        self.special_tokens: list[bool] = []

    def encode_batch(self, inputs: list[str], *, add_special_tokens: bool) -> list[FakeEncoding]:
        self.special_tokens.append(add_special_tokens)
        return [FakeEncoding(self._ids[text]) for text in inputs]


class FakeArrays:
    def ints(self, rows: list[list[int]]) -> object:
        return rows


@dataclass
class FakeSession:
    feeds: list[dict[str, object]] = field(default_factory=list)

    def run(self, output_names: None, input_feed: dict[str, object]) -> list[object]:
        assert output_names is None
        self.feeds.append(input_feed)
        rows = cast("list[list[int]]", input_feed["input_ids"])
        # One logit per prompt: the number of real tokens it had, so each row is told apart.
        mask = cast("list[list[int]]", input_feed["attention_mask"])
        return [[[float(sum(line))] for line in mask[: len(rows)]]]


def build(ids: dict[str, list[int]]) -> tuple[QwenReranker, FakeSession, FakeTokenizer]:
    session, tokenizer = FakeSession(), FakeTokenizer(ids)
    return QwenReranker(session, tokenizer, FakeArrays(), PAD), session, tokenizer


def test_prompts_are_padded_on_the_left_and_tokenised_without_special_tokens() -> None:
    model, session, tokenizer = build({"long": [1, 2, 3], "short": [4]})
    assert model(["long", "short"]) == [3.0, 1.0]
    (feed,) = session.feeds
    assert feed["input_ids"] == [[1, 2, 3], [PAD, PAD, 4]]
    assert feed["attention_mask"] == [[1, 1, 1], [0, 0, 1]]
    assert tokenizer.special_tokens == [False]


def test_a_single_prompt_has_no_padding() -> None:
    model, session, _ = build({"only": [5, 6]})
    assert model(["only"]) == [2.0]
    assert session.feeds[0]["input_ids"] == [[5, 6]]


def test_no_prompts_means_no_scores_and_no_model_call() -> None:
    model, session, _ = build({})
    assert model([]) == []
    assert session.feeds == []


def test_a_prompt_longer_than_the_limit_is_refused_not_cut() -> None:
    model, session, _ = build({"huge": list(range(MAX_TOKENS + 1))})
    with pytest.raises(QwenError, match="longer than"):
        model(["huge"])
    assert session.feeds == []
